"""Far Manager-style casting progress dialog — shown during playback."""

import os
import time

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button


class CastingScreen(ModalScreen):
    """Modal dialog that stays open during the entire cast, like Far's copy dialog.

    Dismisses with:
        "stop"  — user pressed Stop or Escape
        "done"  — playback ended naturally
    """

    BINDINGS = [
        ("escape", "stop_cast", "Stop"),
        ("space", "toggle_pause", "Pause"),
    ]

    def __init__(self, filename: str, device_name: str, session, **kwargs):
        super().__init__(**kwargs)
        self.filename = filename
        self.device_name = device_name
        self.session = session
        self._start_time = time.time()

    # Bar width inside the 64-char dialog (border + padding eat ~4 cols)
    BAR_WIDTH = 60

    @staticmethod
    def _render_bar(fraction, width):
        """Render a Far Manager-style progress bar: ████████░░░░░░░░"""
        filled = int(fraction * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def compose(self):
        with Vertical(classes="far-dialog"):
            yield Static(" Casting ", classes="far-dialog-title")
            yield Static(f"{self.filename}", id="cast-filename")
            yield Static(f"to {self.device_name}")
            yield Static(self._render_bar(0, self.BAR_WIDTH), id="cast-bar")
            yield Static("", id="cast-pct")
            yield Static("Connecting...", id="cast-status")
            with Horizontal(classes="far-dialog-buttons"):
                yield Button("Pause", id="pause")
                yield Button("Stop", id="stop")

    def update_progress(self, current_time, duration, is_paused):
        """Called every second by the app's timer."""
        pct = (current_time / duration * 100) if duration > 0 else 0
        ct = self._format_time(current_time)
        dt = self._format_time(duration)
        state = "\u23f8 Paused" if is_paused else "\u25b6 Playing"

        elapsed = time.time() - self._start_time
        remaining = ""
        if pct > 0 and duration > 0:
            remaining_secs = max(0, duration - current_time)
            remaining = f"Remaining: {self._format_time(remaining_secs)}"

        try:
            self.query_one("#cast-bar", Static).update(self._render_bar(pct / 100, self.BAR_WIDTH))
            self.query_one("#cast-pct", Static).update(f"{pct:.0f}%")
            status = f"{state}  {ct} / {dt}    Time: {self._format_time(elapsed)}  {remaining}"
            self.query_one("#cast-status", Static).update(status)
            btn = self.query_one("#pause", Button)
            btn.label = "Resume" if is_paused else "Pause"
        except Exception:
            pass

    def _format_time(self, seconds):
        seconds = int(seconds)
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "stop":
            self.dismiss("stop")
        elif event.button.id == "pause":
            if self.session:
                self.session.toggle_pause()

    def action_stop_cast(self):
        self.dismiss("stop")

    def action_toggle_pause(self):
        if self.session:
            self.session.toggle_pause()
