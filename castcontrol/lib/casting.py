"""High-level casting session orchestrator."""

import os

from .discovery import DeviceInfo, connect_device, DiscoveryError
from .network import local_ip
from .server import serve, serve_hls
from .transcode import needs_transcode, MIME, HLSTranscode


class CastError(Exception):
    pass


class CastSession:
    """Manages a single casting session: connect, HLS-transcode, serve, cast."""

    def __init__(self, device: DeviceInfo, filepath: str):
        self.device = device
        self.filepath = filepath
        self._server = None
        self._cc = None
        self._mc = None
        self._hls_tc = None
        self._is_playing = False
        self._is_paused = False
        self._url = None
        self._real_duration = 0

    @property
    def is_playing(self):
        return self._is_playing

    @property
    def is_paused(self):
        return self._is_paused

    @property
    def is_transcoding(self):
        return self._hls_tc is not None and not self._hls_tc.finished

    @property
    def transcode_label(self):
        if self._hls_tc:
            return self._hls_tc.label
        return ""

    @property
    def status(self):
        """Current playback status dict with current_time and duration."""
        if self._mc:
            try:
                self._mc.update_status()
                st = self._mc.status
                # Use real duration from source — Chromecast may not know it for HLS
                dur = self._real_duration if self._real_duration > 0 else (st.duration or 0)
                return {
                    "current_time": st.current_time or 0,
                    "duration": dur,
                    "player_state": st.player_state or "UNKNOWN",
                }
            except Exception:
                pass
        return {"current_time": 0, "duration": self._real_duration or 0, "player_state": "UNKNOWN"}

    def start(self, on_transcode_progress=None):
        """Connect to device, HLS-transcode if needed, serve and cast.

        Blocking call — run in a worker thread.
        Uses HLS for seamless streaming: segments are served as they're
        transcoded, no file swap needed.

        Raises:
            CastError on failure.
        """
        filepath = self.filepath
        ext = os.path.splitext(filepath)[1].lower()

        if needs_transcode(filepath):
            self._hls_tc = HLSTranscode(filepath, on_progress=on_transcode_progress)
            self._hls_tc.start()
            self._hls_tc.ready.wait()
            if self._hls_tc.error:
                raise CastError(f"Transcoding failed: {self._hls_tc.error}")
            self._real_duration = self._hls_tc.duration

            self._server, port = serve_hls(self._hls_tc.output_dir, transcode_ref=self._hls_tc)
            self._url = f"http://{local_ip()}:{port}/stream.m3u8"
            content_type = "application/x-mpegURL"
        else:
            content_type = MIME.get(ext, "video/mp4")
            self._server, port = serve(filepath, content_type)
            self._url = f"http://{local_ip()}:{port}/video"
            self._real_duration = 0  # will come from Chromecast

        try:
            self._cc = connect_device(self.device)
        except DiscoveryError as e:
            if self._hls_tc:
                self._hls_tc.kill()
            raise CastError(str(e)) from e

        self._mc = self._cc.media_controller

        # For HLS: stream_type BUFFERED + explicit duration → TV shows progress bar
        play_kwargs = {}
        if self._hls_tc and self._real_duration > 0:
            play_kwargs["stream_type"] = "BUFFERED"
            play_kwargs["media_info"] = {"duration": self._real_duration}
            play_kwargs["title"] = os.path.basename(self.filepath)

        self._mc.play_media(self._url, content_type, **play_kwargs)
        self._mc.block_until_active(timeout=30)
        self._is_playing = True
        self._is_paused = False

    def pause(self):
        if self._mc and self._is_playing:
            self._mc.pause()
            self._is_paused = True

    def resume(self):
        if self._mc and self._is_paused:
            self._mc.play()
            self._is_paused = False

    def toggle_pause(self):
        if self._is_paused:
            self.resume()
        else:
            self.pause()

    def seek(self, offset_seconds):
        """Seek relative to current position (positive = forward)."""
        if self._mc and self._is_playing:
            try:
                current = self._mc.status.current_time or 0
                self._mc.seek(max(0, current + offset_seconds))
            except Exception:
                pass

    def set_volume(self, delta):
        """Adjust volume by delta (-1.0 to 1.0)."""
        if self._cc:
            try:
                current = self._cc.status.volume_level
                self._cc.set_volume(max(0.0, min(1.0, current + delta)))
            except Exception:
                pass

    def stop(self):
        """Stop casting and clean up."""
        if self._mc and self._is_playing:
            try:
                self._mc.stop()
            except Exception:
                pass
        self._is_playing = False
        self._is_paused = False
        if self._hls_tc:
            self._hls_tc.kill()
            self._hls_tc.cleanup()
            self._hls_tc = None
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None
