"""Configuration management for the Spotify TuneGenie updater."""

import json
import os
import sys
from typing import Dict, Any


CONFIG_FILE = "config.json"


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file."""
    if not os.path.exists(CONFIG_FILE):
        print(f"ERROR: Configuration file '{CONFIG_FILE}' not found.")
        print("\nTo set up:")
        print("1. Copy 'config.json.template' to 'config.json'")
        print("2. Fill in your credentials")
        print("3. Run the script again")
        sys.exit(1)

    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            return config
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {CONFIG_FILE}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read {CONFIG_FILE}: {e}")
        sys.exit(1)


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"ERROR: Failed to save {CONFIG_FILE}: {e}")
        return False


def get_spotify_config() -> Dict[str, str]:
    """Get Spotify configuration values."""
    config = load_config()
    return {
        'client_id': config['spotify']['client_id'],
        'client_secret': config['spotify']['client_secret'],
        'refresh_token': config['spotify']['refresh_token'],
        'playlist_id': config['spotify']['playlist_id']
    }


def get_tunegenie_config() -> Dict[str, Any]:
    """Get TuneGenie configuration values."""
    config = load_config()
    return {
        'api_url': config['tunegenie']['api_url'],
        'api_params': {
            "apiid": config['tunegenie']['api_id'],
            "b": config['tunegenie']['brand']
        },
        'timezone_offset': config['tunegenie'].get('timezone_offset', '-04:00')
    }


# Spotify OAuth constants
SPOTIFY_REDIRECT_URI = "https://oauth.pstmn.io/v1/callback"
SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private"