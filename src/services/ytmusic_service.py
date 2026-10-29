"""
YouTube Music Data Provider (YTMusicService).
Works fully without login: searches via ytmusicapi guest mode and extracts
audio-only streams with yt-dlp using a client that needs no account, PO token or JS runtime.
"""

import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from typing import List, Optional

from src.music_backend import MOCK_TRACKS, Track

DEFAULT_PLACEHOLDER = "https://raw.githubusercontent.com/mdn/webaudio-examples/main/audio-analyser/viper.mp3"
STREAM_CACHE_TTL = 3600  # YouTube stream URLs stay valid for several hours
STREAM_CACHE_MAX = 20

# Audio-only AAC (140) first; 360p muxed (18) only as last resort.
# "visionos" is the yt-dlp default client that works logged-out without a JS runtime
# (important on Android, where deno/node are unavailable); "android_vr" is the fallback.
YDL_OPTS = {
    "format": "140/bestaudio[ext=m4a]/bestaudio/18",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 12,
    "cachedir": False,
    "extractor_args": {"youtube": {"player_client": ["visionos", "android_vr"]}},
}


class YTMusicService:
    def __init__(self, config_mgr=None):
        self.config_mgr = config_mgr
        self._ytmusic = None  # Created lazily on first search to keep startup light
        self._ydl = None
        self._ydl_lock = threading.Lock()
        self._stream_cache: "OrderedDict[str, tuple[str, float]]" = OrderedDict()
        self._executor = ThreadPoolExecutor(max_workers=1)

    def _get_ytmusic(self):
        if self._ytmusic is None:
            import ytmusicapi

            self._ytmusic = ytmusicapi.YTMusic()
        return self._ytmusic

    def search_tracks(self, query: str, limit: int = 20) -> List[Track]:
        """Searches YouTube Music songs in guest mode (no login, no API quota)."""
        try:
            results = self._get_ytmusic().search(query, filter="songs", limit=limit)
        except Exception as e:
            print(f"[YTMusicService] Guest search failed: {e}")
            q = query.lower()
            return [t for t in MOCK_TRACKS if q in t.title.lower() or q in t.artist.lower()]

        tracks = []
        for r in results[:limit]:
            vid = r.get("videoId")
            if not vid:
                continue
            thumbs = r.get("thumbnails") or []
            artists = r.get("artists") or []
            album = r.get("album")
            tracks.append(
                Track(
                    id=vid,
                    title=r.get("title", "Unknown"),
                    artist=", ".join(a["name"] for a in artists if a.get("name")) or "Artist",
                    album=album.get("name", "Single") if isinstance(album, dict) else "Single",
                    duration_seconds=float(r.get("duration_seconds") or 180.0),
                    art_url=thumbs[-1].get("url", "") if thumbs else "",
                )
            )
        return tracks

    def get_stream_url(self, video_id: str) -> Optional[str]:
        """Extracts a direct audio stream URL for a YouTube video ID (cached, no login)."""
        if not video_id or video_id.startswith("track_"):
            return DEFAULT_PLACEHOLDER

        now = time.time()
        cached = self._stream_cache.get(video_id)
        if cached and now < cached[1]:
            self._stream_cache.move_to_end(video_id)
            return cached[0]

        try:
            with self._ydl_lock:
                if self._ydl is None:
                    import yt_dlp

                    self._ydl = yt_dlp.YoutubeDL(YDL_OPTS)
                info = self._ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            stream_url = info.get("url")
        except Exception as e:
            print(f"[YTMusicService] Stream extraction failed for {video_id}: {e}")
            return None

        if stream_url:
            self._stream_cache[video_id] = (stream_url, now + STREAM_CACHE_TTL)
            while len(self._stream_cache) > STREAM_CACHE_MAX:
                self._stream_cache.popitem(last=False)
        return stream_url

    async def get_stream_url_async(self, video_id: str) -> Optional[str]:
        """Extracts the stream URL on the single worker thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.get_stream_url, video_id)
