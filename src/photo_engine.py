"""
Photo Engine for Digital Photo Frame.
Asynchronously scans local directories for images (.jpg, .jpeg, .png, .webp),
maintains randomized playback queue, and encodes downscaled photos for display
(the ambient background blur is done on the GPU by Flutter).
"""

import base64
from collections import OrderedDict
import io
import os
from pathlib import Path
import random
from typing import List, Optional
try:
    from PIL import Image
except ImportError:
    Image = None

# Low-RAM tuning: a 1280px RGBA texture is ~3.7MB vs ~8MB at 1920px,
# and only the current/next photos need to stay encoded.
MAX_PHOTO_EDGE = 1280
PHOTO_CACHE_SIZE = 4

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".mkv"}
FALLBACK_SAMPLES_DIR = Path("assets/samples").resolve()

DEFAULT_SAMPLE_WALLPAPERS = [
    "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1920&q=85",
    "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1920&q=85",
    "https://images.unsplash.com/photo-1518791841217-8f162f1e1131?w=1920&q=85",
    "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=1920&q=85",
    "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1920&q=85",
]


def resolve_android_folder_path(folder_path: str) -> str:
    """Converts Android SAF Content URIs or URI-encoded paths to absolute storage paths."""
    if not folder_path:
        return ""

    import urllib.parse
    decoded = urllib.parse.unquote(folder_path)

    # Handle Android SAF content URI: content://com.android.externalstorage.documents/tree/primary%3APictures%2FSG
    if "primary:" in decoded:
        rel_path = decoded.split("primary:")[-1].lstrip("/\\")
        for base in ["/storage/emulated/0", "/sdcard"]:
            cand = os.path.join(base, rel_path)
            if os.path.exists(cand):
                return cand
        return os.path.join("/storage/emulated/0", rel_path)

    if "raw:" in decoded:
        raw_path = decoded.split("raw:")[-1]
        if os.path.exists(raw_path):
            return raw_path

    if os.path.exists(decoded):
        return decoded

    # Try common android storage root prefixes
    for prefix in ["/storage/emulated/0", "/sdcard", "/storage/emulated/0/Pictures", "/storage/emulated/0/DCIM"]:
        clean_name = os.path.basename(decoded.rstrip("/\\"))
        cand = os.path.join(prefix, clean_name)
        if os.path.exists(cand):
            return cand

    return decoded


class PhotoEngine:

    def is_video(self, file_path: str) -> bool:
        if not file_path: return False
        return file_path.lower().endswith((".mp4", ".webm", ".mkv"))

    def __init__(self, initial_folder: Optional[str] = None, shuffle: bool = True, blur_radius: int = 24):
        self.folder_path: Path = Path(initial_folder) if initial_folder else FALLBACK_SAMPLES_DIR
        self.shuffle_enabled: bool = shuffle
        self.blur_radius: int = blur_radius
        self.photo_paths: List[str] = []
        self._playlist: List[str] = []
        self._current_index: int = 0
        self._src_cache: "OrderedDict[str, str]" = OrderedDict()  # photo path -> base64 jpeg

        self.scan_folder(str(self.folder_path))

    def scan_folder(self, folder_path: str) -> int:
        """
        Scans target folder for supported image files on Android and Desktop.
        Resolves Android SAF URIs and scoped storage paths automatically.
        """
        resolved = resolve_android_folder_path(folder_path)
        print(f"[PhotoEngine] Scanning folder: '{folder_path}' -> Resolved path: '{resolved}'")
        target = Path(resolved)
        discovered: List[str] = []

        if target.exists():
            if target.is_dir():
                for root, _, files in os.walk(str(target)):
                    for f in files:
                        ext = os.path.splitext(f)[1].lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            discovered.append(os.path.join(root, f))
            elif target.suffix.lower() in SUPPORTED_EXTENSIONS:
                discovered.append(str(target))
            self.folder_path = target
        else:
            # Try searching in standard Android picture directories if folder name matches
            clean_name = target.name
            for common_dir in ["/storage/emulated/0/Pictures", "/storage/emulated/0/DCIM", "/sdcard/Pictures", "/sdcard/DCIM"]:
                cand_dir = Path(common_dir) / clean_name
                if cand_dir.exists() and cand_dir.is_dir():
                    for root, _, files in os.walk(str(cand_dir)):
                        for f in files:
                            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                                discovered.append(os.path.join(root, f))
                    if discovered:
                        self.folder_path = cand_dir
                        break

        # If user folder has no photos, check assets/samples directory
        if not discovered and FALLBACK_SAMPLES_DIR.exists():
            try:
                for f in os.listdir(FALLBACK_SAMPLES_DIR):
                    if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                        discovered.append(str(FALLBACK_SAMPLES_DIR / f))
            except Exception as e:
                print(f"[PhotoEngine] Note checking samples dir: {e}")

        # If still no photos (e.g. on clean Android APK install), do not inject wallpapers automatically.
        # Let it report 0 photos so the user knows they need to grant Android Storage permissions.
        pass

        self.photo_paths = discovered
        self._reset_playlist()
        print(f"[PhotoEngine] Discovered {len(self.photo_paths)} photos.")
        return len(self.photo_paths)

    def set_custom_photos(self, photo_list: List[str]) -> int:
        """Sets custom photo paths directly (e.g. from FilePicker multi-file selection)."""
        valid_photos = [p for p in photo_list if p and (p.startswith("http") or os.path.exists(p))]
        if valid_photos:
            self.photo_paths = valid_photos
            self._reset_playlist()
            print(f"[PhotoEngine] Loaded {len(self.photo_paths)} custom photos directly.")
            return len(self.photo_paths)
        return len(self.photo_paths)

    def _reset_playlist(self) -> None:
        """Regenerates the image playlist with optional shuffle."""
        if not self.photo_paths:
            self._playlist = list(DEFAULT_SAMPLE_WALLPAPERS)
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

    def get_photo_src(self, photo_path: Optional[str]) -> Optional[str]:
        """
        Returns renderable image source for ft.Image:
        - For remote URLs, returns the URL.
        - For local files on Android/Desktop, returns base64 data string to ensure 100% reliable rendering.
        """
        if not photo_path:
            return None

        if photo_path.startswith("http://") or photo_path.startswith("https://") or photo_path.startswith("data:image"):
            return photo_path

        if not os.path.exists(photo_path):
            return None

        if self.is_video(photo_path):
            return photo_path

        cached = self._src_cache.get(photo_path)
        if cached:
            self._src_cache.move_to_end(photo_path)
            return cached

        try:
            if Image:
                with Image.open(photo_path) as img:
                    # draft() lets the JPEG decoder downscale while decoding, avoiding a full-size bitmap
                    img.draft("RGB", (MAX_PHOTO_EDGE, MAX_PHOTO_EDGE))
                    img = img.convert("RGB")
                    img.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE), Image.Resampling.BILINEAR)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
                self._src_cache[photo_path] = b64
                while len(self._src_cache) > PHOTO_CACHE_SIZE:
                    self._src_cache.popitem(last=False)
                return b64
            else:
                with open(photo_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                    return f"data:image/jpeg;base64,{data}"
        except Exception as e:
            print(f"[PhotoEngine] Error encoding photo {photo_path}: {e}")
            return None

    @property
    def total_photos(self) -> int:
        return len(self.photo_paths)

    @property
    def current_index(self) -> int:
        return self._current_index + 1 if self._playlist else 0
