#!/usr/bin/env python3
"""
Daily script to update a Spotify playlist with songs from TuneGenie API.
Fetches all songs from the previous day and replaces playlist contents.

Usage:
    python script.py --setup    # Run initial setup to get refresh token
    python script.py            # Run daily update
"""

import requests
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional
import base64
import sys
import argparse
import webbrowser
from urllib.parse import urlparse, parse_qs
import time

# ============== CONFIGURATION ==============
# Load configuration from external file
CONFIG_FILE = "config.json"

def load_config():
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

# Load configuration
config = load_config()

# Spotify credentials
SPOTIFY_CLIENT_ID = config['spotify']['client_id']
SPOTIFY_CLIENT_SECRET = config['spotify']['client_secret']
SPOTIFY_REFRESH_TOKEN = config['spotify']['refresh_token']
SPOTIFY_PLAYLIST_ID = config['spotify']['playlist_id']

# TuneGenie configuration
TUNEGENIE_API_URL = config['tunegenie']['api_url']
TUNEGENIE_PARAMS = {
    "apiid": config['tunegenie']['api_id'],
    "b": config['tunegenie']['brand']
}
TIMEZONE_OFFSET = config['tunegenie'].get('timezone_offset', '-04:00')

# Spotify OAuth settings
SPOTIFY_REDIRECT_URI = "https://oauth.pstmn.io/v1/callback"  # Postman's public OAuth callback URL
SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private"

# ============================================


class SpotifySetup:
    """Handle initial Spotify OAuth setup to get refresh token."""
    
    @staticmethod
    def get_auth_url() -> str:
        """Generate the Spotify authorization URL."""
        params = {
            "client_id": SPOTIFY_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": SPOTIFY_REDIRECT_URI,
            "scope": SPOTIFY_SCOPE,
            "show_dialog": "true"
        }
        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"https://accounts.spotify.com/authorize?{param_string}"
    
    @staticmethod
    def exchange_code_for_tokens(auth_code: str) -> Optional[Dict]:
        """Exchange authorization code for access and refresh tokens."""
        token_url = "https://accounts.spotify.com/api/token"
        
        client_creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        client_creds_b64 = base64.b64encode(client_creds.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {client_creds_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": SPOTIFY_REDIRECT_URI
        }
        
        try:
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error exchanging code for tokens: {e}")
            if hasattr(e.response, 'text'):
                print(f"Response: {e.response.text}")
            return None
    
    @staticmethod
    def run_setup():
        """Run the interactive setup process."""
        print("=" * 60)
        print("SPOTIFY AUTHENTICATION SETUP")
        print("=" * 60)
        
        # Check if credentials are configured
        if "YOUR_" in SPOTIFY_CLIENT_ID or "YOUR_" in SPOTIFY_CLIENT_SECRET:
            print("\n⚠️  First, you need to configure your Spotify App credentials:")
            print("1. Go to https://developer.spotify.com/dashboard")
            print("2. Create a new app (or use existing)")
            print(f"3. Add EXACTLY this Redirect URI to your app settings:")
            print(f"   {SPOTIFY_REDIRECT_URI}")
            print("4. Update SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in this script")
            print("\nAfter updating the credentials, run --setup again.")
            return
        
        print(f"\nClient ID: {SPOTIFY_CLIENT_ID[:20]}...")
        print("✓ Credentials detected\n")
        
        # Generate and open auth URL
        auth_url = SpotifySetup.get_auth_url()
        print("Opening Spotify authorization page in your browser...")
        print("\nIf the browser doesn't open automatically, visit this URL:")
        print(f"\n{auth_url}\n")
        
        try:
            webbrowser.open(auth_url)
        except:
            pass
        
        print("=" * 60)
        print("IMPORTANT INSTRUCTIONS:")
        print("=" * 60)
        print("\n1. Authorize the app in your browser")
        print("2. You'll be redirected to oauth.pstmn.io")
        print("3. The page will show 'You've been authenticated!'")
        print("4. Look at the URL in your browser's address bar")
        print("5. Copy the 'code' parameter from the URL")
        print("\nThe URL will look like:")
        print("https://oauth.pstmn.io/v1/callback?code=AQD3x...")
        print("\nYou need just the code part after 'code='")
        
        # Get the code from user
        auth_code = input("\nPaste the authorization code here: ").strip()
        
        # Clean up the code if user pasted the whole URL
        if "code=" in auth_code:
            # User might have pasted the whole URL
            try:
                parsed = urlparse(auth_code)
                params = parse_qs(parsed.query)
                if 'code' in params:
                    auth_code = params['code'][0]
                    print("✓ Extracted code from URL")
            except:
                # Try simple split
                if "code=" in auth_code:
                    auth_code = auth_code.split("code=")[1].split("&")[0]
        
        if not auth_code:
            print("\n✗ No authorization code provided")
            return
        
        print("\n✓ Authorization code received")
        
        # Exchange code for tokens
        print("Exchanging authorization code for tokens...")
        tokens = SpotifySetup.exchange_code_for_tokens(auth_code)
        
        if not tokens:
            print("\n✗ Failed to get tokens")
            print("\nCommon issues:")
            print("- Make sure the Redirect URI in your app matches EXACTLY:")
            print(f"  {SPOTIFY_REDIRECT_URI}")
            print("- The authorization code expires quickly (within a few minutes)")
            print("- Each code can only be used once")
            return
        
        if 'refresh_token' not in tokens:
            print("\n✗ No refresh token received")
            print("This might happen if you've already authorized this app.")
            print("Try removing the app from your Spotify account and re-authorizing:")
            print("1. Go to https://www.spotify.com/account/apps/")
            print("2. Remove this app")
            print("3. Run --setup again")
            return
        
        refresh_token = tokens['refresh_token']
        access_token = tokens['access_token']
        
        print("✓ Tokens received successfully!")
        
        # Test the tokens by getting user profile
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get("https://api.spotify.com/v1/me", headers=headers)
            response.raise_for_status()
            user_data = response.json()
            print(f"✓ Authenticated as: {user_data.get('display_name', user_data.get('id'))}")
        except:
            print("⚠️  Could not verify authentication (but tokens were received)")
        
        # Display the refresh token
        print("\n" + "=" * 60)
        print("SETUP COMPLETE!")
        print("=" * 60)
        print("\nYour refresh token:")
        print(f"\n{refresh_token}\n")
        
        # Offer to update config file
        print("Would you like to automatically update your config.json file?")
        update_config = input("Enter 'yes' to update, or 'no' to do it manually: ").strip().lower()
        
        if update_config == 'yes':
            try:
                config['spotify']['refresh_token'] = refresh_token
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(config, f, indent=4)
                print(f"\n✓ Updated {CONFIG_FILE} with your refresh token")
            except Exception as e:
                print(f"\n⚠️  Could not update {CONFIG_FILE}: {e}")
                print("Please update it manually with the refresh token shown above.")
        else:
            print(f"\nPlease update the SPOTIFY_REFRESH_TOKEN in {CONFIG_FILE} with the value shown above.")
        
        # Also show playlist instruction
        print("\nTo get your playlist ID:")
        print("1. Right-click on a playlist in Spotify")
        print("2. Share -> Copy link to playlist")
        print("3. Extract the ID from the URL:")
        print("   https://open.spotify.com/playlist/[PLAYLIST_ID]?...")
        print(f"\nUpdate SPOTIFY_PLAYLIST_ID in {CONFIG_FILE} with your playlist ID.")
        print("\nOnce both values are updated, run the script without --setup to update your playlist.")


class SpotifyUpdater:
    def __init__(self):
        self.access_token = None
        self.processed_tracks = set()
        
    def get_yesterday_timeframe(self) -> Dict[str, str]:
        """Calculate yesterday's date range in the required format."""
        yesterday = datetime.now() - timedelta(days=1)
        since = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        until = yesterday.replace(hour=23, minute=59, second=0, microsecond=0)
        
        # Format with timezone offset from config
        return {
            "since": since.strftime(f"%Y-%m-%dT%H:%M:%S.00{TIMEZONE_OFFSET}"),
            "until": until.strftime(f"%Y-%m-%dT%H:%M:%S.00{TIMEZONE_OFFSET}")
        }
    
    def refresh_spotify_token(self) -> bool:
        """Refresh the Spotify access token using the refresh token."""
        token_url = "https://accounts.spotify.com/api/token"
        
        # Encode client credentials
        client_creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        client_creds_b64 = base64.b64encode(client_creds.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {client_creds_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": SPOTIFY_REFRESH_TOKEN
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
        params = {**TUNEGENIE_PARAMS, **timeframe}
        
        print(f"Fetching songs from {timeframe['since']} to {timeframe['until']}")
        print(f"Full URL with params: {TUNEGENIE_API_URL}")
        print(f"Parameters: {params}")
        
        try:
            response = requests.get(TUNEGENIE_API_URL, params=params)
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
        
        # First, get all tracks in the playlist
        try:
            response = requests.get(
                f"https://api.spotify.com/v1/playlists/{SPOTIFY_PLAYLIST_ID}/tracks",
                headers=headers,
                params={"fields": "items(track(uri))"}
            )
            response.raise_for_status()
            data = response.json()
            
            if not data["items"]:
                print("✓ Playlist is already empty")
                return True
            
            # Remove all tracks
            track_uris = [{"uri": item["track"]["uri"]} for item in data["items"] if item["track"]]
            
            response = requests.delete(
                f"https://api.spotify.com/v1/playlists/{SPOTIFY_PLAYLIST_ID}/tracks",
                headers=headers,
                json={"tracks": track_uris}
            )
            response.raise_for_status()
            print(f"✓ Cleared {len(track_uris)} tracks from playlist")
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
                    f"https://api.spotify.com/v1/playlists/{SPOTIFY_PLAYLIST_ID}/tracks",
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
        if "YOUR_" in SPOTIFY_CLIENT_ID or "YOUR_" in SPOTIFY_CLIENT_SECRET:
            print("ERROR: Please configure your Spotify credentials in the script.")
            print("\nRun with --setup flag to begin configuration:")
            print("  python script.py --setup")
            sys.exit(1)
        
        if "YOUR_" in SPOTIFY_REFRESH_TOKEN:
            print("ERROR: Missing Spotify refresh token.")
            print("\nRun with --setup flag to authenticate:")
            print("  python script.py --setup")
            sys.exit(1)
        
        if "YOUR_" in SPOTIFY_PLAYLIST_ID:
            print("ERROR: Please configure your Spotify playlist ID in the script.")
            print("\nTo get your playlist ID:")
            print("1. Right-click on a playlist in Spotify")
            print("2. Share -> Copy link to playlist")
            print("3. Extract the ID from the URL")
            sys.exit(1)
        
        # Run the updater
        updater = SpotifyUpdater()
        updater.run()


if __name__ == "__main__":
    main()