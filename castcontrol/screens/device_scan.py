"""Device scanning overlay screen."""

from __future__ import annotations

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button
from textual import work

from ..lib.discovery import scan_devices, DeviceInfo
from ..lib.network import wifi_name


class DeviceScanScreen(ModalScreen[list[DeviceInfo]]):
    """Modal overlay showing device scan progress."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    BAR_WIDTH = 60

    def __init__(self, timeout=8, **kwargs):
        super().__init__(**kwargs)
        self.timeout = timeout
        self._devices = []

    @staticmethod
    def _render_bar(fraction, width):
        """Render a Far Manager-style progress bar: ████████░░░░░░░░"""
        filled = int(fraction * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def compose(self):
        ssid = wifi_name()
        with Vertical(classes="far-dialog"):
            yield Static(" Scanning ", classes="far-dialog-title")
            yield Static(f"Network: {ssid}")
            yield Static("Searching...", id="scan-status")
            yield Static(self._render_bar(0, self.BAR_WIDTH), id="scan-bar")
            yield Static("", id="scan-pct")
            with Horizontal(classes="far-dialog-buttons"):
                yield Button("Cancel", id="cancel")

    def on_mount(self):
        self._run_scan()

    @work(thread=True)
    def _run_scan(self):
        def on_found(dev):
            self._devices.append(dev)
            self.app.call_from_thread(self._update_status)

        def on_tick(remaining, count):
            self.app.call_from_thread(self._update_tick, remaining, count)

        devices = scan_devices(
            timeout=self.timeout,
            on_device_found=on_found,
            on_tick=on_tick,
        )
        self.app.call_from_thread(self.dismiss, devices)

    def _update_status(self):
        count = len(self._devices)
        last = self._devices[-1].name if self._devices else ""
        self.query_one("#scan-status", Static).update(
            f"Found {count} device(s)" + (f" \u2014 {last}" if last else "")
        )

    def _update_tick(self, remaining, count):
        elapsed = self.timeout - remaining
        fraction = elapsed / self.timeout if self.timeout > 0 else 0
        try:
            self.query_one("#scan-bar", Static).update(
                self._render_bar(fraction, self.BAR_WIDTH)
            )
            self.query_one("#scan-pct", Static).update(f"{fraction * 100:.0f}%")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel":
            self.dismiss(self._devices)

    def action_cancel(self):
        self.dismiss(self._devices)
