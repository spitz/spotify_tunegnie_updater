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

#### Synology NAS Deployment

For automated deployment on Synology NAS using Container Manager:

1. **Build Container on Local Workstation:**
   ```bash
   # On your local machine (Mac/PC)
   docker build -t radio-playlist .
   docker save radio-playlist > radio-playlist.tar
   ```

2. **Transfer Image to Synology:**
   - Copy the `radio-playlist.tar` file to your Synology NAS (via File Station, SCP, or shared folder)
   - Also copy your configured `config.json` and create a `data` directory on the NAS

3. **Import Container Image:**
   - Open **Container Manager** in DSM
   - Go to **Image** → **Add** → **Add from file**
   - Select the `radio-playlist.tar` file
   - Wait for import to complete

4. **Create Container:**
   - Go to **Container** → **Create**
   - Select the `radio-playlist` image
   - **Volume Settings:**
     - Mount your `config.json` file to `/app/config.json` (read-only)
     - Mount your data folder to `/app/data` (read-write)
   - **Environment:** Set `PYTHONUNBUFFERED=1`
   - **Auto-restart:** Disabled (we'll run it on schedule)

5. **Schedule Daily Runs:**
   - Go to **Control Panel** → **Task Scheduler**
   - Create **Triggered Task** → **User-defined script**
   - Set schedule (e.g., daily at 6 AM)
   - Script content:
     ```bash
     docker start radio-playlist && docker wait radio-playlist
     ```

6. **Alternative: Using Docker Compose on Synology:**
   - Copy your `docker-compose.yml` to the NAS
   - In Container Manager, go to **Project** → **Create**
   - Upload your `docker-compose.yml` file
   - Ensure volume paths point to your NAS directories
   - Schedule with Task Scheduler:
     ```bash
     cd /volume1/docker/radio-playlist
     docker-compose up radio-playlist
     ```

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