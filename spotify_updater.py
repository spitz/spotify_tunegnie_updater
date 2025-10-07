"""Core Spotify playlist updating functionality."""

import base64
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional

import requests

from config import get_spotify_config, get_tunegenie_config


class SpotifyUpdater:
    """Handles fetching songs from TuneGenie and updating Spotify playlists."""

    def __init__(self):
        self.access_token = None
        self.processed_tracks = set()
        self.spotify_config = get_spotify_config()
        self.tunegenie_config = get_tunegenie_config()

    def get_yesterday_timeframe(self) -> Dict[str, str]:
        """Calculate yesterday's date range in the required format."""
        yesterday = datetime.now() - timedelta(days=1)
        since = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        until = yesterday.replace(hour=23, minute=59, second=0, microsecond=0)

        # Format with timezone offset from config
        timezone_offset = self.tunegenie_config['timezone_offset']
        return {
            "since": since.strftime(f"%Y-%m-%dT%H:%M:%S.00{timezone_offset}"),
            "until": until.strftime(f"%Y-%m-%dT%H:%M:%S.00{timezone_offset}")
        }

    def refresh_spotify_token(self) -> bool:
        """Refresh the Spotify access token using the refresh token."""
        token_url = "https://accounts.spotify.com/api/token"

        # Encode client credentials
        client_creds = f"{self.spotify_config['client_id']}:{self.spotify_config['client_secret']}"
        client_creds_b64 = base64.b64encode(client_creds.encode()).decode()

        headers = {
            "Authorization": f"Basic {client_creds_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.spotify_config['refresh_token']
        }

        try:
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data["access_token"]
            print("✓ Spotify access token refreshed successfully")
            return True
        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to refresh Spotify token: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            return False

    def fetch_tunegenie_songs(self) -> List[Dict]:
        """Fetch songs from TuneGenie API for yesterday."""
        timeframe = self.get_yesterday_timeframe()
        params = {**self.tunegenie_config['api_params'], **timeframe}

        print(f"Fetching songs from {timeframe['since']} to {timeframe['until']}")
        print(f"Full URL with params: {self.tunegenie_config['api_url']}")
        print(f"Parameters: {params}")

        try:
            response = requests.get(self.tunegenie_config['api_url'], params=params)
            response.raise_for_status()
            data = response.json()

            # Debug: Print the full JSON response
            print("\n" + "=" * 50)
            print("DEBUG: TuneGenie API Response:")
            print("=" * 50)
            print(json.dumps(data, indent=2))
            print("=" * 50 + "\n")

            # Extract song information
            songs = []
            # The API returns a direct array of song objects
            if isinstance(data, list):
                for item in data:
                    # Each item has 'artist' and 'song' fields at the root level
                    if "artist" in item and "song" in item:
                        song_info = {
                            "artist": item.get("artist", ""),
                            "title": item.get("song", ""),
                            "timestamp": item.get("played_at", "")
                        }
                        songs.append(song_info)

            print(f"✓ Found {len(songs)} songs from TuneGenie")
            return songs

        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to fetch TuneGenie data: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response text: {e.response.text}")
            return []

    def search_spotify_track(self, artist: str, title: str) -> str:
        """Search for a track on Spotify and return its URI."""
        if not self.access_token:
            return None

        # Clean up search query
        query = f"artist:{artist} track:{title}"

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        params = {
            "q": query,
            "type": "track",
            "limit": 1
        }

        try:
            response = requests.get(
                "https://api.spotify.com/v1/search",
                headers=headers,
                params=params
            )
            response.raise_for_status()
            data = response.json()

            if data["tracks"]["items"]:
                track = data["tracks"]["items"][0]
                return track["uri"]
            else:
                print(f"  ⚠ Track not found on Spotify: {artist} - {title}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error searching for track: {e}")
            return None

    def clear_playlist(self) -> bool:
        """Remove all tracks from the playlist."""
        if not self.access_token:
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        # Get all tracks in the playlist using pagination
        all_track_uris = []
        offset = 0
        limit = 50  # Maximum allowed by Spotify API for get tracks
        has_more_pages = True

        try:
            while has_more_pages:
                response = requests.get(
                    f"https://api.spotify.com/v1/playlists/{self.spotify_config['playlist_id']}/tracks",
                    headers=headers,
                    params={
                        "fields": "items(track(uri)),next,total",
                        "limit": limit,
                        "offset": offset
                    }
                )
                response.raise_for_status()
                data = response.json()

                # Extract track URIs from current batch
                batch_uris = [{"uri": item["track"]["uri"]} for item in data["items"] if item["track"]]
                all_track_uris.extend(batch_uris)

                # Check if there are more pages using the "next" field from Spotify API
                has_more_pages = data.get("next") is not None
                offset += limit

            if not all_track_uris:
                print("✓ Playlist is already empty")
                return True

            print(f"Found {len(all_track_uris)} tracks to remove from playlist")

            # Remove tracks in batches (Spotify API limits to 100 tracks per delete request)
            for i in range(0, len(all_track_uris), 100):
                batch = all_track_uris[i:i+100]

                response = requests.delete(
                    f"https://api.spotify.com/v1/playlists/{self.spotify_config['playlist_id']}/tracks",
                    headers=headers,
                    json={"tracks": batch}
                )
                response.raise_for_status()
                print(f"✓ Cleared {len(batch)} tracks from playlist")

            print(f"✓ Successfully cleared all {len(all_track_uris)} tracks from playlist")
            return True

        except requests.exceptions.RequestException as e:
            print(f"✗ Failed to clear playlist: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            return False

    def add_tracks_to_playlist(self, track_uris: List[str]) -> bool:
        """Add tracks to the playlist."""
        if not self.access_token or not track_uris:
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Spotify API limits to 100 tracks per request
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]

            try:
                response = requests.post(
                    f"https://api.spotify.com/v1/playlists/{self.spotify_config['playlist_id']}/tracks",
                    headers=headers,
                    json={"uris": batch}
                )
                response.raise_for_status()
                print(f"✓ Added {len(batch)} tracks to playlist")

            except requests.exceptions.RequestException as e:
                print(f"✗ Failed to add tracks to playlist: {e}")
                return False

        return True

    def run(self):
        """Main execution flow."""
        print("=" * 50)
        print("Starting Daily Spotify Playlist Update")
        print("=" * 50)

        # Step 1: Refresh Spotify token
        if not self.refresh_spotify_token():
            print("\nFailed to authenticate with Spotify.")
            print("Make sure you have set SPOTIFY_REFRESH_TOKEN correctly.")
            print("Run with --setup to get a new refresh token.")
            sys.exit(1)

        # Step 2: Fetch songs from TuneGenie
        songs = self.fetch_tunegenie_songs()
        if not songs:
            print("No songs found. Exiting.")
            sys.exit(0)

        # Step 3: Search for tracks on Spotify
        print("\nSearching for tracks on Spotify...")
        track_uris = []
        unique_tracks = {}  # Use dict to track unique songs

        for song in songs:
            # Create a unique key for each song
            key = f"{song['artist'].lower()}_{song['title'].lower()}"

            # Skip if we've already processed this song
            if key in unique_tracks:
                continue

            uri = self.search_spotify_track(song['artist'], song['title'])
            if uri:
                unique_tracks[key] = uri
                track_uris.append(uri)
                print(f"  ✓ Found: {song['artist']} - {song['title']}")

        print(f"\n✓ Found {len(track_uris)} unique tracks on Spotify")

        if not track_uris:
            print("No tracks found on Spotify. Exiting.")
            sys.exit(0)

        # Step 4: Clear existing playlist
        print("\nClearing existing playlist...")
        if not self.clear_playlist():
            print("Failed to clear playlist. Exiting.")
            sys.exit(1)

        # Step 5: Add new tracks
        print("\nAdding new tracks to playlist...")
        if self.add_tracks_to_playlist(track_uris):
            print(f"\n✓ Successfully updated playlist with {len(track_uris)} unique tracks!")
        else:
            print("\n✗ Failed to update playlist")
            sys.exit(1)