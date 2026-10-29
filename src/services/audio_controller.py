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

DEFAULT_AUDIO_PLACEHOLDER = "https://raw.githubusercontent.com/mdn/webaudio-examples/main/audio-analyser/viper.mp3"
REPEAT_MODES = ("off", "all", "one")


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
        self._is_playing = False
        self._is_loading_stream = False
        self._position_seconds = 0.0
        self._duration_seconds = 0.0
        self._shuffle = False
        self._repeat = "off"
        self._loaded_track_id: Optional[str] = None

        self.on_track_changed: Optional[Callable[[Track], None]] = None
        self.on_state_changed: Optional[Callable[[], None]] = None

        if self.audio:
            self.audio.on_state_change = self._on_flet_audio_state_change
            self.audio.on_position_change = self._on_flet_audio_position_change
            self.audio.on_duration_change = self._on_flet_audio_duration_change

    # --- Flet Audio events ---

    async def _safe_audio_call(self, coro, timeout: float = 12.0):
        """Awaits a Flet Audio RPC call with a timeout so it can't hang the UI."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"[AudioController] Flet audio operation timed out ({timeout}s).")
        except Exception as e:
            print(f"[AudioController] Flet audio operation note: {e}")

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
        missing = [t.id for t in tracks if t.id not in self._shuffle_ids]
        random.shuffle(missing)
        self._shuffle_ids = [i for i in self._shuffle_ids if i in by_id] + missing
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
        if self.audio:
            self._run_async(self._safe_audio_call(self.audio.seek(int(self._position_seconds * 1000))))
        self._notify_state()

    def toggle_shuffle(self) -> bool:
        self._shuffle = not self._shuffle
        self._shuffle_ids = [self._current.id] if self._shuffle and self._current else []
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
        self._is_loading_stream = True
        self._is_playing = False
        self.state.reset_idle()
        self._notify_track()

        print(f"[AudioController] Preparing audio for: '{track.title}' (ID: {track.id})...")
        stream_url = await self.ytmusic_service.get_stream_url_async(track.id)

        if self._current is not track:
            return  # Another song was picked while this one was loading
        self._is_loading_stream = False
        if not stream_url:
            print(f"[AudioController] Stream URL not found for '{track.title}'.")
            self._notify_state()
            return

        self._loaded_track_id = track.id
        if self.audio:
            self.audio.src = stream_url
            self.audio.volume = 1.0  # Loudness follows the device volume buttons
            try:
                self.audio.update()
            except Exception:
                pass
            await self._safe_audio_call(self.audio.play())
            self._is_playing = True
            print(f"[AudioController] Audio stream playing: '{track.title}'")
        self._notify_state()

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

    def _notify_track(self) -> None:
        if self.on_track_changed and self._current:
            try:
                self.on_track_changed(self._current)
            except Exception as e:
                print(f"[AudioController] Track callback note: {e}")
        self._notify_state()

    def _notify_state(self) -> None:
        if self.on_state_changed:
            try:
                self.on_state_changed()
            except Exception as e:
                print(f"[AudioController] State callback note: {e}")
