"""Core Spotify playlist updating functionality."""

import base64
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional

import requests

from config import get_spotify_config, get_tunegenie_config
from database import CacheDatabase


class SpotifyUpdater:
    """Handles fetching songs from TuneGenie and updating Spotify playlists."""

    def __init__(self):
        self.access_token = None
        self.processed_tracks = set()
        self.spotify_config = get_spotify_config()
        self.tunegenie_config = get_tunegenie_config()
        self.cache_db = CacheDatabase()

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
                        # Use TuneGenie's "sid" field as the unique identifier
                        tunegenie_id = item.get("sid")
                        if not tunegenie_id:
                            # Fallback: create ID from timestamp + artist + song for uniqueness
                            timestamp = item.get("played_at", "")
                            tunegenie_id = f"fallback_{timestamp}_{item.get('artist', '')}_{item.get('song', '')}"

                        song_info = {
                            "tunegenie_id": tunegenie_id,
                            "artist": item.get("artist", ""),
                            "title": item.get("song", ""),
                            "timestamp": item.get("played_at", ""),
                            "raw_data": item  # Store full data for debugging
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

    def search_spotify_track(self, tunegenie_id: str, artist: str, title: str) -> str:
        """Search for a track on Spotify and return its URI, using cache when possible."""
        if not self.access_token:
            return None

        # Check cache first
        cached_uri = self.cache_db.get_cached_track_search(tunegenie_id)
        if cached_uri:
            print(f"  ✓ Cache hit: {artist} - {title}")
            return cached_uri

        # Cache miss - perform Spotify search
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
                spotify_uri = track["uri"]

                # Cache the successful result
                self.cache_db.cache_track_search(
                    tunegenie_id=tunegenie_id,
                    tunegenie_artist=artist,
                    tunegenie_title=title,
                    spotify_uri=spotify_uri,
                    spotify_artist=track["artists"][0]["name"] if track["artists"] else None,
                    spotify_title=track["name"],
                    spotify_album=track["album"]["name"] if track["album"] else None
                )

                print(f"  ✓ Found: {artist} - {title}")
                return spotify_uri
            else:
                # Cache the failed search to avoid repeating it
                self.cache_db.cache_track_search(
                    tunegenie_id=tunegenie_id,
                    tunegenie_artist=artist,
                    tunegenie_title=title,
                    spotify_uri=None
                )
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
                    f"https://api.spotify.com/v1/playlists/{self.spotify_config['daily_playlist_id']}/tracks",
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
                    f"https://api.spotify.com/v1/playlists/{self.spotify_config['daily_playlist_id']}/tracks",
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

    def sync_playlist_cache(self, playlist_id: str, playlist_name: str, playlist_type: str):
        """Sync playlist contents with cache."""
        if not self.access_token or not playlist_id:
            return

        print(f"Syncing {playlist_name} playlist cache...")

        # Add/update playlist in cache
        self.cache_db.add_or_update_playlist(playlist_id, playlist_name, playlist_type)

        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        all_track_data = []  # Store (uri, added_at) tuples
        offset = 0
        limit = 50  # Maximum allowed by Spotify API for get tracks
        has_more_pages = True

        try:
            while has_more_pages:
                response = requests.get(
                    f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                    headers=headers,
                    params={
                        "fields": "items(track(uri,name,artists,album),added_at),next,total",
                        "limit": limit,
                        "offset": offset
                    }
                )
                response.raise_for_status()
                data = response.json()

                # Extract track URIs and added_at timestamps from current batch
                for item in data["items"]:
                    if item["track"]:
                        all_track_data.append((
                            item["track"]["uri"],
                            item.get("added_at")  # This is the Spotify-provided timestamp
                        ))

                # Check if there are more pages using the "next" field from Spotify API
                has_more_pages = data.get("next") is not None
                offset += limit

            # Update cache with current playlist contents including timestamps
            self.cache_db.update_playlist_tracks_with_timestamps(playlist_id, all_track_data)
            print(f"✓ Synced {len(all_track_data)} tracks in {playlist_name} playlist cache")

        except requests.exceptions.RequestException as e:
            print(f"⚠ Failed to sync {playlist_name} playlist cache: {e}")

    def get_existing_tracks_from_cumulative_playlist(self) -> Set[str]:
        """Get all existing track URIs from the cumulative playlist cache."""
        if not self.spotify_config['cumulative_playlist_id']:
            return set()

        # Try to get from cache first
        cached_tracks = self.cache_db.get_playlist_tracks(self.spotify_config['cumulative_playlist_id'])

        if cached_tracks:
            print(f"✓ Found {len(cached_tracks)} existing tracks in cumulative playlist (from cache)")
            return cached_tracks
        else:
            # Cache miss - sync from Spotify and return
            self.sync_playlist_cache(
                self.spotify_config['cumulative_playlist_id'],
                "Cumulative",
                "cumulative"
            )
            return self.cache_db.get_playlist_tracks(self.spotify_config['cumulative_playlist_id'])

    def add_tracks_to_playlist(self, track_uris: List[str], playlist_type: str = "daily") -> bool:
        """Add tracks to the specified playlist."""
        if not self.access_token or not track_uris:
            return False

        # Determine which playlist to use
        if playlist_type == "daily":
            playlist_id = self.spotify_config['daily_playlist_id']
            playlist_name = "daily"
        elif playlist_type == "cumulative":
            playlist_id = self.spotify_config['cumulative_playlist_id']
            playlist_name = "cumulative"
        else:
            print(f"✗ Unknown playlist type: {playlist_type}")
            return False

        if not playlist_id:
            print(f"⚠ No {playlist_name} playlist ID configured, skipping")
            return True

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Spotify API limits to 100 tracks per request
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i+100]

            try:
                response = requests.post(
                    f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                    headers=headers,
                    json={"uris": batch}
                )
                response.raise_for_status()
                print(f"✓ Added {len(batch)} tracks to {playlist_name} playlist")

            except requests.exceptions.RequestException as e:
                print(f"✗ Failed to add tracks to {playlist_name} playlist: {e}")
                return False

        return True

    def add_new_tracks_to_cumulative_playlist(self, track_uris: List[str]) -> bool:
        """Add only new tracks to the cumulative playlist."""
        if not self.spotify_config['cumulative_playlist_id']:
            print("⚠ No cumulative playlist configured, skipping")
            return True

        print("\nProcessing cumulative playlist...")
        existing_tracks = self.get_existing_tracks_from_cumulative_playlist()

        # Filter out tracks that already exist
        new_tracks = [uri for uri in track_uris if uri not in existing_tracks]

        if not new_tracks:
            print("✓ All tracks already exist in cumulative playlist")
            return True

        print(f"Adding {len(new_tracks)} new tracks to cumulative playlist...")

        # Add tracks in smaller batches with better error handling for cumulative playlist
        success = self.add_tracks_to_cumulative_playlist_batched(new_tracks)

        if success:
            # Update cache with new tracks
            updated_tracks = existing_tracks | set(new_tracks)
            self.cache_db.update_playlist_tracks(self.spotify_config['cumulative_playlist_id'], list(updated_tracks))

            # Check if we need to trim the playlist to stay within limits
            self.trim_cumulative_playlist_if_needed()

        return success

    def add_tracks_to_cumulative_playlist_batched(self, track_uris: List[str]) -> bool:
        """Add tracks to cumulative playlist with enhanced error handling and smaller batches."""
        if not self.access_token or not track_uris:
            return False

        playlist_id = self.spotify_config['cumulative_playlist_id']
        if not playlist_id:
            print("⚠ No cumulative playlist ID configured")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Use smaller batch size for cumulative playlist to avoid issues
        batch_size = 50  # Reduced from 100 to be more conservative
        total_added = 0
        failed_batches = 0

        for i in range(0, len(track_uris), batch_size):
            batch = track_uris[i:i + batch_size]
            batch_number = (i // batch_size) + 1

            # Validate URIs in this batch
            valid_uris = [uri for uri in batch if uri and uri.startswith('spotify:track:')]
            if len(valid_uris) != len(batch):
                print(f"⚠ Batch {batch_number}: Filtered out {len(batch) - len(valid_uris)} invalid URIs")

            if not valid_uris:
                print(f"⚠ Batch {batch_number}: No valid URIs to add")
                continue

            try:
                response = requests.post(
                    f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                    headers=headers,
                    json={"uris": valid_uris}
                )

                if response.status_code == 200 or response.status_code == 201:
                    total_added += len(valid_uris)
                    print(f"✓ Added {len(valid_uris)} tracks to cumulative playlist (batch {batch_number})")
                else:
                    print(f"✗ Failed to add batch {batch_number}: HTTP {response.status_code}")
                    print(f"Response: {response.text}")
                    failed_batches += 1

                    # Continue with next batch instead of failing completely
                    continue

            except requests.exceptions.RequestException as e:
                print(f"✗ Error adding batch {batch_number} to cumulative playlist: {e}")
                failed_batches += 1
                continue

        # Consider success if at least some batches worked
        if total_added > 0:
            print(f"✓ Successfully added {total_added} tracks to cumulative playlist")
            if failed_batches > 0:
                print(f"⚠ {failed_batches} batches failed, but partial success achieved")
            return True
        else:
            print(f"✗ Failed to add any tracks to cumulative playlist ({failed_batches} batches failed)")
            return False

    def remove_tracks_from_playlist(self, playlist_id: str, track_uris: List[str]) -> bool:
        """Remove tracks from a Spotify playlist."""
        if not self.access_token or not track_uris or not playlist_id:
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        # Remove tracks in batches (Spotify API limits to 100 tracks per delete request)
        for i in range(0, len(track_uris), 100):
            batch = track_uris[i:i + 100]
            tracks_to_remove = [{"uri": uri} for uri in batch]

            try:
                response = requests.delete(
                    f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
                    headers=headers,
                    json={"tracks": tracks_to_remove}
                )
                response.raise_for_status()
                print(f"✓ Removed {len(batch)} tracks from cumulative playlist")

            except requests.exceptions.RequestException as e:
                print(f"✗ Failed to remove batch of tracks from cumulative playlist: {e}")
                return False

        return True

    def trim_cumulative_playlist_if_needed(self) -> bool:
        """Check if cumulative playlist exceeds max size and trim oldest tracks if needed."""
        playlist_id = self.spotify_config['cumulative_playlist_id']
        max_tracks = self.spotify_config['max_cumulative_tracks']

        if not playlist_id:
            return True

        current_count = self.cache_db.get_playlist_track_count(playlist_id)
        print(f"Current cumulative playlist size: {current_count} tracks (max: {max_tracks})")

        if current_count <= max_tracks:
            return True

        # Calculate how many tracks to remove
        tracks_to_remove_count = current_count - max_tracks + 50  # Remove extra 50 to give breathing room
        print(f"Playlist exceeds limit, removing {tracks_to_remove_count} oldest tracks...")

        # Get the oldest tracks
        oldest_track_uris = self.cache_db.get_oldest_tracks_from_playlist(playlist_id, tracks_to_remove_count)

        if not oldest_track_uris:
            print("⚠ No tracks found to remove (possible cache issue)")
            return True

        # Remove from Spotify
        if self.remove_tracks_from_playlist(playlist_id, oldest_track_uris):
            # Remove from cache
            self.cache_db.remove_tracks_from_playlist_cache(playlist_id, oldest_track_uris)
            print(f"✓ Successfully trimmed {len(oldest_track_uris)} tracks from cumulative playlist")
            return True
        else:
            print("✗ Failed to trim cumulative playlist")
            return False

    def initialize_cache(self):
        """Initialize cache with current playlist contents on first run."""
        cache_stats = self.cache_db.get_cache_stats()

        # If this is the first run (no playlists in cache), populate cache
        if cache_stats['playlist_count'] == 0:
            print("\nInitializing cache with current playlist contents...")

            # Sync daily playlist
            if self.spotify_config['daily_playlist_id']:
                self.sync_playlist_cache(
                    self.spotify_config['daily_playlist_id'],
                    "Daily",
                    "daily"
                )

            # Sync cumulative playlist
            if self.spotify_config['cumulative_playlist_id']:
                self.sync_playlist_cache(
                    self.spotify_config['cumulative_playlist_id'],
                    "Cumulative",
                    "cumulative"
                )

            print("✓ Cache initialization complete")

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

        # Step 1.5: Initialize cache with current playlist contents if needed
        self.initialize_cache()

        # Step 2: Fetch songs from TuneGenie
        songs = self.fetch_tunegenie_songs()
        if not songs:
            print("No songs found. Exiting.")
            sys.exit(0)

        # Step 3: Search for tracks on Spotify (with caching)
        print("\nSearching for tracks on Spotify...")
        track_uris = []
        unique_tracks = {}  # Use dict to track unique songs
        tunegenie_ids = []  # Track TuneGenie IDs for cache updates

        for song in songs:
            # Create a unique key for each song
            key = f"{song['artist'].lower()}_{song['title'].lower()}"

            # Skip if we've already processed this song in this batch
            if key in unique_tracks:
                continue

            uri = self.search_spotify_track(song['tunegenie_id'], song['artist'], song['title'])
            if uri:
                unique_tracks[key] = uri
                track_uris.append(uri)
                tunegenie_ids.append(song['tunegenie_id'])

        print(f"\n✓ Found {len(track_uris)} unique tracks on Spotify")

        # Display cache statistics
        cache_stats = self.cache_db.get_cache_stats()
        print(f"Cache stats: {cache_stats['successful_searches']}/{cache_stats['total_searches']} successful searches cached")

        if not track_uris:
            print("No tracks found on Spotify. Exiting.")
            sys.exit(0)

        # Step 4: Clear existing daily playlist
        print("\nClearing existing daily playlist...")
        if not self.clear_playlist():
            print("Failed to clear daily playlist. Exiting.")
            sys.exit(1)

        # Step 5: Add new tracks to daily playlist
        print("\nAdding new tracks to daily playlist...")
        if not self.add_tracks_to_playlist(track_uris, "daily"):
            print("\n✗ Failed to update daily playlist")
            sys.exit(1)

        # Update daily playlist cache
        self.cache_db.update_playlist_tracks(self.spotify_config['daily_playlist_id'], track_uris)

        # Step 6: Add new tracks to cumulative playlist (only if they don't already exist)
        if not self.add_new_tracks_to_cumulative_playlist(track_uris):
            print("\n✗ Failed to update cumulative playlist")
            sys.exit(1)

        print(f"\n✓ Successfully updated playlists with {len(track_uris)} unique tracks!")

        # Show final cache statistics
        final_stats = self.cache_db.get_cache_stats()
        print(f"Final cache stats: {final_stats['successful_searches']} successful searches, "
              f"{final_stats['playlist_track_count']} total playlist entries")