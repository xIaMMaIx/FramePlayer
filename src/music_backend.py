"""
Music Backend Architecture & Audio Pipeline.
Provides the Track model, the BaseMusicBackend interface and a small offline demo catalog.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


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
