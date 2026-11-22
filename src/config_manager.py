"""
Configuration Manager for Frame Player Kiosk.
All settings and their defaults live in the `Settings` dataclass; config.json only
ever contains these keys and is rewritten atomically, and only when a value changes.
"""

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
from typing import Any

from src.storage import CONFIG_FILE_PATH, SAMPLE_PHOTOS_DIR

DEFAULT_SAMPLE_FOLDER = SAMPLE_PHOTOS_DIR


@dataclass
class Settings:
    photo_folder: str = str(DEFAULT_SAMPLE_FOLDER)
    idle_timeout_seconds: int = 60  # 0 = screensaver off
    slideshow_interval_seconds: int = 10
    slideshow_shuffle: bool = True
    photo_fill_mode: str = "contain"  # "contain" or "cover"


_KEYS = {f.name for f in fields(Settings)}


class ConfigManager:
    def __init__(self, config_path: Path = CONFIG_FILE_PATH):
        self.config_path = config_path
        self.settings = self._load()

    def _load(self) -> Settings:
        """Reads config.json, ignoring unknown keys and values of the wrong type."""
        settings = Settings()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except Exception as e:
            print(f"[ConfigManager] Error reading {self.config_path}: {e}. Using defaults.")
            data = {}

        for key, value in data.items() if isinstance(data, dict) else ():
            default = getattr(settings, key, None)
            if key not in _KEYS:
                continue
            if isinstance(default, float) and isinstance(value, (int, float)):
                value = float(value)
            if isinstance(value, type(default)):
                setattr(settings, key, value)

        if not Path(settings.photo_folder).exists():
            settings.photo_folder = str(DEFAULT_SAMPLE_FOLDER)
        self._write(settings)  # Drops stale keys left by older versions
        return settings

    def _write(self, settings: Settings) -> None:
        tmp = self.config_path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(settings), f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.config_path)
        except Exception as e:
            print(f"[ConfigManager] Error saving {self.config_path}: {e}")

    def get(self, key: str) -> Any:
        return getattr(self.settings, key)

    def set(self, key: str, value: Any) -> None:
        """Updates one setting and saves, skipping the write if nothing changed."""
        if key not in _KEYS:
            raise KeyError(key)
        if getattr(self.settings, key) != value:
            setattr(self.settings, key, value)
            self._write(self.settings)

    def set_photo_folder(self, folder_path: str) -> bool:
        p = Path(folder_path)
        if p.is_dir():
            self.set("photo_folder", str(p.resolve()))
            return True
        return False
