from flask import Flask, render_template, jsonify
import subprocess
import requests
import os
import time
import json
from bs4 import BeautifulSoup
import re
import shutil

app = Flask(__name__)

OLLAMA_URL = "https://ollama.com/library/"

def is_ollama_installed():
    """Check if 'ollama' command is available."""
    return shutil.which('ollama') is not None

def get_installed_models():
    """Retrieve a list of locally installed models."""
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None  # Indicate that 'ollama' is not installed or command failed

    lines = result.stdout.strip().split("\n")[1:]  # Skip the header
    if not lines:
        return []  # No models installed

    models = []
    for line in lines:
        parts = list(filter(None, line.split()))
        if len(parts) >= 4:
            model_name = parts[0]
            installed_version = parts[1]
            local_modified = ' '.join(parts[3:])  # e.g., "22 minutes ago" or "4 weeks ago"

            # Remove "GB" from local_modified
            if "GB" in local_modified:
                local_modified = local_modified.replace("GB", "").strip()

            models.append({
                'name': model_name,
                'installed_version': installed_version,
                'local_update': local_modified,
                # We'll fetch server_version and server_update later
            })
    return models

def get_server_model_info(model_names):
    """Fetch model info from the Ollama server without caching."""
    server_model_info = {}

    for model_name in model_names:
        print(f"Requesting data for: {model_name}", flush=True)
        try:
            server_version = get_model_info_from_web(model_name)
            if server_version:
                server_model_info[model_name] = server_version
        except Exception as e:
            print(f"Error fetching data for {model_name}: {e}", flush=True)
            server_model_info[model_name] = {'latest_update': 'Unknown', 'latest_hash': None}
        time.sleep(1)  # Add delay between requests to prevent rate limiting

    return server_model_info

def get_model_info_from_web(model_name):
    """Parse the Ollama website to get the hash and last update date of the model."""
    url = OLLAMA_URL + model_name
    response = requests.get(url)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract the version hash (e.g., 39c63e7675d7 · 5.0GB)
        hash_match = soup.find(string=re.compile(r'[0-9a-f]{12} · [0-9.]+GB'))
        latest_hash = None
        if hash_match:
            latest_hash = hash_match.split(' · ')[0].strip()

        # Extract the update date (e.g., Updated 11 days ago)
        update_match = soup.find(string=re.compile(r'Updated \d+ (day|week|month)s? ago'))
        latest_update = None
        if update_match:
            latest_update = update_match.strip()

        return {
            'latest_update': latest_update,
            'latest_hash': latest_hash
        }

    return {'latest_update': 'Unknown', 'latest_hash': None}

@app.route('/')
def index():
    # Render the template without performing heavy operations
    return render_template('index.html')

@app.route('/api/check_ollama')
def api_check_ollama():
    installed = is_ollama_installed()
    return jsonify({'installed': installed})

@app.route('/api/models')
def api_models():
    if not is_ollama_installed():
        return jsonify({'error': 'Ollama is not installed'}), 500

    models = get_installed_models()
    if models is None:
        return jsonify({'error': 'Failed to retrieve models'}), 500
    elif not models:
        return jsonify({'error': 'No models installed'}), 404

    model_names = [model['name'] for model in models]
    server_model_info = get_server_model_info(model_names)

    # Update models with server info
    for model in models:
        server_info = server_model_info.get(model['name'], {})
        model['server_version'] = server_info.get('latest_hash', 'Unknown')
        model['server_update'] = server_info.get('latest_update', 'Unknown')
        if model['server_version'] in (None, 'Unknown'):
            model['needs_update'] = False
            model['error'] = True
        else:
            model['needs_update'] = model['installed_version'] != model['server_version']
            model['error'] = False

    return jsonify(models)

@app.route('/api/recheck_model/<model_name>')
def api_recheck_model(model_name):
    if not is_ollama_installed():
        return jsonify({'error': 'Ollama is not installed'}), 500

    try:
        server_info = get_model_info_from_web(model_name)
        if server_info:
            model_info = {
                'name': model_name,
                'server_version': server_info.get('latest_hash', 'Unknown'),
                'server_update': server_info.get('latest_update', 'Unknown'),
                'error': False
            }
        else:
            model_info = {
                'name': model_name,
                'server_version': 'Unknown',
                'server_update': 'Unknown',
                'error': True
            }
    except Exception as e:
        print(f"Error fetching data for {model_name}: {e}", flush=True)
        model_info = {
            'name': model_name,
            'server_version': 'Unknown',
            'server_update': 'Unknown',
            'error': True
        }

    return jsonify(model_info)

if __name__ == '__main__':
    app.run(debug=True)