"""Far Manager-style transcoding progress dialog."""

import os
import time

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button


class TranscodeProgressScreen(ModalScreen):
    """Modal progress bar during video transcoding.

    This is a passive display — call update_progress() from outside
    (via call_from_thread) to update the bar. Dismiss externally when done,
    or user presses Cancel/Escape to dismiss with False.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, filepath: str, label: str = "", **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath
        self.label = label
        self._start_time = time.time()

    BAR_WIDTH = 60

    @staticmethod
    def _render_bar(fraction, width):
        """Render a Far Manager-style progress bar: ████████░░░░░░░░"""
        filled = int(fraction * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def compose(self):
        filename = os.path.basename(self.filepath)
        with Vertical(classes="far-dialog"):
            yield Static(" Transcoding ", classes="far-dialog-title")
            yield Static(filename)
            if self.label:
                yield Static(self.label, classes="far-dialog-dim")
            yield Static(self._render_bar(0, self.BAR_WIDTH), id="transcode-bar")
            yield Static("", id="transcode-pct")
            yield Static("Preparing...", id="transcode-status")
            with Horizontal(classes="far-dialog-buttons"):
                yield Button("Cancel", id="cancel")

    def update_progress(self, pct):
        """Update progress bar and percentage text."""
        elapsed = time.time() - self._start_time
        remaining = ""
        if pct > 1:
            est_total = elapsed / (pct / 100)
            remaining = f"Remaining: {self._format_time(est_total - elapsed)}"

        try:
            self.query_one("#transcode-bar", Static).update(self._render_bar(pct / 100, self.BAR_WIDTH))
            self.query_one("#transcode-pct", Static).update(f"{pct:.0f}%")
            self.query_one("#transcode-status", Static).update(
                f"Time: {self._format_time(elapsed)}  {remaining}"
            )
        except Exception:
            pass

    def _format_time(self, seconds):
        seconds = int(max(0, seconds))
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel":
            self.dismiss(False)

    def action_cancel(self):
        self.dismiss(False)
