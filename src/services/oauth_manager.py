"""
OAuth 2.0 Device Code Flow Manager for YouTube Music.
Handles Google Device Authorization Grant via ytmusicapi native OAuthCredentials,
QR Code generation, background token polling, and credential persistence to oauth.json.
"""

import base64
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
import qrcode
from ytmusicapi.auth.oauth.credentials import OAuthCredentials

OAUTH_FILE_PATH = Path("oauth.json")


class OAuthManager:
    """Manages YouTube Music OAuth 2.0 Device Flow authentication."""

    def __init__(self, config_mgr=None):
        self.config_mgr = config_mgr
        self._oauth_credentials: Optional[OAuthCredentials] = None

    # ─── Authentication State ─────────────────────────────────────────

    def is_authenticated(self) -> bool:
        """Returns True if a valid oauth.json credential file exists."""
        if not OAUTH_FILE_PATH.exists():
            return False
        try:
            with open(OAUTH_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return isinstance(data, dict) and ("access_token" in data or "refresh_token" in data)
        except Exception:
            return False

    # ─── Client Credentials ───────────────────────────────────────────

    @property
    def client_id(self) -> str:
        if self.config_mgr:
            v = self.config_mgr.get("oauth_client_id", "").strip()
            if v:
                return v
        return ""

    @property
    def client_secret(self) -> str:
        if self.config_mgr:
            v = self.config_mgr.get("oauth_client_secret", "").strip()
            if v:
                return v
        return ""

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Saves OAuth client credentials to config."""
        if self.config_mgr:
            self.config_mgr.set("oauth_client_id", client_id.strip())
            self.config_mgr.set("oauth_client_secret", client_secret.strip())

    def has_oauth_credentials(self) -> bool:
        """Returns True if user has configured Google Cloud Client ID & Secret."""
        return bool(self.client_id and self.client_secret)

    # ─── Device Code Flow ─────────────────────────────────────────────

    def request_device_code(self) -> Dict[str, Any]:
        """
        Requests a device authorization code from Google using ytmusicapi OAuthCredentials.
        Returns dict with: device_code, user_code, verification_url, interval, direct_url.
        """
        if not self.has_oauth_credentials():
            raise RuntimeError(
                "Please configure your Google Cloud OAuth Client ID and Client Secret first."
            )

        self._oauth_credentials = OAuthCredentials(self.client_id, self.client_secret)
        code_data = self._oauth_credentials.get_code()

        user_code = code_data.get("user_code", "")
        verification_url = code_data.get("verification_url", "https://www.google.com/device")
        code_data["direct_url"] = f"{verification_url}?user_code={user_code}" if user_code else verification_url

        return dict(code_data)

    def poll_token(self, device_code: str) -> Optional[Dict[str, Any]]:
        """
        Polls Google's token endpoint using ytmusicapi OAuthCredentials.
        Returns token dict on success, None if authorization is still pending.
        """
        if not self._oauth_credentials:
            raise RuntimeError("No active OAuth session. Call request_device_code() first.")

        try:
            token_data = self._oauth_credentials.token_from_code(device_code)

            if token_data and token_data.get("access_token"):
                self._save_oauth_token(token_data)
                return dict(token_data)

            return None
        except Exception as e:
            err_str = str(e).lower()
            if "authorization_pending" in err_str or "slow_down" in err_str:
                return None
            raise

    def _save_oauth_token(self, token_data: dict) -> None:
        """Persists OAuth token and client info to oauth.json."""
        try:
            save_data = dict(token_data)
            save_data["client_id"] = self.client_id
            save_data["client_secret"] = self.client_secret
            with open(OAUTH_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            print(f"[OAuthManager] OAuth credentials saved to {OAUTH_FILE_PATH}")
        except Exception as e:
            print(f"[OAuthManager] Error saving oauth.json: {e}")

    # ─── QR Code Generator ───────────────────────────────────────────

    def generate_qr_code_base64(self, url: str) -> str:
        """Generates a high-contrast QR code image as a PNG base64 string."""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#000000", back_color="#FFFFFF")

            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"[OAuthManager] Local QR generation fallback: {e}")
            import urllib.parse
            import requests
            try:
                encoded = urllib.parse.quote(url)
                resp = requests.get(f"https://api.qrserver.com/v1/create-qr-code/?data={encoded}&size=250x250", timeout=5)
                if resp.status_code == 200:
                    return base64.b64encode(resp.content).decode("utf-8")
            except Exception:
                pass
            return ""

    # ─── Logout ──────────────────────────────────────────────────────

    def logout(self) -> bool:
        """Removes saved oauth.json credentials."""
        try:
            if OAUTH_FILE_PATH.exists():
                os.remove(OAUTH_FILE_PATH)
                print(f"[OAuthManager] Removed {OAUTH_FILE_PATH}")
                return True
        except Exception as e:
            print(f"[OAuthManager] Error removing {OAUTH_FILE_PATH}: {e}")
        return False
