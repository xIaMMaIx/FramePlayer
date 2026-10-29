"""
Configuration Manager for Frame Player Kiosk.
Handles reading, writing, and persistence of user preferences to config.json.
"""

import json
from pathlib import Path
from typing import Any, Dict

from src.storage import CONFIG_FILE_PATH

DEFAULT_CONFIG_PATH = CONFIG_FILE_PATH
DEFAULT_SAMPLE_FOLDER = Path("assets/samples").resolve()


class ConfigManager:
    DEFAULT_CONFIG: Dict[str, Any] = {
        "photo_folder": str(DEFAULT_SAMPLE_FOLDER),
        "idle_timeout_seconds": 60,
        "slideshow_interval_seconds": 8,
        "slideshow_shuffle": True,
        "volume": 0.75,
        "last_played_track_id": "",
        "repeat_mode": "off",  # off, all, one
        "shuffle_mode": False,
        "kiosk_fullscreen": True,
        "show_clock_on_photo_frame": True,
        "background_blur_radius": 24,
        "orientation": "landscape",  # "landscape" or "portrait"
    }

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Loads config from JSON file or initializes defaults if not present."""
        if not self.config_path.exists():
            self.config = dict(self.DEFAULT_CONFIG)
            self.save()
            return self.config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                self.config = {**self.DEFAULT_CONFIG, **loaded}
        except Exception as e:
            print(f"[ConfigManager] Error reading {self.config_path}: {e}. Resetting to defaults.")
            self.config = dict(self.DEFAULT_CONFIG)
            self.save()

        # Validate photo folder existence
        photo_dir = Path(self.config.get("photo_folder", ""))
        if not photo_dir.exists():
            self.config["photo_folder"] = str(DEFAULT_SAMPLE_FOLDER)
            self.save()

        return self.config

    def save(self) -> None:
        """Persists current configuration to JSON file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigManager] Error saving {self.config_path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieves a configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Sets a configuration value and optionally persists immediately."""
        self.config[key] = value
        if auto_save:
            self.save()

    def set_photo_folder(self, folder_path: str) -> bool:
        """Validates and updates the photo directory path."""
        p = Path(folder_path)
        if p.exists() and p.is_dir():
            self.config["photo_folder"] = str(p.resolve())
            self.save()
            return True
        return False
