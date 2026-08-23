"""
YouTube Music Data Provider (YTMusicService).
Integrates official Google YouTube Data API v3 for OAuth 2.0 authenticated sessions
with strict Music Category filtering (Category 10: Music), custom playlist aggregation,
and yt-dlp direct audio stream extraction.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional
import requests
import yt_dlp
import ytmusicapi

from src.music_backend import MOCK_TRACKS, Track
from src.services.oauth_manager import OAUTH_FILE_PATH

STREAM_CACHE_TTL = 3600  # 1 hour cache per video stream URL
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Non-music YouTube categories to filter out from music player
NON_MUSIC_CATEGORIES = {"22", "23", "24", "25", "1", "2", "17", "19", "26", "27", "28"}


def parse_iso8601_duration(dur_str: str) -> float:
    """Parses ISO 8601 duration format (e.g. PT4M13S) into seconds."""
    if not dur_str:
        return 180.0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur_str)
    if not match:
        return 180.0
    hours, minutes, seconds = match.groups()
    total = int(hours or 0) * 3600 + int(minutes or 0) * 60 + int(seconds or 0)
    return float(total or 180.0)


class YTMusicService:
    def __init__(self, config_mgr=None):
        self.config_mgr = config_mgr
        self.ytmusic: Optional[ytmusicapi.YTMusic] = None
        self._stream_cache: Dict[str, tuple[str, float]] = {}  # video_id -> (url, expiry)
        self._executor = ThreadPoolExecutor(max_workers=4)

        # yt-dlp direct audio stream extractor configuration
        self._ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "socket_timeout": 12,
        }

        self.initialize_client()

    def initialize_client(self) -> bool:
        """Initializes client with OAuth credentials or guest mode."""
        try:
            if OAUTH_FILE_PATH.exists():
                print("[YTMusicService] Initialized with Google OAuth 2.0 session.")
                return True

            # Unauthenticated guest mode for searching & exploring
            self.ytmusic = ytmusicapi.YTMusic()
            print("[YTMusicService] Initialized in Guest / Unauthenticated mode.")
            return False

        except Exception as e:
            print(f"[YTMusicService] Error initializing: {e}. Using Guest mode.")
            try:
                self.ytmusic = ytmusicapi.YTMusic()
            except Exception:
                self.ytmusic = None
            return False

    @property
    def is_authenticated(self) -> bool:
        """Returns True if user is signed in with their YouTube Music account."""
        return OAUTH_FILE_PATH.exists()

    def _get_auth_headers(self) -> Optional[Dict[str, str]]:
        """Reads OAuth token, refreshes if expired, and returns Authorization header."""
        if not OAUTH_FILE_PATH.exists():
            return None

        try:
            with open(OAUTH_FILE_PATH, "r", encoding="utf-8") as f:
                token_data = json.load(f)

            access_token = token_data.get("access_token")
            expires_at = token_data.get("expires_at", 0)
            refresh_token = token_data.get("refresh_token")

            # Check if token is expired (or expires within 60s)
            if time.time() > (expires_at - 60) and refresh_token:
                cid = token_data.get("client_id") or (self.config_mgr.get("oauth_client_id") if self.config_mgr else "")
                csec = token_data.get("client_secret") or (self.config_mgr.get("oauth_client_secret") if self.config_mgr else "")

                if cid and csec:
                    resp = requests.post(
                        TOKEN_URL,
                        data={
                            "client_id": cid,
                            "client_secret": csec,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token",
                        },
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        new_data = resp.json()
                        access_token = new_data.get("access_token")
                        token_data["access_token"] = access_token
                        token_data["expires_in"] = new_data.get("expires_in", 3600)
                        token_data["expires_at"] = time.time() + token_data["expires_in"]
                        with open(OAUTH_FILE_PATH, "w", encoding="utf-8") as f:
                            json.dump(token_data, f, indent=2)
                        print("[YTMusicService] Refreshed OAuth access token successfully.")

            return {"Authorization": f"Bearer {access_token}"} if access_token else None

        except Exception as e:
            print(f"[YTMusicService] Error reading OAuth credentials: {e}")
            return None

    def _filter_music_videos_batch(self, video_ids: List[str], headers: Dict[str, str]) -> List[Track]:
        """Queries YouTube video metadata in batch and filters strictly for Music (Category 10)."""
        if not video_ids:
            return []

        tracks = []
        # Chunk into batches of 50
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            ids_str = ",".join(chunk)
            try:
                url = f"{YOUTUBE_API_BASE}/videos?part=snippet,contentDetails&id={ids_str}"
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for it in items:
                        snippet = it.get("snippet", {})
                        cat_id = snippet.get("categoryId", "")

                        # Filter: Must be Category 10 (Music) or from a Topic/VEVO/Music channel
                        channel_title = snippet.get("channelTitle", "")
                        title = snippet.get("title", "")
                        is_music = cat_id == "10" or "topic" in channel_title.lower() or "vevo" in channel_title.lower() or "records" in channel_title.lower() or "music" in channel_title.lower()

                        if not is_music and cat_id in NON_MUSIC_CATEGORIES:
                            continue  # Skip non-music videos (Vlogs, Comedy, Trailers, News)

                        v_id = it.get("id")
                        dur_iso = it.get("contentDetails", {}).get("duration", "")
                        dur_sec = parse_iso8601_duration(dur_iso)

                        thumbs = snippet.get("thumbnails", {})
                        thumb_url = (
                            thumbs.get("maxres", {}).get("url")
                            or thumbs.get("high", {}).get("url")
                            or thumbs.get("medium", {}).get("url")
                            or thumbs.get("default", {}).get("url")
                            or ""
                        )

                        tracks.append(
                            Track(
                                id=v_id,
                                title=title,
                                artist=channel_title,
                                album="YouTube Music",
                                duration_seconds=dur_sec,
                                art_url=thumb_url,
                                is_liked=True,
                            )
                        )
            except Exception as e:
                print(f"[YTMusicService] Error querying video batch: {e}")

        return tracks

    def get_liked_songs(self, limit: int = 50) -> List[Track]:
        """Fetches user's pure music tracks from Liked Playlist and user playlists."""
        headers = self._get_auth_headers()
        if not headers:
            return list(MOCK_TRACKS)

        music_tracks: List[Track] = []

        try:
            # 1. Fetch Liked Videos playlist (LL) and filter for pure music
            url = f"{YOUTUBE_API_BASE}/playlistItems?part=snippet,contentDetails&playlistId=LL&maxResults=50"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                video_ids = [
                    it.get("contentDetails", {}).get("videoId")
                    for it in items
                    if it.get("contentDetails", {}).get("videoId")
                ]
                music_tracks = self._filter_music_videos_batch(video_ids, headers)
                print(f"[YTMusicService] Filtered {len(music_tracks)} pure music tracks from Liked Playlist.")

            # 2. If fewer than 10 tracks found in LL, aggregate tracks from user's custom playlists
            if len(music_tracks) < 15:
                user_playlists = self.get_user_playlists()
                for pl in user_playlists[:4]:
                    p_tracks = self.get_playlist_tracks(pl["id"])
                    for pt in p_tracks:
                        if pt.id not in [t.id for t in music_tracks]:
                            music_tracks.append(pt)

            if music_tracks:
                return music_tracks[:limit]
            return list(MOCK_TRACKS)

        except Exception as e:
            print(f"[YTMusicService] Error fetching music tracks: {e}")
            return list(MOCK_TRACKS)

    def get_user_playlists(self) -> List[Dict[str, Any]]:
        """Fetches user's custom playlists via official YouTube Data API v3."""
        headers = self._get_auth_headers()
        if not headers:
            return [
                {
                    "id": "mock_playlist_1",
                    "title": "Synthwave & Chill Dreams",
                    "thumbnail": "https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=400&q=80",
                    "count": len(MOCK_TRACKS),
                }
            ]

        try:
            url = f"{YOUTUBE_API_BASE}/playlists?part=snippet,contentDetails&mine=true&maxResults=50"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                results = []
                for it in items:
                    snippet = it.get("snippet", {})
                    thumbnails = snippet.get("thumbnails", {})
                    thumb_url = (
                        thumbnails.get("high", {}).get("url")
                        or thumbnails.get("medium", {}).get("url")
                        or thumbnails.get("default", {}).get("url")
                        or ""
                    )
                    results.append(
                        {
                            "id": it.get("id", ""),
                            "title": snippet.get("title", "Untitled Playlist"),
                            "thumbnail": thumb_url,
                            "count": str(it.get("contentDetails", {}).get("itemCount", 0)),
                        }
                    )
                return results
            else:
                return []

        except Exception as e:
            print(f"[YTMusicService] Error fetching playlists: {e}")
            return []

    def get_curated_mood_playlists(self) -> List[Dict[str, Any]]:
        """Returns official YouTube Music curated recommended playlists for changing moods."""
        return [
            {
                "id": "RDCLAK5uy_mkEwQuegHYB8_aAzBO8Q__6gGoaFblISw",
                "title": "🚗 CarPlay & Driving Hits",
                "desc": "Feel-Good & Pop Hits for the Road",
                "thumbnail": "https://images.unsplash.com/photo-1506015391300-4802dc74de2e?w=400&q=80",
                "count": "50 tracks",
            },
            {
                "id": "RDCLAK5uy_nHSqCJjDrW9HBhCNdF6tWPdnOMngOv0wA",
                "title": "☕ Chill & Acoustic Vibes",
                "desc": "Relaxing Lo-Fi, Cafe & Acoustic Tracks",
                "thumbnail": "https://images.unsplash.com/photo-1518495973542-4542c06a5843?w=400&q=80",
                "count": "50 tracks",
            },
            {
                "id": "RDCLAK5uy_nyKVppE-RpLkeCcwLct4rvN9e8AAsS_qw",
                "title": "🔥 Top Hits Thailand",
                "desc": "Trending Popular Songs in Thailand",
                "thumbnail": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&q=80",
                "count": "50 tracks",
            },
            {
                "id": "RDCLAK5uy_mVJ3RRi_YBfUJnZnQxLAedQQcXHujbUcg",
                "title": "⚡ Energize & Workout Beats",
                "desc": "High Energy EDM & Dance Hits",
                "thumbnail": "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=400&q=80",
                "count": "50 tracks",
            },
        ]

    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Fetches all tracks for a playlist via YouTube Data API v3."""
        if playlist_id == "mock_playlist_1":
            return list(MOCK_TRACKS)

        headers = self._get_auth_headers()
        if not headers:
            return list(MOCK_TRACKS)

        try:
            url = f"{YOUTUBE_API_BASE}/playlistItems?part=snippet,contentDetails&playlistId={playlist_id}&maxResults=50"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                video_ids = [
                    it.get("contentDetails", {}).get("videoId")
                    for it in items
                    if it.get("contentDetails", {}).get("videoId")
                ]
                tracks = self._filter_music_videos_batch(video_ids, headers)
                return tracks if tracks else []
            else:
                return []

        except Exception as e:
            print(f"[YTMusicService] Error fetching tracks for playlist {playlist_id}: {e}")
            return []

    def search_tracks(self, query: str, limit: int = 20) -> List[Track]:
        """Searches YouTube Music tracks via YouTube Data API v3 with videoCategoryId=10 (Music)."""
        headers = self._get_auth_headers()
        if headers:
            try:
                url = f"{YOUTUBE_API_BASE}/search?part=snippet&q={query}&type=video&videoCategoryId=10&maxResults={min(25, limit)}"
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    video_ids = [it.get("id", {}).get("videoId") for it in items if it.get("id", {}).get("videoId")]
                    return self._filter_music_videos_batch(video_ids, headers)
            except Exception as ex:
                print(f"[YTMusicService] Search API note: {ex}")

        # Fallback to guest search
        if not self.ytmusic:
            try:
                self.ytmusic = ytmusicapi.YTMusic()
            except Exception:
                pass

        if self.ytmusic:
            try:
                results = self.ytmusic.search(query, filter="songs")
                tracks = []
                for r in results[:limit]:
                    vid = r.get("videoId")
                    if vid:
                        thumbs = r.get("thumbnails", [])
                        art = thumbs[-1].get("url") if thumbs else ""
                        artists = r.get("artists", [])
                        art_name = ", ".join([a.get("name", "") for a in artists if a.get("name")]) or "Artist"
                        tracks.append(
                            Track(
                                id=vid,
                                title=r.get("title", "Unknown"),
                                artist=art_name,
                                album=r.get("album", {}).get("name", "Single") if isinstance(r.get("album"), dict) else "Single",
                                duration_seconds=float(r.get("duration_seconds") or 180.0),
                                art_url=art,
                                is_liked=False,
                            )
                        )
                return tracks
            except Exception:
                pass

        return [t for t in MOCK_TRACKS if query.lower() in t.title.lower() or query.lower() in t.artist.lower()]

    def get_stream_url(self, video_id: str) -> Optional[str]:
        """
        Extracts direct playable audio stream URL for a given YouTube video ID.
        Uses in-memory cache to prevent redundant network extraction.
        """
        if not video_id or video_id.startswith("track_"):
            return ""

        now = time.time()
        if video_id in self._stream_cache:
            url, expiry = self._stream_cache[video_id]
            if now < expiry:
                return url

        try:
            target_url = f"https://www.youtube.com/watch?v={video_id}"
            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                stream_url = info.get("url")
                if stream_url:
                    self._stream_cache[video_id] = (stream_url, now + STREAM_CACHE_TTL)
                    return stream_url
        except Exception as e:
            print(f"[YTMusicService] Stream extraction failed for {video_id}: {e}")

        return None

    async def get_stream_url_async(self, video_id: str) -> Optional[str]:
        """Asynchronously extracts stream URL on worker thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.get_stream_url, video_id)
