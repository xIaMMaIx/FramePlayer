"""
Track model shared by the playlist, search results and the player.
"""

from dataclasses import asdict, dataclass
import re

COVER_SIZE = 720  # Sharp on tablets; about 2 MB once decoded
THUMB_SIZE = 120
_GOOGLE_IMAGE_SIZE = re.compile(r"=(?:w\d+-h\d+|s\d+)")
_YTIMG_LARGE = re.compile(r"/(?:maxres|sd|hq)default\.")


def _resize_art(url: str, size: int) -> str:
    """Google image URLs serve any size; search results only list a 120px one."""
    return _GOOGLE_IMAGE_SIZE.sub(f"=w{size}-h{size}", url, count=1)


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

    @property
    def cover_url(self) -> str:
        return _resize_art(self.art_url, COVER_SIZE)

    @property
    def thumb_url(self) -> str:
        # i.ytimg.com: mqdefault is 320x180, plenty for a 44px list thumbnail
        return _YTIMG_LARGE.sub("/mqdefault.", _resize_art(self.art_url, THUMB_SIZE), count=1)

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
