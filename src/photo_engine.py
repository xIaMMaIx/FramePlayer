"""
Photo Engine for Digital Photo Frame.
Asynchronously scans local directories for images (.jpg, .jpeg, .png, .webp),
maintains randomized playback queue, and generates fast blurred ambient backgrounds
with configurable blur radius.
"""

import base64
import io
import os
from pathlib import Path
import random
from typing import Dict, List, Optional
try:
    from PIL import Image, ImageFilter
except ImportError:
    Image = None
    ImageFilter = None

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
FALLBACK_SAMPLES_DIR = Path("assets/samples").resolve()


class PhotoEngine:
    def __init__(self, initial_folder: Optional[str] = None, shuffle: bool = True, blur_radius: int = 24):
        self.folder_path: Path = Path(initial_folder) if initial_folder else FALLBACK_SAMPLES_DIR
        self.shuffle_enabled: bool = shuffle
        self.blur_radius: int = blur_radius
        self.photo_paths: List[str] = []
        self._playlist: List[str] = []
        self._current_index: int = 0
        self._blur_cache: Dict[str, str] = {}  # cache_key -> base64 jpeg

        self.scan_folder(str(self.folder_path))

    def scan_folder(self, folder_path: str) -> int:
        """
        Scans target folder for supported image files.
        Falls back to assets/samples if folder is empty or invalid.
        """
        target = Path(folder_path).resolve()
        discovered: List[str] = []

        if target.exists() and target.is_dir():
            for root, _, files in os.walk(target):
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        full_p = os.path.join(root, f)
                        discovered.append(full_p)
            self.folder_path = target
        else:
            print(f"[PhotoEngine] Directory {folder_path} not found. Using fallback samples.")
            self.folder_path = FALLBACK_SAMPLES_DIR

        # If user folder has no photos, use sample wallpapers
        if not discovered and FALLBACK_SAMPLES_DIR.exists():
            for f in os.listdir(FALLBACK_SAMPLES_DIR):
                if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS:
                    discovered.append(str(FALLBACK_SAMPLES_DIR / f))

        self.photo_paths = discovered
        self._reset_playlist()
        return len(self.photo_paths)

    def _reset_playlist(self) -> None:
        """Regenerates the image playlist with optional shuffle."""
        if not self.photo_paths:
            self._playlist = []
            self._current_index = 0
            return

        self._playlist = list(self.photo_paths)
        if self.shuffle_enabled and len(self._playlist) > 1:
            random.shuffle(self._playlist)
        self._current_index = 0

    def set_shuffle(self, enabled: bool) -> None:
        """Toggles shuffle mode and rebuilds playlist."""
        self.shuffle_enabled = enabled
        self._reset_playlist()

    def set_blur_radius(self, radius: int) -> None:
        """Updates the background Gaussian blur radius."""
        self.blur_radius = max(1, min(60, radius))
        self._blur_cache.clear()

    def get_current_photo(self) -> Optional[str]:
        """Returns the current photo path."""
        if not self._playlist:
            return None
        return self._playlist[self._current_index % len(self._playlist)]

    def get_next_photo(self) -> Optional[str]:
        """Advances to next photo in playlist and returns its path."""
        if not self._playlist:
            return None
        self._current_index = (self._current_index + 1) % len(self._playlist)
        if self._current_index == 0 and self.shuffle_enabled and len(self._playlist) > 2:
            random.shuffle(self._playlist)
        return self._playlist[self._current_index]

    def get_previous_photo(self) -> Optional[str]:
        """Steps back to previous photo in playlist."""
        if not self._playlist:
            return None
        self._current_index = (self._current_index - 1) % len(self._playlist)
        return self._playlist[self._current_index]

    def get_blurred_background(self, photo_path: Optional[str], blur_radius: Optional[int] = None) -> Optional[str]:
        """
        Generates a fast Gaussian-blurred ambient background for the photo.
        Returns a base64 encoded JPEG string.
        """
        if not Image or not photo_path or not os.path.exists(photo_path):
            return None

        radius = blur_radius if blur_radius is not None else self.blur_radius
        cache_key = f"{photo_path}_{radius}"

        if cache_key in self._blur_cache:
            return self._blur_cache[cache_key]

        try:
            with Image.open(photo_path) as img:
                img = img.convert("RGB")
                # Downsample to 480x270 for ultra-fast, high-quality Gaussian blur
                bg = img.resize((480, 270), Image.Resampling.BILINEAR)
                blurred = bg.filter(ImageFilter.GaussianBlur(radius=radius))
                buf = io.BytesIO()
                blurred.save(buf, format="JPEG", quality=80)
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

                # Cache management (keep up to 100 items)
                if len(self._blur_cache) > 100:
                    self._blur_cache.clear()
                self._blur_cache[cache_key] = b64
                return b64
        except Exception as e:
            print(f"[PhotoEngine] Error generating blurred background for {photo_path}: {e}")
            return None

    @property
    def total_photos(self) -> int:
        return len(self.photo_paths)

    @property
    def current_index(self) -> int:
        return self._current_index + 1 if self._playlist else 0
