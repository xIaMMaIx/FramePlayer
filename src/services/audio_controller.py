"""
Audio Playback Controller (AudioController).
Plays streams through the native Flet Audio control (Android). The saved playlist
is the play queue; the current song is tracked by object, so editing the playlist
(add, remove, reorder) never interrupts what is playing.
"""

import asyncio
import random
from typing import Any, Callable, List, Optional

from src.music_backend import Track
from src.services.local_playlist_manager import LocalPlaylistManager
from src.services.ytmusic_service import YTMusicService
from src.state import AppState

# flet_audio.Audio needs a source before the first song is picked. A bundled silent
# clip (assets/silence.wav) costs nothing, unlike a remote file fetched on every start.
DEFAULT_AUDIO_PLACEHOLDER = "silence.wav"
REPEAT_MODES = ("off", "all", "one")
PREFETCH_DELAY_SECONDS = 10.0  # How far into a song the next one's stream URL is looked up


def _parse_duration_to_seconds(val) -> float:
    """Safely converts Duration, timedelta, int, float, or None to seconds."""
    if val is None:
        return 0.0
    if hasattr(val, "in_milliseconds"):
        return float(val.in_milliseconds) / 1000.0
    if hasattr(val, "in_seconds"):
        return float(val.in_seconds)
    if hasattr(val, "total_seconds"):
        return float(val.total_seconds())
    if hasattr(val, "milliseconds"):
        return float(val.milliseconds) / 1000.0
    try:
        f = float(val)
        return f / 1000.0 if f > 10000 else f
    except (ValueError, TypeError):
        return 0.0


class AudioController:
    def __init__(
        self,
        state: AppState,
        ytmusic_service: YTMusicService,
        playlist: LocalPlaylistManager,
        audio_control: Optional[Any] = None,
        async_runner: Optional[Callable] = None,
    ):
        self.state = state
        self.ytmusic_service = ytmusic_service
        self.playlist = playlist
        self.audio = audio_control
        self.async_runner = async_runner

        self._current: Optional[Track] = playlist.tracks[0] if playlist.tracks else None
        self._last_index: int = 0  # Where to continue if the current song was removed
        self._shuffle_ids: List[str] = []
        self._shuffle_seen: set = set()
        self._prefetch_token = 0  # Bumped to supersede a pending next-song lookup
        self._is_playing = False
        self._is_loading_stream = False
        self._position_seconds = 0.0
        self._duration_seconds = 0.0
        self._shuffle = False
        self._repeat = "off"
        self._loaded_track_id: Optional[str] = None

        # Each listener is called once per change: new song, play/pause, seek,
        # shuffle/repeat or a playlist edit.
        self._listeners: List[Callable[[], None]] = []

        self._source_ready = asyncio.Event()  # Set when the player has buffered a new source

        if self.audio:
            self.audio.on_state_change = self._on_flet_audio_state_change
            self.audio.on_position_change = self._on_flet_audio_position_change
            self.audio.on_duration_change = self._on_flet_audio_duration_change
            self.audio.on_loaded = self._on_flet_audio_loaded

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    # --- Flet Audio events ---

    async def _safe_audio_call(self, coro, timeout: float = 12.0):
        """Awaits a Flet Audio RPC call with a timeout so it can't hang the UI."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[AudioController] Flet audio operation timed out ({timeout}s).")
        except Exception as e:
            print(f"[AudioController] Flet audio operation note: {e}")

    def _on_flet_audio_loaded(self, e) -> None:
        self._source_ready.set()

    def _on_flet_audio_state_change(self, e) -> None:
        if "completed" in str(getattr(e, "state", "")).lower():
            self._handle_track_completed()

    def _on_flet_audio_position_change(self, e) -> None:
        try:
            # AudioPositionChangeEvent.position is in milliseconds
            self._position_seconds = max(0.0, float(getattr(e, "position", 0)) / 1000.0)
        except (TypeError, ValueError):
            pass

    def _on_flet_audio_duration_change(self, e) -> None:
        secs = _parse_duration_to_seconds(getattr(e, "duration", None))
        if secs > 0:
            self._duration_seconds = secs

    # --- Read-only state ---

    @property
    def current_track(self) -> Optional[Track]:
        return self._current

    @property
    def queue(self) -> List[Track]:
        return self.playlist.tracks

    @property
    def is_current_saved(self) -> bool:
        return bool(self._current) and self.playlist.contains(self._current.id)

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def is_loading(self) -> bool:
        return self._is_loading_stream

    @property
    def position_seconds(self) -> float:
        return self._position_seconds

    @property
    def duration_seconds(self) -> float:
        if self._current and self._current.duration_seconds > 0:
            return self._current.duration_seconds
        return self._duration_seconds or 180.0

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat(self) -> str:
        return self._repeat

    # --- Queue order ---

    def _play_order(self) -> List[Track]:
        """Playlist order, or the shuffled order (new songs appended, removed ones dropped)."""
        tracks = self.playlist.tracks
        if not self._shuffle:
            return tracks
        by_id = {t.id: t for t in tracks}
        if by_id.keys() != self._shuffle_seen:  # Only when the playlist was edited
            missing = [i for i in by_id if i not in self._shuffle_seen]
            random.shuffle(missing)
            self._shuffle_ids = [i for i in self._shuffle_ids if i in by_id] + missing
            self._shuffle_seen = set(self._shuffle_ids)
        return [by_id[i] for i in self._shuffle_ids]

    def _step(self, delta: int) -> Optional[Track]:
        order = self._play_order()
        if not order:
            return None
        ids = [t.id for t in order]
        if self._current and self._current.id in ids:
            index = (ids.index(self._current.id) + delta) % len(order)
        else:
            # Current song was removed: the song that slid into its slot plays next
            index = (self._last_index if delta > 0 else self._last_index - 1) % len(order)
        return order[index]

    # --- Transport ---

    def _run_async(self, coro):
        if self.async_runner:
            return self.async_runner(coro)
        return asyncio.get_running_loop().create_task(coro)

    def play_track(self, track: Track) -> None:
        """Plays a track, adding it to the playlist first if it is not saved yet."""
        self.playlist.add(track)
        if self._current and self._current.id == track.id and self._is_playing:
            return
        self._start(track)

    def play_track_by_id(self, track_id: str) -> None:
        for track in self.playlist.tracks:
            if track.id == track_id:
                self.play_track(track)
                return

    def _start(self, track: Track) -> None:
        self._current = track
        self._position_seconds = 0.0
        ids = [t.id for t in self.playlist.tracks]
        if track.id in ids:
            self._last_index = ids.index(track.id)
        self._is_loading_stream = True
        self._is_playing = False
        self._prefetch_token += 1  # A pending lookup for the previous song's successor is moot
        self.state.reset_idle()
        self._notify_state()  # One UI refresh now, one more when the stream starts
        self._run_async(self._load_and_play_track(track))

    def play(self) -> None:
        if not self._current:
            if not self.playlist.tracks:
                return
            self._current = self.playlist.tracks[0]
        self.state.reset_idle()
        if self._loaded_track_id == self._current.id and self.audio:
            self._is_playing = True
            self._run_async(self._safe_audio_call(self.audio.resume()))
            self._schedule_prefetch()
            self._notify_state()
        else:
            self._start(self._current)

    def pause(self) -> None:
        self._is_playing = False
        if self.audio:
            self._run_async(self._safe_audio_call(self.audio.pause()))
        self._notify_state()

    def toggle_play(self) -> bool:
        self.pause() if self._is_playing else self.play()
        return self._is_playing

    def next_track(self) -> None:
        track = self._current if self._repeat == "one" else self._step(+1)
        if track:
            self._start(track)

    def prev_track(self) -> None:
        if self._position_seconds > 3.0:
            self.seek(0)
            return
        track = self._step(-1)
        if track:
            self._start(track)

    def seek(self, position_seconds: float) -> None:
        self._position_seconds = max(0.0, min(position_seconds, self.duration_seconds))
        # Not while a song is still loading: the native player would keep a seek issued
        # before it is ready and apply it to every following song as well.
        if self.audio and not self._is_loading_stream:
            self._run_async(self._safe_audio_call(self.audio.seek(int(self._position_seconds * 1000))))
        self._notify_state()

    def toggle_shuffle(self) -> bool:
        self._shuffle = not self._shuffle
        self._shuffle_ids = [self._current.id] if self._shuffle and self._current else []
        self._shuffle_seen = set(self._shuffle_ids)
        self._notify_state()
        return self._shuffle

    def cycle_repeat(self) -> str:
        self._repeat = REPEAT_MODES[(REPEAT_MODES.index(self._repeat) + 1) % len(REPEAT_MODES)]
        self._notify_state()
        return self._repeat

    def toggle_saved(self) -> bool:
        """Heart button: saves the current song to the playlist, or removes it."""
        if not self._current:
            return False
        if self.playlist.contains(self._current.id):
            self.playlist.remove(self._current.id)
        else:
            self.playlist.add(self._current)
        self._notify_state()
        return self.is_current_saved

    def remove_track(self, track_id: str) -> None:
        """Removes a song from the playlist; the current song keeps playing."""
        ids = [t.id for t in self.playlist.tracks]
        if track_id in ids and self._current and self._current.id == track_id:
            self._last_index = ids.index(track_id)
        self.playlist.remove(track_id)
        self._notify_state()

    def move_track(self, old_index: int, new_index: int) -> None:
        self.playlist.move(old_index, new_index)
        self._notify_state()

    async def _load_and_play_track(self, track: Track) -> None:
        """Resolves the audio stream and starts playback via native Flet Audio."""
        print(f"[AudioController] Preparing audio for: '{track.title}' (ID: {track.id})...")
        # Skipping quickly through songs queues one extraction per song on the single
        # worker; the ones already skipped past are dropped instead of resolved.
        stream_url = await self.ytmusic_service.get_stream_url_async(
            track.id, still_wanted=lambda: self._current is track
        )

        if self._current is not track:
            return  # Another song was picked while this one was loading
        if not stream_url:
            print(f"[AudioController] Stream URL not found for '{track.title}'.")
            self._is_loading_stream = False
            self._notify_state()
            return

        self._loaded_track_id = track.id
        if self.audio:
            self.audio.volume = 1.0  # Loudness follows the device volume buttons
            if self.audio.src != stream_url:
                # The native player buffers a new stream for several seconds on a slow
                # tablet; is_loading stays set until it reports the source as loaded.
                # resume() instead of play(): play() first seeks to 0, and a seek issued
                # before the stream is buffered makes Android re-buffer right after
                # playback starts (measured: up to 4 s more before any sound).
                self._source_ready.clear()
                self.audio.src = stream_url
                try:
                    self.audio.update()
                except Exception:
                    pass
                await self._safe_audio_call(self.audio.resume())  # Starts by itself once buffered
                await self._safe_audio_call(self._source_ready.wait())
                if self._current is track:
                    await self._safe_audio_call(self.audio.resume())  # In case it was paused meanwhile
            else:
                # Same stream as before (e.g. a one-song playlist on repeat): start it over
                try:
                    self.audio.update()
                except Exception:
                    pass
                await self._safe_audio_call(self.audio.play())
            if self._current is not track:
                return  # Another song was picked while the player was buffering
            self._is_playing = True
            print(f"[AudioController] Audio stream playing: '{track.title}'")
            self._schedule_prefetch()
        self._is_loading_stream = False
        self._notify_state()

    # --- Next-song prefetch ---

    def _upcoming_track(self) -> Optional[Track]:
        """The song that will start by itself when the current one ends, if any."""
        if not self._current or self._repeat == "one":
            return None
        order = self._play_order()
        if not order or (order[-1].id == self._current.id and self._repeat != "all"):
            return None  # End of the playlist: playback stops there
        upcoming = self._step(+1)
        return upcoming if upcoming and upcoming.id != self._current.id else None

    def _schedule_prefetch(self) -> None:
        """
        Looks up the next song's stream URL a little into the current one, so the change
        of song skips that lookup (seconds on a slow tablet). Any earlier request is
        superseded, which keeps quick skipping from queueing lookups nobody needs.
        """
        self._prefetch_token += 1
        self._run_async(self._prefetch_upcoming(self._prefetch_token))

    async def _prefetch_upcoming(self, token: int) -> None:
        await asyncio.sleep(PREFETCH_DELAY_SECONDS)

        def still_wanted() -> bool:
            return token == self._prefetch_token and self._is_playing

        upcoming = self._upcoming_track() if still_wanted() else None
        if upcoming is None or self.ytmusic_service.has_stream_url(upcoming.id):
            return
        if await self.ytmusic_service.get_stream_url_async(upcoming.id, still_wanted=still_wanted):
            print(f"[AudioController] Next song ready: '{upcoming.title}'")

    def _handle_track_completed(self) -> None:
        if self._repeat == "one":
            self.seek(0)
            if self.audio:
                self._run_async(self._safe_audio_call(self.audio.resume()))
            return
        order = self._play_order()
        is_last = bool(order) and self._current is not None and order[-1].id == self._current.id
        if self._repeat == "all" or not is_last:
            self.next_track()
        else:
            self._position_seconds = self.duration_seconds
            self.pause()

    def _notify_state(self) -> None:
        for callback in self._listeners:
            try:
                callback()
            except Exception as e:
                print(f"[AudioController] Listener note: {e}")
