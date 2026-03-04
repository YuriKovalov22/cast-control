#!/usr/bin/env python3
"""Cast TUI — Far Manager-style Chromecast casting app."""

import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Header, Footer, Static
from textual.screen import ModalScreen
from textual import work

from .widgets.file_pane import FileBrowserPane
from .widgets.device_pane import DevicePane
from .screens.device_scan import DeviceScanScreen
from .screens.transcode_confirm import TranscodeConfirmScreen
from .screens.transcode_progress import TranscodeProgressScreen
from .screens.casting import CastingScreen
from .lib.transcode import needs_transcode, is_video, probe
from .lib.casting import CastSession, CastError


class ErrorScreen(ModalScreen):
    """Simple error dialog."""

    BINDINGS = [("escape", "dismiss_screen", "Close"), ("enter", "dismiss_screen", "Close")]

    def __init__(self, title: str, message: str, **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._message = message

    def compose(self):
        from textual.containers import Vertical
        from textual.widgets import Button
        with Vertical(classes="modal-dialog"):
            yield Static(self._title, classes="modal-title")
            yield Static(self._message)
            with Horizontal(classes="modal-buttons"):
                yield Button("OK", variant="primary", id="ok")

    def on_button_pressed(self, event):
        self.dismiss()

    def action_dismiss_screen(self):
        self.dismiss()


class FileInfoScreen(ModalScreen):
    """Show video file information via ffprobe."""

    BINDINGS = [("escape", "dismiss_screen", "Close"), ("enter", "dismiss_screen", "Close")]

    def __init__(self, filepath: str, **kwargs):
        super().__init__(**kwargs)
        self.filepath = filepath

    def compose(self):
        from textual.containers import Vertical
        from textual.widgets import Button
        filename = os.path.basename(self.filepath)
        size = os.path.getsize(self.filepath)
        vcodec, acodec, duration = probe(self.filepath)

        size_str = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB"
        dur_m, dur_s = divmod(int(duration), 60)
        dur_h, dur_m = divmod(dur_m, 60)
        dur_str = f"{dur_h}:{dur_m:02d}:{dur_s:02d}" if dur_h else f"{dur_m}:{dur_s:02d}"

        with Vertical(classes="modal-dialog"):
            yield Static("File Info", classes="modal-title")
            yield Static(f"Name:     {filename}")
            yield Static(f"Size:     {size_str}")
            yield Static(f"Duration: {dur_str}")
            yield Static(f"Video:    {vcodec or 'unknown'}")
            yield Static(f"Audio:    {acodec or 'unknown'}")
            yield Static(f"Needs transcoding: {'Yes' if needs_transcode(self.filepath) else 'No'}")
            with Horizontal(classes="modal-buttons"):
                yield Button("OK", variant="primary", id="ok")

    def on_button_pressed(self, event):
        self.dismiss()

    def action_dismiss_screen(self):
        self.dismiss()


class CastApp(App):
    """Far Manager-style Chromecast casting TUI."""

    CSS_PATH = "tui.tcss"
    TITLE = "Cast"

    BINDINGS = [
        Binding("f3", "view_info", "View", show=True),
        Binding("f5", "cast", "Cast", show=True),
        Binding("f8", "stop_cast", "Stop", show=True),
        Binding("f9", "refresh_devices", "Refresh", show=True),
        Binding("f10", "quit", "Quit", show=True),
        Binding("tab", "switch_pane", "Switch", priority=True),
        Binding("backspace", "go_parent", "Back"),
        Binding("space", "toggle_pause", "Pause", show=False),
        Binding("ctrl+right", "seek_forward", "Seek+", show=False),
        Binding("ctrl+left", "seek_backward", "Seek-", show=False),
        Binding("plus,equal", "volume_up", "Vol+", show=False),
        Binding("minus", "volume_down", "Vol-", show=False),
    ]

    def __init__(self):
        super().__init__()
        self._status_timer = None
        self._casting_screen = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-panels"):
            yield FileBrowserPane(id="left-pane")
            yield DevicePane(id="right-pane")
        yield Footer()

    def on_mount(self):
        self.query_one("#left-pane").focus()
        # Auto-scan for devices on startup
        self.action_refresh_devices()

    # --- Pane switching ---

    @property
    def _active_pane(self):
        """Determine active pane from which widget has focus."""
        focused = self.focused
        if focused:
            try:
                # Check if focused widget is inside the right pane
                right = self.query_one("#right-pane")
                node = focused
                while node:
                    if node is right:
                        return "right"
                    node = node.parent
            except Exception:
                pass
        return "left"

    def action_switch_pane(self):
        if self._active_pane == "left":
            self.query_one("#device-table").focus()
        else:
            self.query_one("#file-table").focus()

    def action_go_parent(self):
        if self._active_pane == "left":
            self.query_one("#left-pane", FileBrowserPane).go_parent()
        else:
            self.query_one("#right-pane", DevicePane).go_parent()

    # --- Device scanning ---

    def action_refresh_devices(self):
        self.push_screen(DeviceScanScreen(), callback=self._on_scan_complete)

    def _on_scan_complete(self, devices):
        self.query_one("#right-pane", DevicePane).set_devices(devices or [])

    # --- Casting ---

    def action_cast(self):
        file_pane = self.query_one("#left-pane", FileBrowserPane)
        device_pane = self.query_one("#right-pane", DevicePane)

        filepath = file_pane.selected_file
        if not filepath:
            self.push_screen(ErrorScreen("Error", "Select a video file in the left panel."))
            return

        if not is_video(filepath):
            self.push_screen(ErrorScreen("Error", f"Not a video file: {os.path.basename(filepath)}"))
            return

        if not device_pane.current_device:
            self.push_screen(ErrorScreen("Error", "Open a device first.\nSelect a device in the right panel and press Enter."))
            return

        if device_pane.cast_session and device_pane.cast_session.is_playing:
            device_pane.cast_session.stop()
            device_pane.cast_session = None

        if needs_transcode(filepath):
            vcodec, acodec, _dur = probe(filepath)
            if vcodec == "h264":
                label = "Remuxing (video is already H.264)"
            else:
                label = "Transcoding (HW accelerated)"
            self.push_screen(
                TranscodeConfirmScreen(filepath, label=label),
                callback=lambda confirmed, _fp=filepath, _dp=device_pane, _lb=label: self._on_transcode_confirmed(confirmed, _fp, _dp, _lb),
            )
        else:
            self._start_cast(filepath, device_pane)

    def _on_transcode_confirmed(self, confirmed, filepath, device_pane, label):
        if not confirmed:
            return
        # Show progress dialog, then start cast with progress updates
        progress_screen = TranscodeProgressScreen(filepath, label=label)
        self._progress_screen = progress_screen
        self.push_screen(progress_screen, callback=lambda result: self._on_progress_dismissed(result, filepath, device_pane))
        self._start_cast_with_progress(filepath, device_pane, progress_screen)

    def _on_progress_dismissed(self, result, filepath, device_pane):
        """Called when progress screen is dismissed (by cancel or completion)."""
        if result is False:
            # User cancelled — stop any in-progress cast session
            if device_pane.cast_session:
                device_pane.cast_session.stop()
                device_pane.cast_session = None

    def _start_cast(self, filepath, device_pane):
        """Start casting a file that does NOT need transcoding."""
        session = CastSession(device_pane.current_device, filepath)
        device_pane.cast_session = session
        self._do_cast(session, device_pane)

    @work(thread=True)
    def _do_cast(self, session, device_pane):
        try:
            session.start()
            self.app.call_from_thread(self._on_cast_started, session, device_pane)
        except CastError as e:
            self.app.call_from_thread(
                self.push_screen,
                ErrorScreen("Cast Error", str(e)),
            )
            device_pane.cast_session = None

    @work(thread=True)
    def _start_cast_with_progress(self, filepath, device_pane, progress_screen):
        """Start casting with transcode progress updates."""
        session = CastSession(device_pane.current_device, filepath)
        device_pane.cast_session = session

        def on_progress(pct):
            try:
                self.app.call_from_thread(progress_screen.update_progress, pct)
            except Exception:
                pass

        try:
            session.start(on_transcode_progress=on_progress)
            self.app.call_from_thread(self._on_cast_started_with_progress, session, device_pane, progress_screen)
        except CastError as e:
            device_pane.cast_session = None
            self.app.call_from_thread(self._on_cast_error_with_progress, str(e), progress_screen)

    def _on_cast_started_with_progress(self, session, device_pane, progress_screen):
        """Cast started — dismiss transcode progress, show casting dialog."""
        try:
            progress_screen.dismiss(True)
        except Exception:
            pass
        self._on_cast_started(session, device_pane)

    def _on_cast_error_with_progress(self, error_msg, progress_screen):
        """Cast failed — dismiss progress screen and show error."""
        try:
            progress_screen.dismiss(True)
        except Exception:
            pass
        self.push_screen(ErrorScreen("Cast Error", error_msg))

    def _on_cast_started(self, session, device_pane):
        # Refresh device pane to show the casting file
        device_pane.open_device(device_pane.current_device)
        device_pane.post_message(DevicePane.CastStarted())
        # Show the Far Manager-style casting dialog
        filename = os.path.basename(session.filepath)
        device_name = device_pane.current_device.name
        casting_screen = CastingScreen(filename, device_name, session)
        self._casting_screen = casting_screen
        self.push_screen(casting_screen, callback=self._on_casting_dismissed)
        # Start status update timer
        self._start_status_updates()

    def _on_casting_dismissed(self, result):
        """Casting dialog closed."""
        self._stop_status_timer()
        if result == "stop":
            # User stopped — clean up
            device_pane = self.query_one("#right-pane", DevicePane)
            if device_pane.cast_session:
                device_pane.cast_session.stop()
                device_pane.cast_session = None
            if device_pane.current_device:
                device_pane.open_device(device_pane.current_device)
        self._casting_screen = None

    def _start_status_updates(self):
        self._stop_status_timer()
        self._status_timer = self.set_interval(1.0, self._update_playback_status)

    def _stop_status_timer(self):
        if self._status_timer:
            self._status_timer.stop()
            self._status_timer = None

    def _update_playback_status(self):
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session and device_pane.cast_session.is_playing:
            status = device_pane.cast_session.status
            if self._casting_screen:
                self._casting_screen.update_progress(
                    status["current_time"],
                    status["duration"],
                    device_pane.cast_session.is_paused,
                )
        else:
            # Playback ended naturally
            self._stop_status_timer()
            if self._casting_screen:
                try:
                    self._casting_screen.dismiss("done")
                except Exception:
                    pass
                self._casting_screen = None

    # --- Playback controls ---

    def action_stop_cast(self):
        if self._casting_screen:
            # Dismiss the casting dialog — triggers _on_casting_dismissed
            try:
                self._casting_screen.dismiss("stop")
            except Exception:
                pass
            return
        # No casting dialog open — stop directly
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session:
            device_pane.cast_session.stop()
            device_pane.cast_session = None
            if device_pane.current_device:
                device_pane.open_device(device_pane.current_device)
            self._stop_status_timer()

    def action_toggle_pause(self):
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session and device_pane.cast_session.is_playing:
            device_pane.cast_session.toggle_pause()

    def action_seek_forward(self):
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session and device_pane.cast_session.is_playing:
            device_pane.cast_session.seek(30)

    def action_seek_backward(self):
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session and device_pane.cast_session.is_playing:
            device_pane.cast_session.seek(-30)

    def action_volume_up(self):
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session:
            device_pane.cast_session.set_volume(0.05)

    def action_volume_down(self):
        device_pane = self.query_one("#right-pane", DevicePane)
        if device_pane.cast_session:
            device_pane.cast_session.set_volume(-0.05)

    # --- File info ---

    def action_view_info(self):
        file_pane = self.query_one("#left-pane", FileBrowserPane)
        filepath = file_pane.selected_file
        if filepath and is_video(filepath):
            self.push_screen(FileInfoScreen(filepath))

    # --- Cleanup ---

    def on_unmount(self):
        try:
            device_pane = self.query_one("#right-pane", DevicePane)
            if device_pane.cast_session:
                device_pane.cast_session.stop()
        except Exception:
            pass


def main():
    app = CastApp()
    app.run()


if __name__ == "__main__":
    main()
