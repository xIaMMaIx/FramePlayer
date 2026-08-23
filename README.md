# 🎵 Frame Player: CarPlay Music & Digital Photo Frame Kiosk

A touch-friendly Kiosk application designed for **7-inch+ landscape tablets** (Apple CarPlay / Android Auto aesthetic), combining a live YouTube Music dashboard (`ytmusicapi` + `yt-dlp` streaming) with an automated local photo digital frame screensaver.

---

## 📱 Core Features

- **🚗 Apple CarPlay / Android Auto UI Theme:**
  - High-contrast dark theme (`#0D0E12`) with glassmorphic cards and glowing accents.
  - Oversized touch targets (48px–68px) designed specifically for capacitive touch screens.
  - Left navigation dock with live digital clock, active tab indicator, and idle countdown timer.
- **🔐 OAuth 2.0 Device Code Login (`oauth_manager.py` & `oauth_modal.py`):**
  - Instant Google OAuth Device Code Grant flow for touch screens.
  - Generates a **live QR Code** and **large bold User Code** for easy phone camera scanning.
  - Asynchronously polls for authorization in the background and persists credentials to `oauth.json`.
- **🎧 Live YouTube Music Streaming (`ytmusic_service.py` & `audio_controller.py`):**
  - **Liked Songs:** 1-tap playback of your entire Liked Songs library.
  - **My Playlists:** Browse and play your custom YouTube Music playlists with album art and track counts.
  - **Catalog Search:** Real-time on-screen search for any song or artist on YouTube Music.
  - **Direct Audio Stream Extractor:** Uses `yt-dlp` (`bestaudio[ext=m4a]`) with in-memory caching for zero-delay stream loading.
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
│   │   ├── oauth_manager.py # Google Device Code flow & QR code generator
│   │   ├── ytmusic_service.py# ytmusicapi wrapper & yt-dlp audio stream extractor
│   │   └── audio_controller.py# flet.Audio engine, queue manager, state sync & idle integration
│   └── ui/
│       ├── __init__.py
│       ├── theme.py         # Dark color palette & glassmorphic styling
│       ├── sidebar.py       # CarPlay left navigation dock with live clock
│       ├── music_view.py    # Split-view CarPlay dashboard (Now Playing + Controls + Queue)
│       ├── photo_view.py    # Fullscreen cross-fading photo slideshow
│       ├── action_overlay.py# 2-card touch wake modal
│       ├── oauth_modal.py   # Modal showing QR code & User Code
│       ├── library_drawer.py# Playlists, Liked Songs & Search browser
│       └── settings_view.py # Folder configuration & YouTube Music login
├── config.json              # Local kiosk configuration
├── oauth.json               # Auto-saved YouTube Music credentials
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
- `yt-dlp>=2026.0.0`
- `qrcode>=7.4.0`
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

## 🔐 Logging into YouTube Music

1. In the application, navigate to **Settings** (⚙️ on sidebar) or open the **Library** drawer.
2. Tap **Sign In with YouTube Music**.
3. Scan the displayed QR Code with your smartphone or open `https://www.google.com/device` and enter the code shown on the screen.
4. Authorize access with your Google account.
5. The modal will automatically close and your **Liked Songs** and **Playlists** will load immediately.
