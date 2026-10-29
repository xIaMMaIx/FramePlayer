"""
Saved playlist (local_playlist.json).
This one list is also the play queue: playing a search result adds it here,
and the heart button adds or removes the current song.
"""

import json
import os
from pathlib import Path
from typing import List

from src.music_backend import Track
from src.storage import LOCAL_PLAYLIST_PATH

# Only used when the playlist file has never been created
STARTER_TRACKS = [
    Track(
        id="UZM-tISUD2A",
        title="[Electro] ZABO - Drown",
        artist="Buried Sound",
        album="Local Favorites",
        duration_seconds=218.0,
        art_url="https://i.ytimg.com/vi/UZM-tISUD2A/hqdefault.jpg",
    ),
    Track(
        id="tIGNjVfvKtI",
        title="NAY x TangBadVoice - ‘ยกมือขึ้น’ Another Version",
        artist="gnest_official",
        album="Local Favorites",
        duration_seconds=184.0,
        art_url="https://i.ytimg.com/vi/tIGNjVfvKtI/hqdefault.jpg",
    ),
]


class LocalPlaylistManager:
    def __init__(self, file_path: Path = LOCAL_PLAYLIST_PATH):
        self.file_path = file_path
        self.tracks: List[Track] = self._load()

    def _load(self) -> List[Track]:
        if not self.file_path.exists():
            self.tracks = list(STARTER_TRACKS)
            self._save()
            return self.tracks
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [Track.from_dict(t) for t in data if isinstance(t, dict) and t.get("id")]
        except Exception as e:
            print(f"[Playlist] Error loading {self.file_path}: {e}")
            return []

    def _save(self) -> None:
        tmp = self.file_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump([t.to_dict() for t in self.tracks], f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.file_path)
        except Exception as e:
            print(f"[Playlist] Error saving {self.file_path}: {e}")

    def contains(self, track_id: str) -> bool:
        return any(t.id == track_id for t in self.tracks)

    def add(self, track: Track) -> bool:
        """Appends the track unless it is already saved. Returns True if added."""
        if self.contains(track.id):
            return False
        self.tracks.append(track)
        self._save()
        return True

    def remove(self, track_id: str) -> bool:
        before = len(self.tracks)
        self.tracks = [t for t in self.tracks if t.id != track_id]
        if len(self.tracks) == before:
            return False
        self._save()
        return True

    def move(self, old_index: int, new_index: int) -> bool:
        if not (0 <= old_index < len(self.tracks) and 0 <= new_index < len(self.tracks)):
            return False
        self.tracks.insert(new_index, self.tracks.pop(old_index))
        self._save()
        return True
