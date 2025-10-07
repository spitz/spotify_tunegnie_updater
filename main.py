#!/usr/bin/env python3
"""
Daily script to update a Spotify playlist with songs from TuneGenie API.
Fetches all songs from the previous day and replaces playlist contents.

Usage:
    python main.py --setup    # Run initial setup to get refresh token
    python main.py            # Run daily update
"""

import argparse
import sys

from config import get_spotify_config
from spotify_setup import SpotifySetup
from spotify_updater import SpotifyUpdater


def main():
    parser = argparse.ArgumentParser(
        description="Update Spotify playlist with songs from TuneGenie API"
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run setup to get Spotify refresh token"
    )

    args = parser.parse_args()

    if args.setup:
        # Run setup mode
        SpotifySetup.run_setup()
    else:
        # Check if credentials are configured
        spotify_config = get_spotify_config()

        if "YOUR_" in spotify_config['client_id'] or "YOUR_" in spotify_config['client_secret']:
            print("ERROR: Please configure your Spotify credentials in config.json.")
            print("\nRun with --setup flag to begin configuration:")
            print("  python main.py --setup")
            sys.exit(1)

        if "YOUR_" in spotify_config['refresh_token']:
            print("ERROR: Missing Spotify refresh token.")
            print("\nRun with --setup flag to authenticate:")
            print("  python main.py --setup")
            sys.exit(1)

        if "YOUR_" in spotify_config['daily_playlist_id']:
            print("ERROR: Please configure your daily playlist ID in config.json.")
            print("\nTo get your playlist ID:")
            print("1. Right-click on a playlist in Spotify")
            print("2. Share -> Copy link to playlist")
            print("3. Extract the ID from the URL")
            print("4. Update 'daily_playlist_id' in config.json")
            print("5. Optionally update 'cumulative_playlist_id' for a growing collection")
            sys.exit(1)

        # Run the updater
        updater = SpotifyUpdater()
        updater.run()


if __name__ == "__main__":
    main()