"""
Theme, Color Palette, and Touch Design Constants.
Tailored for Apple CarPlay & Android Auto aesthetic on landscape touch screens.
"""

import flet as ft

# 1x1 Transparent PNG Base64 to prevent "Image must have either src or src_base64 specified" error
TRANSPARENT_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

# Color Palette
BG_DARK = "#0D0E12"
SURFACE_DARK = "#16181F"
SURFACE_CARD = "#1D212B"
SURFACE_ELEVATED = "#252B38"
SURFACE_TRANSLUCENT = "rgba(255, 255, 255, 0.08)"
SURFACE_GLASS_BORDER = "rgba(255, 255, 255, 0.12)"

ACCENT_RED = "#FF0033"  # YouTube Music Primary Red
ACCENT_CYAN = "#3EA6FF"  # CarPlay secondary blue/cyan
ACCENT_GREEN = "#10B981"  # Active / Play green

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A6B2"
TEXT_MUTED = "#656C7A"

# Touch Sizing & Spacing
BORDER_RADIUS_CARD = 18
BORDER_RADIUS_BUTTON = 14
BORDER_RADIUS_ROUND = 40

# List thumbnails are drawn at 40-44px; decoding them at 3x that keeps each bitmap
# around 90 KB in memory instead of the ~700 KB a full 480x360 YouTube still needs.
THUMB_CACHE_HEIGHT = 132

DEFAULT_ART_URL = "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=600&auto=format&fit=crop&q=80"


def glass_card(
    content: ft.Control,
    padding: int = 16,
    border_radius: int = BORDER_RADIUS_CARD,
    bgcolor: str = SURFACE_CARD,
    expand: bool | int = False,
    width: int | None = None,
    height: int | None = None,
) -> ft.Container:
    """Creates a modern glassmorphic card container with rounded corners."""
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=border_radius,
        bgcolor=bgcolor,
        border=ft.Border.all(1, SURFACE_GLASS_BORDER),
        expand=expand,
        width=width,
        height=height,
    )
