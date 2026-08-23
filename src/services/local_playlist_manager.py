"""
Local Playlist Manager (LocalPlaylistManager).
Handles persistence, retrieval, addition, and removal of tracks in local storage (local_playlist.json).
Provides the primary curated queue for the CarPlay dashboard with zero network startup delay.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.music_backend import Track

LOCAL_PLAYLIST_PATH = Path("local_playlist.json")

# Initial recommended tracks if newly initialized
DEFAULT_INITIAL_TRACKS = [
    {
        "id": "UZM-tISUD2A",
        "title": "[Electro] ZABO - Drown",
        "artist": "Buried Sound",
        "album": "Local Favorites",
        "duration_seconds": 218.0,
        "art_url": "https://i.ytimg.com/vi/UZM-tISUD2A/hqdefault.jpg",
        "is_liked": True,
    },
    {
        "id": "tIGNjVfvKtI",
        "title": "NAY x TangBadVoice - ‘ยกมือขึ้น’ Another Version",
        "artist": "gnest_official",
        "album": "Local Favorites",
        "duration_seconds": 184.0,
        "art_url": "https://i.ytimg.com/vi/tIGNjVfvKtI/hqdefault.jpg",
        "is_liked": True,
    },
]


class LocalPlaylistManager:
    def __init__(self, file_path: Path = LOCAL_PLAYLIST_PATH):
        self.file_path = file_path
        self._tracks: List[Track] = []
        self.load()

    def load(self) -> List[Track]:
        """Loads tracks from local_playlist.json or seeds defaults."""
        if not self.file_path.exists():
            self._tracks = [Track.from_dict(t) for t in DEFAULT_INITIAL_TRACKS]
            self.save()
            return self._tracks

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    self._tracks = [Track.from_dict(t) for t in data]
                else:
                    self._tracks = [Track.from_dict(t) for t in DEFAULT_INITIAL_TRACKS]
                    self.save()
        except Exception as e:
            print(f"[LocalPlaylistManager] Error loading {self.file_path}: {e}")
            self._tracks = [Track.from_dict(t) for t in DEFAULT_INITIAL_TRACKS]

        return self._tracks

    def save(self) -> bool:
        """Persists current tracks list to local_playlist.json."""
        try:
            data = [t.to_dict() for t in self._tracks]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[LocalPlaylistManager] Saved {len(self._tracks)} tracks to {self.file_path}")
            return True
        except Exception as e:
            print(f"[LocalPlaylistManager] Error saving {self.file_path}: {e}")
            return False

    def get_tracks(self) -> List[Track]:
        """Returns list of all tracks in the local playlist."""
        return list(self._tracks)

    def add_track(self, track: Track) -> bool:
        """Adds a track to the local playlist if not already present."""
        if self.has_track(track.id):
            print(f"[LocalPlaylistManager] Track '{track.title}' is already in the playlist.")
            return False

        self._tracks.append(track)
        self.save()
        print(f"[LocalPlaylistManager] Added track: '{track.title}'")
        return True

    def remove_track(self, track_id: str) -> bool:
        """Removes a track by ID from the local playlist."""
        initial_len = len(self._tracks)
        self._tracks = [t for t in self._tracks if t.id != track_id]
        if len(self._tracks) < initial_len:
            self.save()
            print(f"[LocalPlaylistManager] Removed track ID: {track_id}")
            return True
        return False

    def has_track(self, track_id: str) -> bool:
        """Checks if a track ID already exists in the playlist."""
        return any(t.id == track_id for t in self._tracks)

    def count(self) -> int:
        return len(self._tracks)
