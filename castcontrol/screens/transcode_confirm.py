"""Transcoding confirmation dialog."""

import os

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button


class TranscodeConfirmScreen(ModalScreen[bool]):
    """Ask user to confirm transcoding before casting."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, filepath: str, label: str = "", **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath
        self.label = label

    def compose(self):
        filename = os.path.basename(self.filepath)
        ext = os.path.splitext(filename)[1].upper()
        with Vertical(classes="modal-dialog"):
            yield Static("Transcoding Required", classes="modal-title")
            yield Static(f'File "{filename}" is in {ext} format\nand needs conversion to MP4 for Chromecast.')
            if self.label:
                yield Static(self.label)
            yield Static("This may take several minutes.")
            with Horizontal(classes="modal-buttons"):
                yield Button("Transcode", variant="primary", id="yes")
                yield Button("Cancel", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")

    def action_cancel(self):
        self.dismiss(False)
