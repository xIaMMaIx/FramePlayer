# 🎵 Frame Player: CarPlay Music & Digital Photo Frame Kiosk

A touch-friendly Kiosk application designed for **7-inch+ landscape tablets** (Apple CarPlay / Android Auto aesthetic), combining a live YouTube Music dashboard (`ytmusicapi` + `yt-dlp` streaming) with an automated local photo digital frame screensaver.

---

## 📱 Core Features

- **🚗 Apple CarPlay / Android Auto UI Theme:**
  - High-contrast dark theme (`#0D0E12`) with glassmorphic cards and glowing accents.
  - Oversized touch targets (48px–68px) designed specifically for capacitive touch screens.
  - Left navigation dock with live digital clock, active tab indicator, and idle countdown timer.
- **🎧 Live YouTube Music Streaming (`ytmusic_service.py` & `audio_controller.py`):**
  - **No login required:** search uses `ytmusicapi` guest mode; no Google account or API key.
  - **Catalog Search:** Real-time on-screen search for any song or artist on YouTube Music.
  - **Local Playlist:** Save search results to an on-device playlist (`local_playlist.json`).
  - **Direct Audio Stream Extractor:** Uses `yt-dlp` with the logged-out `visionos` client (no PO token / JS runtime) to fetch audio-only AAC (itag 140), with a small in-memory URL cache.
  - Full transport controls: Shuffle, Previous, 64px Play/Pause, Next, Repeat (All/One/Off), Timeline Scrubber, and Volume.
- **🖼️ Digital Photo Frame Screensaver (`photo_view.py`):**
  - Automatically transitions with smooth cross-fade when playback is paused/stopped for **60 continuous seconds** (customizable).
  - Dual-layer async cross-fading slideshow engine advancing images every 8–10 seconds.
  - Scans local folders for `.jpg`, `.jpeg`, `.png`, and `.webp` images.
- **✨ Touch Wake / Quick Action Overlay (`action_overlay.py`):**
  - Tapping the screen during screensaver mode triggers a 2-card action overlay:
    1. **[ 🎵 YouTube Music ]** -> Instantly returns to the CarPlay dashboard.
    2. **[ 📁 Change Photo Folder ]** -> Native folder selection dialog (`FilePicker`).

---

## 📂 Project Architecture

```
Frame_player/
├── assets/
│   └── samples/             # Built-in artistic landscape sample wallpapers
├── src/
│   ├── __init__.py
│   ├── config_manager.py    # JSON persistence manager (config.json)
│   ├── state.py             # AppState, AppMode enums, event dispatch
│   ├── photo_engine.py      # Async image scanner & playlist manager
│   ├── music_backend.py     # Track dataclass & BaseMusicBackend interface
│   ├── services/
│   │   ├── __init__.py
│   │   ├── local_playlist_manager.py# On-device playlist persistence
│   │   ├── ytmusic_service.py# ytmusicapi wrapper & yt-dlp audio stream extractor
│   │   └── audio_controller.py# flet.Audio engine, queue manager, state sync & idle integration
│   └── ui/
│       ├── __init__.py
│       ├── theme.py         # Dark color palette & glassmorphic styling
│       ├── music_view.py    # Split-view CarPlay dashboard (Now Playing + Controls + Queue)
│       ├── photo_view.py    # Fullscreen cross-fading photo slideshow
│       ├── action_overlay.py# 2-card touch wake modal
│       ├── library_drawer.py# Local playlist & search browser
│       └── settings_view.py # Display & photo folder configuration
├── config.json              # Local kiosk configuration
├── local_playlist.json      # Saved local playlist
├── main.py                  # Application entrypoint & background async task coordinator
├── requirements.txt         # Project dependencies
└── README.md                # Documentation & setup guide
```

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- `flet>=0.25.0`
- `ytmusicapi>=1.12.0`
- `yt-dlp>=2026.10.26`
- `pillow>=10.0.0`

### 2. Installation
```bash
pip install -r requirements.txt
```

### 3. Launch Application
```bash
python main.py
```

---

## 🎶 Playing Music

No account is needed. Open the **Library** drawer, search for a song or artist, and tap a result to play it or add it to your local playlist.
