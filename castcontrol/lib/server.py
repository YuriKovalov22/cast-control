"""HTTP server for streaming video to Chromecast."""

import os
import time
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

CHUNK = 256 * 1024


class SingleFileHandler(SimpleHTTPRequestHandler):
    """Serve exactly one file at /video."""
    file_path = None
    content_type = "video/mp4"

    def do_GET(self):
        if self.path != "/video":
            self.send_error(404)
            return
        size = os.path.getsize(self.file_path)

        range_header = self.headers.get("Range")
        if range_header:
            start, end = 0, size - 1
            r = range_header.replace("bytes=", "").split("-")
            start = int(r[0])
            if r[1]:
                end = int(r[1])
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
        else:
            start, length = 0, size
            self.send_response(200)
            self.send_header("Content-Length", str(size))

        self.send_header("Content-Type", self.content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        try:
            with open(self.file_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    data = f.read(min(CHUNK, remaining))
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        except BrokenPipeError:
            pass

    def log_message(self, *args):
        pass


class StreamingFileHandler(SimpleHTTPRequestHandler):
    """Serve a growing file with Range support for Chromecast.

    Uses estimated file size and waits for data when reading ahead of
    what ffmpeg has written so far.
    """
    file_path = None
    content_type = "video/mp4"
    transcode_ref = None
    estimated_size = 0  # set before serving

    def _current_size(self):
        try:
            return os.path.getsize(self.file_path)
        except OSError:
            return 0

    def _wait_for_data(self, offset, needed):
        """Block until file has enough data at offset, or transcode finishes."""
        tc = self.__class__.transcode_ref
        for _ in range(600):  # up to 60s
            available = self._current_size()
            if available >= offset + needed:
                return True
            if tc and tc.finished:
                return available >= offset + needed
            time.sleep(0.1)
        return False

    def do_GET(self):
        if self.path != "/video":
            self.send_error(404)
            return

        tc = self.__class__.transcode_ref
        est_size = self.__class__.estimated_size

        # Use actual size if transcode is done, otherwise estimated
        if tc and tc.finished:
            total_size = self._current_size()
        else:
            total_size = max(est_size, self._current_size())

        range_header = self.headers.get("Range")
        if range_header:
            start, end = 0, total_size - 1
            r = range_header.replace("bytes=", "").split("-")
            start = int(r[0])
            if r[1]:
                end = min(int(r[1]), total_size - 1)
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_size}")
            self.send_header("Content-Length", str(length))
        else:
            start, length = 0, total_size
            self.send_response(200)
            self.send_header("Content-Length", str(total_size))

        self.send_header("Content-Type", self.content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        try:
            with open(self.file_path, "rb") as f:
                f.seek(start)
                sent = 0
                while sent < length:
                    to_read = min(CHUNK, length - sent)
                    # Wait for data if we're ahead of transcode
                    if not self._wait_for_data(start + sent, to_read):
                        break
                    data = f.read(to_read)
                    if not data:
                        break
                    self.wfile.write(data)
                    sent += len(data)
        except BrokenPipeError:
            pass

    def log_message(self, *args):
        pass


def serve(filepath, content_type):
    """Start HTTP server for a single file. Returns (server, port)."""
    SingleFileHandler.file_path = filepath
    SingleFileHandler.content_type = content_type
    server = HTTPServer(("0.0.0.0", 0), SingleFileHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def serve_streaming(filepath, content_type, transcode_ref, estimated_size):
    """Start HTTP server for a growing file (live transcode). Returns (server, port)."""
    StreamingFileHandler.file_path = filepath
    StreamingFileHandler.content_type = content_type
    StreamingFileHandler.transcode_ref = transcode_ref
    StreamingFileHandler.estimated_size = estimated_size
    server = HTTPServer(("0.0.0.0", 0), StreamingFileHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


class HLSHandler(SimpleHTTPRequestHandler):
    """Serve HLS playlist and segment files with CORS for Chromecast.

    Serves files from hls_dir at the root level (no /hls/ prefix) to
    avoid Chromecast's broken relative URL resolution. CORS headers are
    required for adaptive streaming on Chromecast.
    """
    hls_dir = None
    transcode_ref = None
    _MIME = {".m3u8": "application/x-mpegURL", ".ts": "video/mp2t"}

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Expose-Headers",
                         "Content-Length, Content-Range, Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _resolve(self):
        """Resolve request path to a local file. Returns (filepath, ext) or None.

        For .ts segments still being transcoded, waits up to 30s for the
        file to appear on disk.
        """
        filename = self.path.split("?")[0].lstrip("/")
        if not filename:
            return None
        filepath = os.path.join(self.__class__.hls_dir, filename)
        # Wait for segments that are still being transcoded
        if not os.path.isfile(filepath) and filename.endswith(".ts"):
            tc = self.__class__.transcode_ref
            if tc and not tc.finished:
                for _ in range(300):  # up to 30s
                    if os.path.isfile(filepath) or tc.finished:
                        break
                    time.sleep(0.1)
        if not os.path.isfile(filepath):
            return None
        return filepath, os.path.splitext(filename)[1].lower()

    def _send_headers(self, filepath, ext):
        """Send response headers for a file. Returns (start, length) for body."""
        size = os.path.getsize(filepath)
        ctype = self._MIME.get(ext, "application/octet-stream")

        range_hdr = self.headers.get("Range")
        if range_hdr:
            start, end = 0, size - 1
            r = range_hdr.replace("bytes=", "").split("-")
            start = int(r[0])
            if r[1]:
                end = int(r[1])
            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
        else:
            start, length = 0, size
            self.send_response(200)
            self.send_header("Content-Length", str(size))

        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self._cors_headers()
        if ext == ".m3u8":
            self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        return start, length

    def do_HEAD(self):
        resolved = self._resolve()
        if not resolved:
            self.send_error(404)
            return
        self._send_headers(*resolved)

    def do_GET(self):
        resolved = self._resolve()
        if not resolved:
            self.send_error(404)
            return
        filepath, ext = resolved
        start, length = self._send_headers(filepath, ext)

        try:
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    data = f.read(min(CHUNK, remaining))
                    if not data:
                        break
                    self.wfile.write(data)
                    remaining -= len(data)
        except BrokenPipeError:
            pass

    def log_message(self, *args):
        pass


def serve_hls(hls_dir, transcode_ref=None):
    """Start HTTP server for HLS content. Returns (server, port)."""
    HLSHandler.hls_dir = hls_dir
    HLSHandler.transcode_ref = transcode_ref
    server = HTTPServer(("0.0.0.0", 0), HLSHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port
