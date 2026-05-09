"""Configuration management for the Spotify TuneGenie updater.

Configuration can come from `config.json` or environment variables. When both
are present, environment variables win — this lets you bake a base config into
an image and override per-deployment via Synology Container Manager / Docker
`-e` flags.
"""

import json
import os
import sys
from typing import Dict, Any


CONFIG_FILE = "config.json"

DEFAULT_TUNEGENIE_API_URL = "https://api.tunegenie.com/v2/brand/nowplaying/"

# Map of env-var name -> (section, field) it overrides in the merged config.
ENV_OVERRIDES = {
    "SPOTIFY_CLIENT_ID": ("spotify", "client_id"),
    "SPOTIFY_CLIENT_SECRET": ("spotify", "client_secret"),
    "SPOTIFY_REFRESH_TOKEN": ("spotify", "refresh_token"),
    "SPOTIFY_DAILY_PLAYLIST_ID": ("spotify", "daily_playlist_id"),
    "SPOTIFY_CUMULATIVE_PLAYLIST_ID": ("spotify", "cumulative_playlist_id"),
    "SPOTIFY_MAX_CUMULATIVE_TRACKS": ("spotify", "max_cumulative_tracks"),
    "TUNEGENIE_API_URL": ("tunegenie", "api_url"),
    "TUNEGENIE_API_ID": ("tunegenie", "api_id"),
    "TUNEGENIE_BRAND": ("tunegenie", "brand"),
    "TUNEGENIE_TIMEZONE_OFFSET": ("tunegenie", "timezone_offset"),
}

INT_FIELDS = {("spotify", "max_cumulative_tracks")}


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("YOUR_")


def _load_file_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {CONFIG_FILE}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read {CONFIG_FILE}: {e}")
        sys.exit(1)


def load_config() -> Dict[str, Any]:
    """Load config from file (if present) and overlay environment variables."""
    config = _load_file_config()
    config.setdefault("spotify", {})
    config.setdefault("tunegenie", {})

    # Strip placeholder values from the file so env vars (or required-field
    # checks) treat them as missing.
    for section in ("spotify", "tunegenie"):
        for key, value in list(config[section].items()):
            if _is_placeholder(value):
                config[section][key] = ""

    for env_name, (section, field) in ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        if (section, field) in INT_FIELDS:
            try:
                config[section][field] = int(raw)
            except ValueError:
                print(f"ERROR: {env_name} must be an integer, got: {raw!r}")
                sys.exit(1)
        else:
            config[section][field] = raw

    return config


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration to JSON file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"ERROR: Failed to save {CONFIG_FILE}: {e}")
        return False


def _require(section: Dict[str, Any], key: str, env_name: str) -> str:
    value = section.get(key)
    if not value:
        print(f"ERROR: missing required config '{key}'.")
        print(f"  Provide it via environment variable {env_name} or in {CONFIG_FILE}.")
        sys.exit(1)
    return value


def get_spotify_config() -> Dict[str, Any]:
    """Get Spotify configuration values."""
    config = load_config()
    spotify = config.get("spotify", {})
    return {
        'client_id': _require(spotify, 'client_id', 'SPOTIFY_CLIENT_ID'),
        'client_secret': _require(spotify, 'client_secret', 'SPOTIFY_CLIENT_SECRET'),
        'refresh_token': _require(spotify, 'refresh_token', 'SPOTIFY_REFRESH_TOKEN'),
        'daily_playlist_id': _require(spotify, 'daily_playlist_id', 'SPOTIFY_DAILY_PLAYLIST_ID'),
        'cumulative_playlist_id': spotify.get('cumulative_playlist_id', '') or '',
        'max_cumulative_tracks': spotify.get('max_cumulative_tracks', 9000),
    }


def get_tunegenie_config() -> Dict[str, Any]:
    """Get TuneGenie configuration values."""
    config = load_config()
    tunegenie = config.get("tunegenie", {})
    return {
        'api_url': tunegenie.get('api_url') or DEFAULT_TUNEGENIE_API_URL,
        'api_params': {
            "apiid": _require(tunegenie, 'api_id', 'TUNEGENIE_API_ID'),
            "b": _require(tunegenie, 'brand', 'TUNEGENIE_BRAND'),
        },
        'timezone_offset': tunegenie.get('timezone_offset', '-04:00'),
    }


# Spotify OAuth constants
SPOTIFY_REDIRECT_URI = "https://oauth.pstmn.io/v1/callback"
SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private"
