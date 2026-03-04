"""Left panel: local filesystem browser in Far Manager style."""

import os
import stat
import time

from textual.containers import Vertical
from textual.widgets import DataTable, Static
from textual.message import Message

from ..lib.transcode import is_video


class FileBrowserPane(Vertical):
    """File browser panel with DataTable showing directory contents."""

    class FileSelected(Message):
        """Fired when a file is highlighted."""
        def __init__(self, path: str):
            super().__init__()
            self.path = path

    def __init__(self, start_path=None, **kwargs):
        super().__init__(**kwargs)
        self.current_path = start_path or os.path.expanduser("~")
        self._entries = []

    def compose(self):
        yield Static(self.current_path, classes="pane-header", id="file-header")
        yield DataTable(id="file-table", classes="pane-table", cursor_type="row")

    def on_mount(self):
        table = self.query_one("#file-table", DataTable)
        table.add_columns("Name", "Size", "Modified")
        self.navigate_to(self.current_path)

    def navigate_to(self, path):
        """Populate table with directory contents."""
        path = os.path.abspath(path)
        try:
            entries = os.listdir(path)
        except PermissionError:
            return

        self.current_path = path
        self.query_one("#file-header", Static).update(path)

        table = self.query_one("#file-table", DataTable)
        table.clear()
        self._entries = []

        # Parent directory
        self._entries.append(("..", None, True))
        table.add_row("[bold white]..[/]", "<UP>", "")

        # Collect and sort: directories first, then files
        dirs = []
        files = []
        for name in entries:
            if name.startswith("."):
                continue
            full = os.path.join(path, name)
            try:
                st = os.stat(full)
                is_dir = stat.S_ISDIR(st.st_mode)
                size = st.st_size
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
                if is_dir:
                    dirs.append((name, full, size, mtime))
                else:
                    files.append((name, full, size, mtime))
            except OSError:
                continue

        dirs.sort(key=lambda x: x[0].lower())
        files.sort(key=lambda x: x[0].lower())

        for name, full, size, mtime in dirs:
            self._entries.append((name, full, True))
            table.add_row(f"[bold white]{name}/[/]", "<DIR>", mtime)

        for name, full, size, mtime in files:
            self._entries.append((name, full, False))
            size_str = self._format_size(size)
            if is_video(full):
                table.add_row(f"[bold green]{name}[/]", size_str, mtime)
            else:
                table.add_row(name, size_str, mtime)

    def _format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} K"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} M"
        else:
            return f"{size / 1024 / 1024 / 1024:.1f} G"

    @property
    def selected_entry(self):
        """Get the currently highlighted entry: (name, full_path, is_dir) or None."""
        table = self.query_one("#file-table", DataTable)
        if table.cursor_row is not None and 0 <= table.cursor_row < len(self._entries):
            return self._entries[table.cursor_row]
        return None

    @property
    def selected_file(self):
        """Get the full path of the selected file, or None if it's a directory."""
        entry = self.selected_entry
        if entry and not entry[2]:  # not a directory
            return entry[1]
        return None

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Handle Enter key on a row."""
        if event.data_table.id != "file-table":
            return
        entry = self.selected_entry
        if not entry:
            return

        name, full_path, is_dir = entry
        if name == "..":
            parent = os.path.dirname(self.current_path)
            self.navigate_to(parent)
        elif is_dir:
            self.navigate_to(full_path)
        else:
            self.post_message(self.FileSelected(full_path))

    def go_parent(self):
        """Navigate to parent directory."""
        parent = os.path.dirname(self.current_path)
        if parent != self.current_path:
            self.navigate_to(parent)
