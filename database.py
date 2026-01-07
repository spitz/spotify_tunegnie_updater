"""SQLite database management for caching track searches and playlist contents."""

import sqlite3
import os
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime


class CacheDatabase:
    """Manages SQLite database for caching track searches and playlist contents."""

    def __init__(self, db_path: str = "cache.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Playlists table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,  -- 'daily' or 'cumulative'
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tracks table - stores both TuneGenie and Spotify track info
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    tunegenie_id TEXT PRIMARY KEY,  -- TuneGenie's unique track ID
                    tunegenie_artist TEXT NOT NULL,
                    tunegenie_title TEXT NOT NULL,
                    spotify_uri TEXT,
                    spotify_artist TEXT,
                    spotify_title TEXT,
                    spotify_album TEXT,
                    search_key TEXT,  -- normalized key for fallback searches
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Junction table for playlist-track relationships
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id TEXT,
                    tunegenie_id TEXT,
                    position INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (playlist_id, tunegenie_id),
                    FOREIGN KEY (playlist_id) REFERENCES playlists (id),
                    FOREIGN KEY (tunegenie_id) REFERENCES tracks (tunegenie_id)
                )
            """)

            # Create indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_search_key ON tracks (search_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_spotify_uri ON tracks (spotify_uri)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks (playlist_id)")

            conn.commit()

    def normalize_search_key(self, artist: str, title: str) -> str:
        """Create normalized search key for deduplication."""
        return f"{artist.lower().strip()}_{title.lower().strip()}"

    def add_or_update_playlist(self, playlist_id: str, name: str, playlist_type: str):
        """Add or update playlist information."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO playlists (id, name, type, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (playlist_id, name, playlist_type))
            conn.commit()

    def get_cached_track_search(self, tunegenie_id: str) -> Optional[str]:
        """Get cached Spotify URI for a TuneGenie track ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT spotify_uri FROM tracks
                WHERE tunegenie_id = ? AND spotify_uri IS NOT NULL
            """, (tunegenie_id,))
            result = cursor.fetchone()

            if result:
                # Update last_found timestamp
                cursor.execute("""
                    UPDATE tracks SET last_found = CURRENT_TIMESTAMP
                    WHERE tunegenie_id = ?
                """, (tunegenie_id,))
                conn.commit()
                return result[0]

            return None

    def cache_track_search(self, tunegenie_id: str, tunegenie_artist: str, tunegenie_title: str,
                          spotify_uri: Optional[str], spotify_artist: str = None,
                          spotify_title: str = None, spotify_album: str = None):
        """Cache the result of a track search."""
        search_key = self.normalize_search_key(tunegenie_artist, tunegenie_title)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO tracks
                (tunegenie_id, tunegenie_artist, tunegenie_title, spotify_uri, spotify_artist,
                 spotify_title, spotify_album, search_key, created_at, last_found)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (tunegenie_id, tunegenie_artist, tunegenie_title, spotify_uri, spotify_artist,
                  spotify_title, spotify_album, search_key))
            conn.commit()

    def get_playlist_tracks(self, playlist_id: str) -> Set[str]:
        """Get all track URIs for a playlist from cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.spotify_uri
                FROM tracks t
                JOIN playlist_tracks pt ON t.tunegenie_id = pt.tunegenie_id
                WHERE pt.playlist_id = ? AND t.spotify_uri IS NOT NULL
                ORDER BY pt.position
            """, (playlist_id,))
            return {row[0] for row in cursor.fetchall()}

    def update_playlist_tracks(self, playlist_id: str, spotify_track_uris: List[str]):
        """Update the cached tracks for a playlist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Clear existing playlist tracks
            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))

            # Add tracks that exist in our tracks table
            for position, uri in enumerate(spotify_track_uris):
                cursor.execute("""
                    INSERT OR IGNORE INTO playlist_tracks (playlist_id, tunegenie_id, position)
                    SELECT ?, tunegenie_id, ?
                    FROM tracks
                    WHERE spotify_uri = ?
                """, (playlist_id, position, uri))

            conn.commit()

    def update_playlist_tracks_with_timestamps(self, playlist_id: str, track_data: List[tuple]):
        """Update the cached tracks for a playlist with Spotify-provided timestamps."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Clear existing playlist tracks
            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))

            # Add tracks with Spotify-provided added_at timestamps
            for position, (uri, added_at) in enumerate(track_data):
                cursor.execute("""
                    INSERT OR IGNORE INTO playlist_tracks (playlist_id, tunegenie_id, position, added_at)
                    SELECT ?, tunegenie_id, ?, ?
                    FROM tracks
                    WHERE spotify_uri = ?
                """, (playlist_id, position, added_at, uri))

            conn.commit()

    def add_tracks_to_playlist_cache(self, playlist_id: str, tunegenie_ids: List[str]):
        """Add tracks to playlist cache by TuneGenie IDs (for cumulative playlist updates)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Get current max position
            cursor.execute("""
                SELECT COALESCE(MAX(position), -1)
                FROM playlist_tracks
                WHERE playlist_id = ?
            """, (playlist_id,))
            max_position = cursor.fetchone()[0]

            # Add new tracks
            for i, tunegenie_id in enumerate(tunegenie_ids):
                position = max_position + i + 1
                cursor.execute("""
                    INSERT OR IGNORE INTO playlist_tracks (playlist_id, tunegenie_id, position)
                    VALUES (?, ?, ?)
                """, (playlist_id, tunegenie_id, position))

            conn.commit()

    def get_track_by_uri(self, spotify_uri: str) -> Optional[Dict]:
        """Get track details by Spotify URI."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tunegenie_id, tunegenie_artist, tunegenie_title, spotify_uri,
                       spotify_artist, spotify_title, spotify_album
                FROM tracks
                WHERE spotify_uri = ?
            """, (spotify_uri,))
            result = cursor.fetchone()

            if result:
                return {
                    'tunegenie_id': result[0],
                    'tunegenie_artist': result[1],
                    'tunegenie_title': result[2],
                    'spotify_uri': result[3],
                    'spotify_artist': result[4],
                    'spotify_title': result[5],
                    'spotify_album': result[6]
                }
            return None

    def get_track_by_tunegenie_id(self, tunegenie_id: str) -> Optional[Dict]:
        """Get track details by TuneGenie ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT tunegenie_id, tunegenie_artist, tunegenie_title, spotify_uri,
                       spotify_artist, spotify_title, spotify_album
                FROM tracks
                WHERE tunegenie_id = ?
            """, (tunegenie_id,))
            result = cursor.fetchone()

            if result:
                return {
                    'tunegenie_id': result[0],
                    'tunegenie_artist': result[1],
                    'tunegenie_title': result[2],
                    'spotify_uri': result[3],
                    'spotify_artist': result[4],
                    'spotify_title': result[5],
                    'spotify_album': result[6]
                }
            return None

    def get_playlist_track_count(self, playlist_id: str) -> int:
        """Get the total number of tracks in a playlist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM playlist_tracks
                WHERE playlist_id = ?
            """, (playlist_id,))
            return cursor.fetchone()[0]

    def get_oldest_tracks_from_playlist(self, playlist_id: str, count: int) -> List[str]:
        """Get the oldest tracks from a playlist based on added_at timestamp."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.spotify_uri
                FROM playlist_tracks pt
                JOIN tracks t ON pt.tunegenie_id = t.tunegenie_id
                WHERE pt.playlist_id = ? AND t.spotify_uri IS NOT NULL
                ORDER BY pt.added_at ASC, pt.position ASC
                LIMIT ?
            """, (playlist_id, count))
            return [row[0] for row in cursor.fetchall()]

    def remove_tracks_from_playlist_cache(self, playlist_id: str, spotify_uris: List[str]):
        """Remove specific tracks from playlist cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for uri in spotify_uris:
                cursor.execute("""
                    DELETE FROM playlist_tracks
                    WHERE playlist_id = ? AND tunegenie_id IN (
                        SELECT tunegenie_id FROM tracks WHERE spotify_uri = ?
                    )
                """, (playlist_id, uri))
            conn.commit()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached data."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Count tracks with successful Spotify matches
            cursor.execute("SELECT COUNT(*) FROM tracks WHERE spotify_uri IS NOT NULL")
            successful_searches = cursor.fetchone()[0]

            # Count tracks with failed searches (no Spotify match)
            cursor.execute("SELECT COUNT(*) FROM tracks WHERE spotify_uri IS NULL")
            failed_searches = cursor.fetchone()[0]

            # Count playlists
            cursor.execute("SELECT COUNT(*) FROM playlists")
            playlist_count = cursor.fetchone()[0]

            # Count total playlist entries
            cursor.execute("SELECT COUNT(*) FROM playlist_tracks")
            playlist_track_count = cursor.fetchone()[0]

            return {
                'successful_searches': successful_searches,
                'failed_searches': failed_searches,
                'total_searches': successful_searches + failed_searches,
                'playlist_count': playlist_count,
                'playlist_track_count': playlist_track_count
            }

    def cleanup_old_data(self, days: int = 30):
        """Clean up old search results that haven't been found recently."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM tracks
                WHERE last_found < datetime('now', '-{} days')
                AND spotify_uri IS NULL
            """.format(days))
            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def get_tracks_needing_spotify_search(self, tunegenie_ids: List[str]) -> List[Dict]:
        """Get tracks that need Spotify search (not in cache or failed previous search)."""
        if not tunegenie_ids:
            return []

        placeholders = ','.join(['?' for _ in tunegenie_ids])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT tunegenie_id, tunegenie_artist, tunegenie_title
                FROM tracks
                WHERE tunegenie_id IN ({placeholders})
                AND spotify_uri IS NULL
            """, tunegenie_ids)

            failed_searches = {row[0]: {'tunegenie_id': row[0], 'tunegenie_artist': row[1], 'tunegenie_title': row[2]}
                             for row in cursor.fetchall()}

            # Return tracks that either aren't cached or have failed searches
            return [track for track_id, track in failed_searches.items()]