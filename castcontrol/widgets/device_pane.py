"""Right panel: Chromecast device browser with device-as-folder metaphor."""

from __future__ import annotations

import os

from textual.containers import Vertical
from textual.widgets import DataTable, Static
from textual.message import Message

from ..lib.discovery import DeviceInfo
from ..lib.casting import CastSession


class DevicePane(Vertical):
    """Device browser with two states: device list and device-open (folder)."""

    class DeviceOpened(Message):
        def __init__(self, device: DeviceInfo):
            super().__init__()
            self.device = device

    class DeviceClosed(Message):
        pass

    class CastStarted(Message):
        pass

    class CastStopped(Message):
        pass

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.devices: list[DeviceInfo] = []
        self.current_device: DeviceInfo | None = None
        self.cast_session: CastSession | None = None

    def compose(self):
        yield Static("Devices", classes="pane-header", id="device-header")
        yield DataTable(id="device-table", classes="pane-table", cursor_type="row")

    def on_mount(self):
        table = self.query_one("#device-table", DataTable)
        table.add_columns("Name", "Model", "Address")

    def set_devices(self, devices: list[DeviceInfo]):
        """Update the device list."""
        self.devices = devices
        if not self.current_device:
            self.show_device_list()

    def show_device_list(self):
        """Show all discovered devices as 'folders'."""
        self.current_device = None
        self.query_one("#device-header", Static).update("Devices")

        table = self.query_one("#device-table", DataTable)
        table.clear()

        if not self.devices:
            table.add_row("[dim]No devices found[/]", "", "")
            table.add_row("[dim]Press F9 to scan[/]", "", "")
        else:
            for dev in self.devices:
                table.add_row(
                    f"[bold white]{dev.name}/[/]",
                    dev.model,
                    f"{dev.host}:{dev.port}",
                )

    def open_device(self, device: DeviceInfo):
        """Enter a device 'folder'."""
        self.current_device = device
        self.query_one("#device-header", Static).update(f"{device.name}")

        table = self.query_one("#device-table", DataTable)
        table.clear()
        table.add_row("[bold white]..[/]", "<UP>", "")

        if self.cast_session and self.cast_session.is_playing:
            fname = os.path.basename(self.cast_session.filepath)
            table.add_row(f"[bold green]{fname}[/]", "CASTING", "")

        self.post_message(self.DeviceOpened(device))

    def close_device(self):
        """Exit device folder, stop any active cast."""
        if self.cast_session:
            self.cast_session.stop()
            self.cast_session = None
            self.post_message(self.CastStopped())
        self.current_device = None
        self.show_device_list()
        self.post_message(self.DeviceClosed())

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Handle Enter on a row."""
        if event.data_table.id != "device-table":
            return

        table = self.query_one("#device-table", DataTable)
        row_idx = table.cursor_row

        if self.current_device:
            # Inside a device folder
            if row_idx == 0:  # ".." entry
                self.close_device()
        else:
            # Device list mode
            if 0 <= row_idx < len(self.devices):
                self.open_device(self.devices[row_idx])

    def go_parent(self):
        """Navigate back from device folder."""
        if self.current_device:
            self.close_device()
