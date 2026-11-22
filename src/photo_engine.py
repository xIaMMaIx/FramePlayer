"""
Photo Engine for Digital Photo Frame.
Scans local directories for images and videos, keeps the (optionally shuffled)
slideshow order and prepares each photo for display as a `Slide`: a downscaled JPEG
plus a tiny pre-blurred copy used as the ambient backdrop.

Nothing here runs at startup: the folder is scanned and photos are decoded only when
the UI asks, and both are meant to be called from a worker thread (see PhotoFrameView).
"""

from collections import OrderedDict
from dataclasses import dataclass
import io
import os
from pathlib import Path
import random
import threading
from typing import List, Optional, Union

from src.storage import SAMPLE_PHOTOS_DIR

# Low-RAM tuning: a 1280px RGBA texture is ~3.7MB vs ~8MB at 1920px,
# and only the current and the pre-loaded next photo need to stay encoded.
MAX_PHOTO_EDGE = 1280
PHOTO_CACHE_SIZE = 3

# The backdrop is a thumbnail that Flutter stretches over the screen: scaling ~96px up
# to full screen is itself a heavy blur, so no blur filter has to run on the GPU.
BACKDROP_EDGE = 96
BACKDROP_BLUR_RADIUS = 1.8

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".mkv"}
FALLBACK_SAMPLES_DIR = SAMPLE_PHOTOS_DIR

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


@dataclass(frozen=True)
class Slide:
    """One slideshow item, ready to hand to Flet."""

    src: Union[str, bytes]  # JPEG bytes, a remote image URL or a video file path
    backdrop: Optional[bytes] = None  # Tiny pre-blurred PNG shown behind a letterboxed photo
    is_video: bool = False


class PhotoEngine:

    def is_video(self, file_path: str) -> bool:
        if not file_path: return False
        return file_path.lower().endswith((".mp4", ".webm", ".mkv"))

    def __init__(self, initial_folder: Optional[str] = None, shuffle: bool = True):
        """Remembers the folder only; call scan_folder() to look for photos."""
        self.folder_path: Path = Path(initial_folder) if initial_folder else FALLBACK_SAMPLES_DIR
        self.shuffle_enabled: bool = shuffle
        self.photo_paths: List[str] = []
        self._playlist: List[str] = []
        self._current_index: int = 0
        self._slide_cache: "OrderedDict[str, Slide]" = OrderedDict()
        self._decode_lock = threading.Lock()  # One decode at a time; a second caller finds the cache

    def scan_folder(self, folder_path: str) -> int:
        """
        Scans target folder for supported image files on Android and Desktop.
        Resolves Android SAF URIs and scoped storage paths automatically.
        Walking a large folder is slow, so call this from a worker thread.
        """
        resolved = resolve_android_folder_path(folder_path)
        print(f"[PhotoEngine] Scanning folder: '{folder_path}' -> Resolved path: '{resolved}'")
        target = Path(resolved)
        discovered: List[str] = []
        scanned_folder: Optional[Path] = None

        if target.exists():
            if target.is_dir():
                for root, _, files in os.walk(str(target)):
                    for f in files:
                        ext = os.path.splitext(f)[1].lower()
                        if ext in SUPPORTED_EXTENSIONS:
                            discovered.append(os.path.join(root, f))
            elif target.suffix.lower() in SUPPORTED_EXTENSIONS:
                discovered.append(str(target))
            scanned_folder = target
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
                        scanned_folder = cand_dir
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

        # Publish the result only now, so the slideshow never sees a half-scanned folder
        if scanned_folder is not None:
            self.folder_path = scanned_folder
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
        playlist = list(self.photo_paths) or list(DEFAULT_SAMPLE_WALLPAPERS)
        if self.photo_paths and self.shuffle_enabled and len(playlist) > 1:
            random.shuffle(playlist)
        self._playlist = playlist
        self._current_index = 0

    def set_shuffle(self, enabled: bool) -> None:
        """Toggles shuffle mode and rebuilds playlist."""
        self.shuffle_enabled = enabled
        self._reset_playlist()

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

    def peek_next_photo(self) -> Optional[str]:
        """The photo get_next_photo() will most likely return, without advancing (used to pre-load it)."""
        if not self._playlist:
            return None
        return self._playlist[(self._current_index + 1) % len(self._playlist)]

    def get_previous_photo(self) -> Optional[str]:
        """Steps back to previous photo in playlist."""
        if not self._playlist:
            return None
        self._current_index = (self._current_index - 1) % len(self._playlist)
        return self._playlist[self._current_index]

    def load_slide(self, photo_path: Optional[str]) -> Optional[Slide]:
        """
        Prepares a photo for display. Decoding and re-encoding a camera photo takes a
        while, so call this from a worker thread; the most recent results are cached.
        Remote URLs and videos are passed through for Flutter to load itself.
        """
        if not photo_path:
            return None

        if photo_path.startswith(("http://", "https://")):
            return Slide(src=photo_path)

        if not os.path.exists(photo_path):
            return None

        if self.is_video(photo_path):
            return Slide(src=photo_path, is_video=True)

        with self._decode_lock:
            cached = self._slide_cache.get(photo_path)
            if cached:
                self._slide_cache.move_to_end(photo_path)
                return cached

            try:
                slide = self._encode(photo_path)
            except Exception as e:
                print(f"[PhotoEngine] Error encoding photo {photo_path}: {e}")
                return None

            self._slide_cache[photo_path] = slide
            while len(self._slide_cache) > PHOTO_CACHE_SIZE:
                self._slide_cache.popitem(last=False)
            return slide

    @staticmethod
    def _encode(photo_path: str) -> Slide:
        try:
            from PIL import Image, ImageFilter, ImageOps  # Imported on first use to keep startup light
        except ImportError:
            with open(photo_path, "rb") as f:
                return Slide(src=f.read())

        with Image.open(photo_path) as img:
            # draft() lets the JPEG decoder downscale while decoding, avoiding a full-size bitmap
            img.draft("RGB", (MAX_PHOTO_EDGE, MAX_PHOTO_EDGE))
            img = img.convert("RGB")
            img.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE), Image.Resampling.BILINEAR)
            # Phones store portrait shots sideways plus an EXIF "rotate" tag. The tag is not
            # written to the re-encoded JPEG, so turn the pixels upright here (on the
            # already-downscaled image, where it is cheap).
            ImageOps.exif_transpose(img, in_place=True)
            photo = io.BytesIO()
            img.save(photo, format="JPEG", quality=85)

            img.thumbnail((BACKDROP_EDGE, BACKDROP_EDGE), Image.Resampling.BILINEAR)
            backdrop = io.BytesIO()
            # Lossless: stretched ~13x, even faint JPEG blocks show as blotches in dark
            # areas (seen on a real tablet). At this size a PNG is only a few KB.
            img.filter(ImageFilter.GaussianBlur(BACKDROP_BLUR_RADIUS)).save(backdrop, format="PNG")
        return Slide(src=photo.getvalue(), backdrop=backdrop.getvalue())

    @property
    def total_photos(self) -> int:
        return len(self.photo_paths)

    @property
    def current_index(self) -> int:
        return self._current_index + 1 if self._playlist else 0
