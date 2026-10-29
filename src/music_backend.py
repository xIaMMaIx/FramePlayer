"""
Track model shared by the playlist, search results and the player.
"""

from dataclasses import asdict, dataclass


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    duration_seconds: float
    art_url: str

    @property
    def formatted_duration(self) -> str:
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        """Builds a Track, ignoring keys older versions saved (audio_url, is_liked)."""
        return cls(
            id=data.get("id", ""),
            title=data.get("title", "Unknown"),
            artist=data.get("artist", "Unknown Artist"),
            album=data.get("album", ""),
            duration_seconds=float(data.get("duration_seconds") or 180.0),
            art_url=data.get("art_url", ""),
        )
