#!/usr/bin/env python3
"""
Daily script to update a Spotify playlist with songs from TuneGenie API.
Fetches all songs from the previous day and replaces playlist contents.

Usage:
    python main.py --setup    # Run initial setup to get refresh token
    python main.py            # Run daily update
"""

import argparse

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
        # Validate that all required Spotify config is present (config.py
        # exits with a helpful message naming the missing field/env var).
        get_spotify_config()

        # Run the updater
        updater = SpotifyUpdater()
        updater.run()


if __name__ == "__main__":
    main()