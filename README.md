# Radio Station Playlist Updater

Automatically update a Spotify playlist with songs played on WXRV (The River) radio station from the previous day.

## Features

- Fetches daily playlist data from TuneGenie API (WXRV radio station)
- Searches for each song on Spotify
- Clears and updates a Spotify playlist with unique tracks
- Handles duplicate songs automatically
- Configurable timezone support

## Prerequisites

- Python 3.6+ (for local installation) OR Docker (for containerized deployment)
- Spotify Developer Account
- Spotify playlist (public or private)
- For Synology: Synology NAS with DSM 7.0+ and Container Manager package installed

## Installation

### Option 1: Local Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/radio-playlist-updater.git
cd radio-playlist-updater
```

2. Install required packages:
```bash
pip install requests
```

3. Copy the configuration template:
```bash
cp config.json.template config.json
```

### Option 2: Docker Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/radio-playlist-updater.git
cd radio-playlist-updater
```

2. Copy the configuration template:
```bash
cp config.json.template config.json
```

3. Build the Docker image:
```bash
docker build -t radio-playlist .
```

4. Create a data directory for persistent storage:
```bash
mkdir data
```

## Configuration

### Step 1: Create a Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click "Create App"
3. Fill in the app details
4. Add exactly this Redirect URI: `https://oauth.pstmn.io/v1/callback`
5. Save your **Client ID** and **Client Secret**

### Step 2: Configure the Script

Edit `config.json` and add your Spotify Client ID and Client Secret:

```json
{
    "spotify": {
        "client_id": "your_actual_client_id_here",
        "client_secret": "your_actual_client_secret_here",
        ...
    }
}
```

### Step 3: Get Refresh Token

Run the setup process to authenticate with Spotify:

**Local installation:**
```bash
python main.py --setup
```

**Docker installation:**
```bash
docker run -it --rm \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/data:/app/data \
  radio-playlist python main.py --setup
```

This will:
1. Open your browser for Spotify authorization
2. Redirect to a page showing "You've been authenticated!"
3. Display your refresh token
4. Optionally update your config.json automatically

### Step 4: Add Playlist ID

1. Right-click on your target playlist in Spotify
2. Select "Share" → "Copy link to playlist"
3. Extract the ID from the URL: `https://open.spotify.com/playlist/[PLAYLIST_ID]`
4. Add it to your `config.json`

## Usage

### Manual Run

Run the script to update your playlist with yesterday's songs:

**Local installation:**
```bash
python main.py
```

**Docker installation:**
```bash
docker run --rm \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/data:/app/data \
  radio-playlist
```

**Docker Compose:**
```bash
docker-compose up radio-playlist
```

### Automated Daily Updates

#### Local Installation

**Linux/macOS (cron):**
```bash
# Edit crontab
crontab -e

# Add this line to run daily at 1 AM
0 1 * * * /usr/bin/python3 /path/to/main.py
```

**Windows (Task Scheduler):**
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily
4. Set action: Start a program
   - Program: `python.exe`
   - Arguments: `C:\path\to\main.py`

#### Docker Installation

**Using cron (Linux/macOS):**
```bash
# Add to crontab to run daily at 6 AM
0 6 * * * cd /path/to/radio-playlist && docker-compose up radio-playlist
```

#### Synology NAS Deployment (DS925+ / Container Manager)

The image is built for you by GitHub Actions on every push to `main` and
attached to the workflow run as a downloadable artifact. You don't need
Docker installed locally — everything below is configured through the
Synology DSM UI, with credentials supplied as environment variables (no
`config.json` on the NAS).

##### 1. Download the image artifact from GitHub

1. In the repo, open **Actions** → **Build Docker Image**.
2. Click the most recent successful run on `main`.
3. Under **Artifacts**, download `radio-playlist-image-<sha>.zip`.
4. Unzip it locally — you'll get `radio-playlist.tar`.

##### 2. Get a Spotify refresh token (one-time, on your computer)

The Synology container is non-interactive, so the OAuth flow has to run
once on a desktop with a browser:

```bash
git clone https://github.com/yourusername/spotify_tunegnie_updater.git
cd spotify_tunegnie_updater
pip install -r requirements.txt
cp config.json.template config.json
# edit config.json: fill in client_id and client_secret only
python main.py --setup
```

Copy the **refresh token** that's printed at the end. You'll paste it
into the Synology UI as `SPOTIFY_REFRESH_TOKEN` in step 4. You can
discard the local `config.json` afterward.

##### 3. Import the image into Container Manager

1. Copy `radio-playlist.tar` to the NAS (File Station, SMB, or SCP).
2. Open **Container Manager** in DSM.
3. **Image** → **Add** → **Add From File** → pick `radio-playlist.tar`.
4. Wait for the import to finish; you should see `radio-playlist:latest`
   in the Image list.

##### 4. Create the container (configure entirely in the UI)

1. **Image** tab → select `radio-playlist:latest` → **Run**.
2. **General Settings**:
   - Container name: `radio-playlist-updater`
   - Enable auto-restart: **off** (the container is one-shot — it runs,
     updates the playlist, then exits).
3. **Advanced Settings** → **Volume** → **Add Folder**:
   - Mount path in container: `/app/data`
   - Source: a folder on the NAS you create for this purpose, e.g.
     `/docker/radio-playlist/data`. This is where `cache.db` lives so
     Spotify search results persist between runs.
4. **Advanced Settings** → **Environment**: click **+** and add the
   following variables. The first four are required; the rest are
   optional with sensible defaults.

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `SPOTIFY_CLIENT_ID` | yes | From the Spotify Developer Dashboard. |
   | `SPOTIFY_CLIENT_SECRET` | yes | From the Spotify Developer Dashboard. |
   | `SPOTIFY_REFRESH_TOKEN` | yes | From step 2 above. |
   | `SPOTIFY_DAILY_PLAYLIST_ID` | yes | Playlist that gets replaced daily. |
   | `SPOTIFY_CUMULATIVE_PLAYLIST_ID` | no | Optional growing playlist. Omit to disable. |
   | `SPOTIFY_MAX_CUMULATIVE_TRACKS` | no | Default `9000`. |
   | `TUNEGENIE_API_ID` | no | Default `m2g_bar`. |
   | `TUNEGENIE_BRAND` | no | Default `wxrv` (WXRV / The River). |
   | `TUNEGENIE_TIMEZONE_OFFSET` | no | Default `-04:00`. |
   | `PYTHONUNBUFFERED` | no | Set to `1` so logs stream live in the UI. |

5. **Execution Command**: leave blank — the image's default `CMD`
   (`python main.py`) is correct.
6. Click **Next** → **Done**. The container will start once and exit;
   that first run is your smoke test. Open **Container** → click the
   container → **Logs** to confirm it printed `✓ Found N songs from
   TuneGenie` and updated the playlist. (If it errors with "missing
   required config 'X'", you forgot env var `X` — edit the container,
   add it, and rerun.)

##### 5. Schedule it via Synology Task Scheduler

1. **Control Panel** → **Task Scheduler** → **Create** →
   **Scheduled Task** → **User-defined script**.
2. **General**:
   - Task: `Run radio-playlist-updater`
   - User: `root` (Task Scheduler needs root to control Docker.)
   - Enabled: checked.
3. **Schedule**:
   - Date: Daily.
   - First run time: pick a time after the radio station's "yesterday"
     window has closed for your timezone — e.g. **02:00**.
   - Frequency: Run every day.
4. **Task Settings** → **Run command**:
   ```bash
   docker start -a radio-playlist-updater
   ```
   `-a` attaches stdout/stderr so the output is captured in the Task
   Scheduler run log, and the task's exit code reflects the container's
   exit code (so a failed run shows up as a failed task).
5. (Optional, recommended) **Task Settings** → **Notification**:
   check **Send run details by email** and supply your email so a
   non-zero exit (e.g., another TuneGenie 403, or expired credentials)
   reaches you instead of dying silently.
6. **OK** to save. Right-click the task → **Run** to test it
   immediately. Then **Action** → **View Result** to see logs.

##### Updating to a newer image

When you push a change to `main` and want to roll it out:

1. Download the new artifact (step 1).
2. Container Manager → **Image** → **Add** → **Add From File** → pick
   the new `radio-playlist.tar`. The new tag (`radio-playlist:<sha>`)
   imports alongside `:latest`, which is overwritten in place.
3. Container Manager → **Container** → select `radio-playlist-updater`
   → **Action** → **Reset**. Synology recreates the container from the
   updated `:latest` image, preserving your env vars and volume mount.
4. The next scheduled run picks up the new code.

#### GitHub Actions Deployment

For automated deployment using GitHub Actions (recommended for cloud-based hosting):

1. **Fork or Clone this Repository** to your GitHub account

2. **Configure GitHub Secrets:**
   - Go to your repository's Settings → Secrets and variables → Actions
   - Click "New repository secret" and add each of the following:

   | Secret Name | Description | How to Get |
   |-------------|-------------|------------|
   | `SPOTIFY_CLIENT_ID` | Your Spotify app client ID | From [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
   | `SPOTIFY_CLIENT_SECRET` | Your Spotify app client secret | From [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
   | `SPOTIFY_REFRESH_TOKEN` | Your Spotify refresh token | Run `python main.py --setup` locally first |
   | `SPOTIFY_DAILY_PLAYLIST_ID` | Your target playlist ID | Right-click playlist → Share → Copy link, extract ID |
   | `SPOTIFY_CUMULATIVE_PLAYLIST_ID` | (Optional) Cumulative playlist ID | Same as above, or leave as "YOUR_CUMULATIVE_SPOTIFY_PLAYLIST_ID" |

3. **Get Your Refresh Token:**

   You'll need to run the setup process locally first to get your refresh token:
   ```bash
   # Clone the repo locally
   git clone https://github.com/yourusername/spotify_tunegnie_updater.git
   cd spotify_tunegnie_updater

   # Install dependencies
   pip install -r requirements.txt

   # Create config from template
   cp config.json.template config.json

   # Edit config.json with your client_id and client_secret
   # Then run setup
   python main.py --setup
   ```

   Copy the refresh token from the output and add it to your GitHub secrets.

4. **Workflow Schedule:**

   The GitHub Action is configured to run daily at 2 AM UTC. To change the schedule:
   - Edit `.github/workflows/daily-update.yml`
   - Modify the cron expression under `schedule:`
   ```yaml
   schedule:
     - cron: '0 2 * * *'  # Daily at 2 AM UTC
   ```

5. **Manual Trigger:**

   You can also trigger the workflow manually:
   - Go to Actions tab in your repository
   - Select "Daily Spotify Playlist Update"
   - Click "Run workflow"

6. **Monitor Runs:**

   - View workflow runs in the Actions tab
   - Check logs for any errors
   - Failed runs will upload error logs as artifacts

**Benefits of GitHub Actions:**
- Free for public repositories
- No server maintenance required
- Automatic error logging
- Easy schedule configuration
- Runs in the cloud (no local infrastructure needed)
- Persistent SQLite cache reduces API calls and improves performance

**Cache Persistence:**
The workflow uses GitHub Actions cache to persist the SQLite database (`cache.db`) between runs. This cache stores:
- Previously searched tracks and their Spotify URIs
- Track metadata from both TuneGenie and Spotify
- Playlist history

This means:
- First run: All tracks need to be searched on Spotify (slower)
- Subsequent runs: Only new tracks are searched (much faster)
- Cache is shared across all workflow runs for your repository
- No manual cache management required

**Note on Cache Limits:**
- GitHub Actions cache has a 10GB limit per repository
- The SQLite cache file is typically very small (< 1MB for thousands of tracks)
- Old cache entries are automatically cleaned up by the application

## Configuration Options

### Timezone

The default timezone is Eastern Time (-04:00). To change it, edit the `timezone_offset` in `config.json`:

```json
"timezone_offset": "-05:00"  // For EST or CDT
```

### Radio Station

To use a different station (if supported by TuneGenie), modify:

```json
"tunegenie": {
    "brand": "your_station_code"
}
```

## Troubleshooting

### Songs Not Found

Some songs might not be found on Spotify due to:
- Different artist name formatting
- Different song title formatting
- Regional availability restrictions
- Songs not available on Spotify

The script will show which songs couldn't be found and continue with the rest.

### Token Expired

If you get authentication errors, run the setup process again:

**Local installation:**
```bash
python main.py --setup
```

**Docker installation:**
```bash
docker run -it --rm \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/data:/app/data \
  radio-playlist python main.py --setup
```

## Security Notes

- **Never commit `config.json`** to Git (it's in `.gitignore`)
- Keep your Client Secret secure
- The refresh token doesn't expire but can be revoked from your Spotify account

## License

MIT

## Contributing

Pull requests are welcome! For major changes, please open an issue first.

## Acknowledgments

- Uses [TuneGenie API](https://api.tunegenie.com) for radio station data
- Built with [Spotify Web API](https://developer.spotify.com/documentation/web-api)