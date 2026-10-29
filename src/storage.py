"""
Persistent Storage Directory Helper for Android and Desktop.
Ensures persistent, writable directories for config.json and local_playlist.json
across Windows, Linux, and Android APK environments.
"""

import os
from pathlib import Path
import tempfile


def get_app_data_dir() -> Path:
    """Returns persistent, writable storage directory for application JSON files."""
    if os.name != "nt":
        # Android / Linux environment
        env_path = os.environ.get("FLET_APP_STORAGE_DATA")
        candidates = []
        if env_path:
            candidates.append(Path(env_path))

        home = Path.home()
        candidates.append(home / ".frame_player")
        candidates.append(Path(tempfile.gettempdir()) / "frame_player_data")

        for c in candidates:
            try:
                c.mkdir(parents=True, exist_ok=True)
                test_f = c / ".test_write"
                test_f.touch()
                test_f.unlink()
                return c
            except Exception:
                continue

        fallback = Path(tempfile.gettempdir())
        return fallback

    return Path(".")


APP_DATA_DIR = get_app_data_dir()
CONFIG_FILE_PATH = APP_DATA_DIR / "config.json"
LOCAL_PLAYLIST_PATH = APP_DATA_DIR / "local_playlist.json"
