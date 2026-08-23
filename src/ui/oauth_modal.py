"""
OAuth 2.0 Device Code Login Modal for YouTube Music.
Displays the Verification URL, Large Bold Activation Code, and QR Code for instant phone scanning.
Polls Google's OAuth endpoint asynchronously until authorized.
"""

import asyncio
from typing import Callable, Optional
import flet as ft

from src.services.oauth_manager import OAuthManager
from src.ui.theme import (
    ACCENT_GREEN,
    ACCENT_RED,
    BORDER_RADIUS_CARD,
    SURFACE_CARD,
    SURFACE_ELEVATED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TRANSPARENT_IMAGE_BASE64,
)


class OAuthModal(ft.Container):
    def __init__(
        self,
        oauth_manager: OAuthManager,
        on_login_success: Callable[[], None],
        on_close: Callable[[], None],
        async_runner: Optional[Callable] = None,
    ):
        self.oauth_manager = oauth_manager
        self.on_login_success = on_login_success
        self.on_close = on_close
        self.async_runner = async_runner
        self._polling_future = None
        self._is_active = False

        # --- 1. QR Code Display Elements ---
        self.img_qr = ft.Image(
            src_base64=TRANSPARENT_IMAGE_BASE64,
            width=180,
            height=180,
            fit=ft.ImageFit.CONTAIN,
            visible=False,
        )
        self.qr_loading_spinner = ft.ProgressRing(width=36, height=36, stroke_width=3, color=ACCENT_RED, visible=True)

        # --- 2. Activation Code & URL Elements ---
        self.txt_user_code = ft.Text(
            value="---- ----",
            size=30,
            weight=ft.FontWeight.W_900,
            color=ACCENT_RED,
            selectable=True,
            text_align=ft.TextAlign.CENTER,
        )
        self.txt_url = ft.Text(
            value="https://www.google.com/device",
            size=14,
            weight=ft.FontWeight.BOLD,
            color="#38BDF8",
            selectable=True,
        )
        self.spinner_status = ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT_RED, visible=False)
        self.txt_status = ft.Text("กำลังโหลดรหัสเข้าสู่ระบบ...", size=12, color=TEXT_SECONDARY, max_lines=3)

        # --- 3. Client Credentials Input Fields ---
        self.tf_client_id = ft.TextField(
            value=self.oauth_manager.client_id,
            label="Google Cloud OAuth Client ID",
            hint_text="xxxxxx.apps.googleusercontent.com",
            text_size=11,
            color=TEXT_PRIMARY,
            border_color="rgba(255, 255, 255, 0.2)",
            focused_border_color=ACCENT_RED,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        self.tf_client_secret = ft.TextField(
            value=self.oauth_manager.client_secret,
            label="Google Cloud OAuth Client Secret",
            password=True,
            can_reveal_password=True,
            text_size=11,
            color=TEXT_PRIMARY,
            border_color="rgba(255, 255, 255, 0.2)",
            focused_border_color=ACCENT_RED,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )

        # Main dynamic body container
        self.body_container = ft.Container(expand=True)

        # Master Modal Box
        modal_content = ft.Container(
            content=ft.Column(
                controls=[
                    # Modal Header
                    ft.Row(
                        controls=[
                            ft.Row(
                                [
                                    ft.Icon(ft.icons.ACCOUNT_CIRCLE_ROUNDED, size=28, color=ACCENT_RED),
                                    ft.Text("เชื่อมต่อ YouTube Music (OAuth 2.0)", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                ],
                                spacing=8,
                            ),
                            ft.IconButton(
                                icon=ft.icons.CLOSE_ROUNDED,
                                icon_color=TEXT_PRIMARY,
                                icon_size=24,
                                bgcolor="rgba(255, 255, 255, 0.1)",
                                on_click=lambda e: self.close_modal(),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(color="rgba(255, 255, 255, 0.1)", height=12),
                    self.body_container,
                ],
                spacing=10,
                expand=True,
            ),
            width=700,
            height=490,
            padding=22,
            border_radius=24,
            bgcolor=SURFACE_CARD,
            border=ft.border.all(1.5, "rgba(255, 255, 255, 0.15)"),
            shadow=ft.BoxShadow(spread_radius=10, blur_radius=50, color="rgba(0, 0, 0, 0.85)"),
        )

        super().__init__(
            content=ft.Column(
                controls=[modal_content],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
            bgcolor="rgba(0, 0, 0, 0.85)",
            alignment=ft.alignment.center,
            visible=False,
            expand=True,
        )

        self._refresh_body()

    def _refresh_body(self) -> None:
        """Renders either the QR code authorization screen or the credentials setup screen."""
        if self.oauth_manager.has_oauth_credentials():
            self.body_container.content = self._build_qr_screen()
        else:
            self.body_container.content = self._build_setup_screen()

        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def _build_qr_screen(self) -> ft.Container:
        """Screen showing QR code, user code, and status."""
        qr_box = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Stack(
                            controls=[
                                ft.Container(content=self.qr_loading_spinner, alignment=ft.alignment.center, width=180, height=180),
                                self.img_qr,
                            ],
                            alignment=ft.alignment.center,
                        ),
                        padding=6,
                        bgcolor="#FFFFFF",
                        border_radius=12,
                        shadow=ft.BoxShadow(spread_radius=1, blur_radius=12, color="rgba(0, 0, 0, 0.4)"),
                    ),
                    ft.Text("สแกนด้วยกล้องมือถือเพื่อเข้าสู่ระบบ", size=11, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            padding=14,
            bgcolor="rgba(255, 255, 255, 0.03)",
            border_radius=16,
            border=ft.border.all(1, "rgba(255, 255, 255, 0.08)"),
        )

        instructions_box = ft.Column(
            controls=[
                ft.Text("1. ไปที่ลิงก์นี้บนเบราว์เซอร์:", size=12, color=TEXT_SECONDARY),
                ft.Container(
                    content=ft.Row([ft.Icon(ft.icons.LINK_ROUNDED, size=16, color="#38BDF8"), self.txt_url], spacing=6),
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                    border_radius=8,
                    bgcolor="rgba(56, 189, 248, 0.1)",
                    border=ft.border.all(1, "rgba(56, 189, 248, 0.3)"),
                ),
                ft.Text("2. ป้อนรหัสยืนยันตัวตนนี้:", size=12, color=TEXT_SECONDARY),
                ft.Container(
                    content=self.txt_user_code,
                    padding=ft.padding.symmetric(horizontal=16, vertical=10),
                    border_radius=12,
                    bgcolor="rgba(255, 0, 51, 0.12)",
                    border=ft.border.all(1.5, ACCENT_RED),
                    alignment=ft.alignment.center,
                ),
                ft.Row(
                    controls=[self.spinner_status, self.txt_status],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                ),
                # Option to edit Client ID/Secret
                ft.Row(
                    controls=[
                        ft.TextButton(
                            content=ft.Row([ft.Icon(ft.icons.SETTINGS_OUTLINED, size=14, color=TEXT_MUTED), ft.Text("เปลี่ยน Client ID / Secret", size=11, color=TEXT_MUTED)]),
                            on_click=lambda e: self._switch_to_setup(),
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
            expand=True,
        )

        return ft.Container(
            content=ft.Row(
                controls=[qr_box, instructions_box],
                spacing=18,
                vertical_alignment=ft.CrossAxisAlignment.START,
                expand=True,
            ),
            expand=True,
        )

    def _build_setup_screen(self) -> ft.Container:
        """Screen asking user to input their Google Cloud OAuth credentials."""
        btn_save = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.icons.QR_CODE_2_ROUNDED, size=18),
                    ft.Text("บันทึกและสร้าง QR Code", size=14, weight=ft.FontWeight.BOLD),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
            bgcolor=ACCENT_RED,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                padding=ft.padding.symmetric(horizontal=20, vertical=14),
            ),
            on_click=self._handle_save_credentials,
        )

        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Row(
                                    [
                                        ft.Icon(ft.icons.INFO_OUTLINE_ROUNDED, size=18, color="#38BDF8"),
                                        ft.Text("ตั้งค่า Google OAuth Client ID ครั้งแรก (ใช้งานถาวร)", size=13, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ],
                                    spacing=6,
                                ),
                                ft.Text(
                                    "1. เข้าไปที่ Google Cloud Console (console.cloud.google.com) แล้วสร้างโปรเจกต์ฟรี\n"
                                    "2. เปิดใช้งาน 'YouTube Data API v3'\n"
                                    "3. ไปที่ Credentials → Create OAuth client ID → เลือกประเภท 'TVs and Limited Input devices'\n"
                                    "4. นำ Client ID และ Client Secret มาวางด้านล่างแล้วกดบันทึก",
                                    size=11,
                                    color=TEXT_SECONDARY,
                                ),
                            ],
                            spacing=4,
                        ),
                        padding=12,
                        border_radius=12,
                        bgcolor="rgba(56, 189, 248, 0.08)",
                        border=ft.border.all(1, "rgba(56, 189, 248, 0.25)"),
                    ),
                    self.tf_client_id,
                    self.tf_client_secret,
                    ft.Row([btn_save], alignment=ft.MainAxisAlignment.CENTER),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
        )

    def _switch_to_setup(self) -> None:
        self.tf_client_id.value = self.oauth_manager.client_id
        self.tf_client_secret.value = self.oauth_manager.client_secret
        self.body_container.content = self._build_setup_screen()
        if getattr(self, "page", None):
            self.update()

    def _handle_save_credentials(self, e) -> None:
        cid = self.tf_client_id.value.strip()
        sec = self.tf_client_secret.value.strip()
        if not cid or not sec:
            return

        self.oauth_manager.set_credentials(cid, sec)
        self._refresh_body()
        if self._is_active:
            self._start_oauth_flow()

    def open_modal(self) -> None:
        """Opens OAuth modal and initiates device authorization flow."""
        self._is_active = True
        self.visible = True
        self.opacity = 1.0

        if not self.oauth_manager.has_oauth_credentials():
            self._refresh_body()
        else:
            self._refresh_body()
            self._start_oauth_flow()

        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

    def close_modal(self) -> None:
        """Cancels polling and closes modal."""
        self._is_active = False
        if self._polling_future:
            try:
                if hasattr(self._polling_future, "cancel"):
                    self._polling_future.cancel()
            except Exception:
                pass

        self.visible = False
        self.opacity = 0.0
        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass
        self.on_close()

    def _start_oauth_flow(self) -> None:
        self.txt_status.value = "กำลังขอรหัสยืนยันจาก Google..."
        self.txt_status.color = TEXT_SECONDARY
        self.spinner_status.visible = True
        self.img_qr.visible = False
        self.qr_loading_spinner.visible = True

        if getattr(self, "page", None):
            try:
                self.update()
            except Exception:
                pass

        if self.async_runner:
            self._polling_future = self.async_runner(self._run_oauth_flow())
        else:
            try:
                loop = asyncio.get_running_loop()
                self._polling_future = loop.create_task(self._run_oauth_flow())
            except RuntimeError:
                pass

    async def _run_oauth_flow(self) -> None:
        """Requests device code and polls endpoint until authorized."""
        loop = asyncio.get_event_loop()
        try:
            code_info = await loop.run_in_executor(None, self.oauth_manager.request_device_code)
            user_code = code_info.get("user_code", "")
            verification_url = code_info.get("verification_url", "https://www.google.com/device")
            direct_url = code_info.get("direct_url", verification_url)
            device_code = code_info.get("device_code", "")
            interval = max(3, int(code_info.get("interval", 5)))

            qr_base64 = await loop.run_in_executor(None, self.oauth_manager.generate_qr_code_base64, direct_url)

            self.txt_user_code.value = user_code
            self.txt_url.value = verification_url
            self.img_qr.src_base64 = qr_base64
            self.img_qr.visible = True
            self.qr_loading_spinner.visible = False
            self.txt_status.value = "รอการยืนยันจากมือถือหรือเบราว์เซอร์ของคุณ..."

            if getattr(self, "page", None):
                try:
                    self.update()
                except Exception:
                    pass

            while self._is_active:
                await asyncio.sleep(interval)
                if not self._is_active:
                    break

                try:
                    token_result = await loop.run_in_executor(None, self.oauth_manager.poll_token, device_code)
                    if token_result:
                        self.txt_status.value = "เข้าสู่ระบบสำเร็จแล้ว!"
                        self.txt_status.color = ACCENT_GREEN
                        self.spinner_status.visible = False
                        if getattr(self, "page", None):
                            try:
                                self.update()
                            except Exception:
                                pass

                        await asyncio.sleep(1.5)
                        self.close_modal()
                        self.on_login_success()
                        break
                except Exception as poll_err:
                    print(f"[OAuthModal] Polling note: {poll_err}")
                    if "expired" in str(poll_err).lower() or "denied" in str(poll_err).lower():
                        self.txt_status.value = "รหัสหมดอายุ กรุณาเปิดหน้าต่างนี้ใหม่"
                        self.spinner_status.visible = False
                        if getattr(self, "page", None):
                            try:
                                self.update()
                            except Exception:
                                pass
                        break

        except Exception as e:
            print(f"[OAuthModal] OAuth Error: {e}")
            self.txt_status.value = f"ข้อผิดพลาด: {e}"
            self.txt_status.color = ACCENT_RED
            self.spinner_status.visible = False
            self.qr_loading_spinner.visible = False
            if getattr(self, "page", None):
                try:
                    self.update()
                except Exception:
                    pass
