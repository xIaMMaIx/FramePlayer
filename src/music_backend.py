"""
Music Backend Architecture & Audio Pipeline.
Provides BaseMusicBackend abstract interface, MockMusicBackend with realistic
playback simulation and rich curated tracks, and pluggable YTMusicBackend structure.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import random
import time
from typing import Callable, List, Optional


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    duration_seconds: float
    art_url: str
    audio_url: str = ""
    is_liked: bool = False

    @property
    def formatted_duration(self) -> str:
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_seconds": self.duration_seconds,
            "art_url": self.art_url,
            "audio_url": self.audio_url,
            "is_liked": self.is_liked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", "Unknown"),
            artist=data.get("artist", "Unknown Artist"),
            album=data.get("album", "Album"),
            duration_seconds=float(data.get("duration_seconds", 180.0)),
            art_url=data.get("art_url", ""),
            audio_url=data.get("audio_url", ""),
            is_liked=bool(data.get("is_liked", False)),
        )


# Curated high-aesthetic mock catalog with fast CDN album art
MOCK_TRACKS = [
    Track(
        id="track_1",
        title="Midnight City Lights",
        artist="Neon Odyssey",
        album="Synthwave Dreams Vol. 2",
        duration_seconds=234,  # 03:54
        art_url="https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=600&auto=format&fit=crop&q=80",
        audio_url="",
    ),
    Track(
        id="track_2",
        title="Chasing Horizons",
        artist="Aura & The Wanderers",
        album="Solitude in Bloom",
        duration_seconds=268,  # 04:28
        art_url="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=600&auto=format&fit=crop&q=80",
        audio_url="",
    ),
    Track(
        id="track_3",
        title="Deep Space Resonance",
        artist="Cosmic Echoes",
        album="Interstellar Drift",
        duration_seconds=312,  # 05:12
        art_url="https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop&q=80",
        audio_url="",
    ),
    Track(
        id="track_4",
        title="Sunset Drive (Lo-Fi Chill)",
        artist="Coffee & Vinyl",
        album="Late Night Study Session",
        duration_seconds=185,  # 03:05
        art_url="https://images.unsplash.com/photo-1518609878373-06d740f60d8b?w=600&auto=format&fit=crop&q=80",
        audio_url="",
    ),
    Track(
        id="track_5",
        title="Electric Horizon",
        artist="Cyber Pulse",
        album="Neon Metropolis",
        duration_seconds=210,  # 03:30
        art_url="https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=600&auto=format&fit=crop&q=80",
        audio_url="",
    ),
    Track(
        id="track_6",
        title="Autumn Rain Whisper",
        artist="Acoustic Haven",
        album="Woodland Melodies",
        duration_seconds=245,  # 04:05
        art_url="https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=600&auto=format&fit=crop&q=80",
        audio_url="",
    ),
]


class BaseMusicBackend(ABC):
    """Abstract interface defining required music player functionality."""

    @abstractmethod
    def play(self) -> None:
        pass

    @abstractmethod
    def pause(self) -> None:
        pass

    @abstractmethod
    def toggle_play(self) -> bool:
        pass

    @abstractmethod
    def next_track(self) -> Optional[Track]:
        pass

    @abstractmethod
    def prev_track(self) -> Optional[Track]:
        pass

    @abstractmethod
    def seek(self, position_seconds: float) -> None:
        pass

    @abstractmethod
    def set_volume(self, volume: float) -> None:
        pass

    @abstractmethod
    def toggle_shuffle(self) -> bool:
        pass

    @abstractmethod
    def cycle_repeat(self) -> str:
        pass

    @abstractmethod
    def play_track_by_id(self, track_id: str) -> Optional[Track]:
        pass

    @property
    @abstractmethod
    def current_track(self) -> Optional[Track]:
        pass

    @property
    @abstractmethod
    def is_playing(self) -> bool:
        pass

    @property
    @abstractmethod
    def queue(self) -> List[Track]:
        pass


class MockMusicBackend(BaseMusicBackend):
    """
    Complete standalone music backend simulating YouTube Music / streaming playback.
    Operates seamlessly without network credentials for testing and instant kiosk demo.
    """

    def __init__(self, tracks: Optional[List[Track]] = None):
        self._catalog: List[Track] = tracks or list(MOCK_TRACKS)
        self._queue: List[Track] = list(self._catalog)
        self._current_index: int = 0
        self._is_playing: bool = False
        self._position_seconds: float = 0.0
        self._volume: float = 0.75
        self._shuffle: bool = False
        self._repeat: str = "off"  # "off", "all", "one"
        self._last_tick_time: float = time.time()

        # Listeners for playback events
        self.on_track_changed: Optional[Callable[[Track], None]] = None
        self.on_state_changed: Optional[Callable[[], None]] = None

    @property
    def current_track(self) -> Optional[Track]:
        if 0 <= self._current_index < len(self._queue):
            return self._queue[self._current_index]
        return None

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def queue(self) -> List[Track]:
        return self._queue

    @property
    def position_seconds(self) -> float:
        return self._position_seconds

    @property
    def duration_seconds(self) -> float:
        curr = self.current_track
        return curr.duration_seconds if curr else 0.0

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> str:
        return self._repeat

    def play(self) -> None:
        if not self._is_playing:
            self._is_playing = True
            self._last_tick_time = time.time()
            self._notify_state()

    def pause(self) -> None:
        if self._is_playing:
            self._is_playing = False
            self._notify_state()

    def toggle_play(self) -> bool:
        if self._is_playing:
            self.pause()
        else:
            self.play()
        return self._is_playing

    def next_track(self) -> Optional[Track]:
        if not self._queue:
            return None

        if self._repeat == "one":
            self._position_seconds = 0.0
        else:
            self._current_index = (self._current_index + 1) % len(self._queue)
            self._position_seconds = 0.0

        self._last_tick_time = time.time()
        self._notify_track()
        return self.current_track

    def prev_track(self) -> Optional[Track]:
        if not self._queue:
            return None

        # If played more than 3 seconds, rewind to start of current track
        if self._position_seconds > 3.0:
            self._position_seconds = 0.0
        else:
            self._current_index = (self._current_index - 1) % len(self._queue)
            self._position_seconds = 0.0

        self._last_tick_time = time.time()
        self._notify_track()
        return self.current_track

    def play_track_by_id(self, track_id: str) -> Optional[Track]:
        for idx, track in enumerate(self._queue):
            if track.id == track_id:
                self._current_index = idx
                self._position_seconds = 0.0
                self._is_playing = True
                self._last_tick_time = time.time()
                self._notify_track()
                return track
        return None

    def seek(self, position_seconds: float) -> None:
        curr = self.current_track
        max_dur = curr.duration_seconds if curr else 0.0
        self._position_seconds = max(0.0, min(position_seconds, max_dur))
        self._last_tick_time = time.time()
        self._notify_state()

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        self._notify_state()

    def toggle_shuffle(self) -> bool:
        self._shuffle = not self._shuffle
        current = self.current_track
        if self._shuffle:
            shuffled = list(self._catalog)
            random.shuffle(shuffled)
            if current and current in shuffled:
                shuffled.remove(current)
                shuffled.insert(0, current)
            self._queue = shuffled
            self._current_index = 0
        else:
            self._queue = list(self._catalog)
            if current:
                self._current_index = self._queue.index(current) if current in self._queue else 0
        self._notify_state()
        return self._shuffle

    def cycle_repeat(self) -> str:
        modes = ["off", "all", "one"]
        curr_idx = modes.index(self._repeat) if self._repeat in modes else 0
        self._repeat = modes[(curr_idx + 1) % len(modes)]
        self._notify_state()
        return self._repeat

    def toggle_like(self) -> bool:
        curr = self.current_track
        if curr:
            curr.is_liked = not curr.is_liked
            self._notify_state()
            return curr.is_liked
        return False

    def tick_playback(self) -> None:
        """Called every second by the background progress tracker to update timestamp."""
        if not self._is_playing:
            return

        now = time.time()
        elapsed = now - self._last_tick_time
        self._last_tick_time = now
        self._position_seconds += elapsed

        curr = self.current_track
        if curr and self._position_seconds >= curr.duration_seconds:
            if self._repeat == "one":
                self._position_seconds = 0.0
            elif self._repeat == "all" or self._current_index < len(self._queue) - 1:
                self.next_track()
            else:
                # End of playlist in repeat-off mode
                self._position_seconds = curr.duration_seconds
                self.pause()

    def _notify_track(self) -> None:
        if self.on_track_changed and self.current_track:
            self.on_track_changed(self.current_track)
        self._notify_state()

    def _notify_state(self) -> None:
        if self.on_state_changed:
            self.on_state_changed()


class YTMusicBackend(BaseMusicBackend):
    """
    YouTube Music Backend integration using ytmusicapi.
    Provides scaffolding to search, authenticate, extract stream metadata,
    and populate queues from user playlists.
    """

    def __init__(self, auth_path: Optional[str] = None):
        self.auth_path = auth_path
        self._ytmusic = None
        self._init_client()
        self._mock_fallback = MockMusicBackend()

    def _init_client(self) -> None:
        try:
            import ytmusicapi
            if self.auth_path and os.path.exists(self.auth_path):
                self._ytmusic = ytmusicapi.YTMusic(self.auth_path)
            else:
                self._ytmusic = ytmusicapi.YTMusic()
            print("[YTMusicBackend] Initialized ytmusicapi successfully.")
        except Exception as e:
            print(f"[YTMusicBackend] Could not initialize ytmusicapi ({e}). Operating in Mock mode.")
            self._ytmusic = None

    def search_and_enqueue(self, query: str) -> List[Track]:
        """Searches YouTube Music for tracks and enqueues them."""
        if not self._ytmusic:
            return self._mock_fallback.queue

        try:
            results = self._ytmusic.search(query, filter="songs")
            parsed_tracks = []
            for r in results[:10]:
                duration_str = r.get("duration", "0:00")
                parts = duration_str.split(":")
                dur = int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 180
                art = r.get("thumbnails", [{}])[-1].get("url", "")
                artist = r.get("artists", [{}])[0].get("name", "Unknown Artist")
                parsed_tracks.append(
                    Track(
                        id=r.get("videoId", str(time.time())),
                        title=r.get("title", "Unknown Title"),
                        artist=artist,
                        album=r.get("album", {}).get("name", "YouTube Music"),
                        duration_seconds=dur,
                        art_url=art,
                    )
                )
            if parsed_tracks:
                self._mock_fallback._catalog = parsed_tracks
                self._mock_fallback._queue = parsed_tracks
                self._mock_fallback._current_index = 0
            return parsed_tracks
        except Exception as e:
            print(f"[YTMusicBackend] Search failed: {e}")
            return self._mock_fallback.queue

    # Delegate audio transport control to fallback player
    def play(self) -> None:
        self._mock_fallback.play()

    def pause(self) -> None:
        self._mock_fallback.pause()

    def toggle_play(self) -> bool:
        return self._mock_fallback.toggle_play()

    def next_track(self) -> Optional[Track]:
        return self._mock_fallback.next_track()

    def prev_track(self) -> Optional[Track]:
        return self._mock_fallback.prev_track()

    def seek(self, position_seconds: float) -> None:
        self._mock_fallback.seek(position_seconds)

    def set_volume(self, volume: float) -> None:
        self._mock_fallback.set_volume(volume)

    def toggle_shuffle(self) -> bool:
        return self._mock_fallback.toggle_shuffle()

    def cycle_repeat(self) -> str:
        return self._mock_fallback.cycle_repeat()

    def play_track_by_id(self, track_id: str) -> Optional[Track]:
        return self._mock_fallback.play_track_by_id(track_id)

    @property
    def current_track(self) -> Optional[Track]:
        return self._mock_fallback.current_track

    @property
    def is_playing(self) -> bool:
        return self._mock_fallback.is_playing

    @property
    def queue(self) -> List[Track]:
        return self._mock_fallback.queue
