"""Spotify OAuth setup functionality for getting refresh tokens."""

import base64
import webbrowser
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict

import requests

from config import get_spotify_config, save_config, load_config, SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPE


class SpotifySetup:
    """Handle initial Spotify OAuth setup to get refresh token."""

    @staticmethod
    def get_auth_url() -> str:
        """Generate the Spotify authorization URL."""
        spotify_config = get_spotify_config()
        params = {
            "client_id": spotify_config['client_id'],
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
        spotify_config = get_spotify_config()
        token_url = "https://accounts.spotify.com/api/token"

        client_creds = f"{spotify_config['client_id']}:{spotify_config['client_secret']}"
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

        spotify_config = get_spotify_config()

        # Check if credentials are configured
        if "YOUR_" in spotify_config['client_id'] or "YOUR_" in spotify_config['client_secret']:
            print("\n⚠️  First, you need to configure your Spotify App credentials:")
            print("1. Go to https://developer.spotify.com/dashboard")
            print("2. Create a new app (or use existing)")
            print(f"3. Add EXACTLY this Redirect URI to your app settings:")
            print(f"   {SPOTIFY_REDIRECT_URI}")
            print("4. Update SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in config.json")
            print("\nAfter updating the credentials, run --setup again.")
            return

        print(f"\nClient ID: {spotify_config['client_id'][:20]}...")
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
                config = load_config()
                config['spotify']['refresh_token'] = refresh_token
                if save_config(config):
                    print(f"\n✓ Updated config.json with your refresh token")
                else:
                    print(f"\n⚠️  Could not update config.json")
                    print("Please update it manually with the refresh token shown above.")
            except Exception as e:
                print(f"\n⚠️  Could not update config.json: {e}")
                print("Please update it manually with the refresh token shown above.")
        else:
            print(f"\nPlease update the SPOTIFY_REFRESH_TOKEN in config.json with the value shown above.")

        # Also show playlist instruction
        print("\nTo get your playlist ID:")
        print("1. Right-click on a playlist in Spotify")
        print("2. Share -> Copy link to playlist")
        print("3. Extract the ID from the URL:")
        print("   https://open.spotify.com/playlist/[PLAYLIST_ID]?...")
        print(f"\nUpdate SPOTIFY_PLAYLIST_ID in config.json with your playlist ID.")
        print("\nOnce both values are updated, run the script without --setup to update your playlist.")