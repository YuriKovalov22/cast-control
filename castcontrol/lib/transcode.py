"""Video transcoding with progress reporting."""

import json
import os
import shutil
import subprocess
import tempfile
import threading


class TranscodeError(Exception):
    pass


NATIVE_EXTENSIONS = {".mp4", ".m4v", ".webm"}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts"}
MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm"}


def needs_transcode(filepath):
    """Check if file needs transcoding based on extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext not in NATIVE_EXTENSIONS


def is_video(filepath):
    """Check if file is a video based on extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in VIDEO_EXTENSIONS


def get_mime(filepath):
    """Get MIME type for a video file."""
    ext = os.path.splitext(filepath)[1].lower()
    return MIME.get(ext, "video/mp4")


def probe(path):
    """Get video codec, audio codec, and duration via ffprobe.

    Returns:
        (video_codec, audio_codec, duration_seconds) tuple.
    """
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "quiet", "-show_entries",
            "stream=codec_name,codec_type", "-show_entries", "format=duration",
            "-of", "json", path,
        ], stderr=subprocess.DEVNULL, text=True)
        info = json.loads(out)
        duration = float(info.get("format", {}).get("duration", 0))
        vcodec = acodec = None
        for s in info.get("streams", []):
            if s.get("codec_type") == "video" and not vcodec:
                vcodec = s["codec_name"]
            elif s.get("codec_type") == "audio" and not acodec:
                acodec = s["codec_name"]
        return vcodec, acodec, duration
    except Exception:
        return None, None, 0


def _build_ffmpeg_args(src, vcodec, acodec, movflags):
    """Build ffmpeg codec args based on source codecs."""
    if vcodec == "h264":
        cv = ["-c:v", "copy"]
        label = "Remuxing (video is already H.264)"
    else:
        cv = ["-c:v", "h264_videotoolbox", "-q:v", "65"]
        label = "Transcoding (HW accelerated)"
    ca = ["-c:a", "copy"] if acodec == "aac" else ["-c:a", "aac", "-ac", "2"]
    return cv, ca, label


def transcode(src, on_progress=None):
    """Transcode video to MP4 (blocking, waits for completion).

    Returns:
        (path_to_transcoded_file, label) tuple.
    """
    vcodec, acodec, duration = probe(src)
    cv, ca, label = _build_ffmpeg_args(src, vcodec, acodec, "+faststart")

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()

    cmd = [
        "ffmpeg", "-y", "-progress", "pipe:1", "-i", src,
        *cv, *ca, "-movflags", "+faststart", tmp.name,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    for line in proc.stdout:
        if line.startswith("out_time_us=") and on_progress and duration > 0:
            try:
                us = int(line.split("=")[1])
                pct = min(us / 1_000_000 / duration * 100, 100)
                on_progress(pct)
            except ValueError:
                pass
    proc.wait()
    if proc.returncode != 0:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise TranscodeError(f"ffmpeg failed with exit code {proc.returncode}")

    if on_progress:
        on_progress(100)
    return tmp.name, label


class ChunkedTranscode:
    """Transcode in time chunks — each chunk is a complete, seekable MP4.

    Produces the first chunk fast so casting can start immediately,
    then continues transcoding the rest in the background.

    Usage:
        ct = ChunkedTranscode(src, chunk_secs=300)
        ct.start()
        # ct.current_path is ready after ct.ready.wait()
        # ct.full_path is set when full transcode finishes
    """

    FIRST_CHUNK = 120   # seconds for quick start
    FULL_CHUNK = 600    # seconds per subsequent chunk (0 = rest of file)

    def __init__(self, src, on_progress=None):
        self.src = src
        self.on_progress = on_progress
        self.vcodec, self.acodec, self.duration = probe(src)
        _, _, self.label = _build_ffmpeg_args(src, self.vcodec, self.acodec, "+faststart")
        self.current_path = None
        self.full_path = None
        self.finished = False
        self.error = None
        self.ready = threading.Event()
        self._tmp_files = []
        self._thread = None
        self._killed = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _transcode_segment(self, ss, duration_limit=None):
        """Transcode a segment to a complete faststart MP4."""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        self._tmp_files.append(tmp.name)

        vcodec, acodec = self.vcodec, self.acodec
        cv, ca, _ = _build_ffmpeg_args(self.src, vcodec, acodec, "+faststart")

        cmd = ["ffmpeg", "-y"]
        if ss > 0:
            cmd += ["-ss", str(ss)]
        cmd += ["-i", self.src]
        if duration_limit:
            cmd += ["-t", str(duration_limit)]
        cmd += [*cv, *ca, "-movflags", "+faststart", tmp.name]

        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if proc.returncode != 0:
            return None
        return tmp.name

    def _run(self):
        try:
            # First chunk: quick start
            path = self._transcode_segment(0, self.FIRST_CHUNK)
            if not path or self._killed:
                return
            self.current_path = path
            self.ready.set()

            if self.duration <= self.FIRST_CHUNK:
                self.full_path = path
                self.finished = True
                if self.on_progress:
                    self.on_progress(100)
                return

            # Full transcode in background
            if self.on_progress:
                self.on_progress(self.FIRST_CHUNK / self.duration * 100)

            full = self._transcode_full()
            if full and not self._killed:
                self.full_path = full
                if self.on_progress:
                    self.on_progress(100)
        except Exception as e:
            self.error = str(e)
        finally:
            self.finished = True

    def _transcode_full(self):
        """Full transcode with progress."""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        self._tmp_files.append(tmp.name)

        cv, ca, _ = _build_ffmpeg_args(self.src, self.vcodec, self.acodec, "+faststart")
        cmd = [
            "ffmpeg", "-y", "-progress", "pipe:1", "-i", self.src,
            *cv, *ca, "-movflags", "+faststart", tmp.name,
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in proc.stdout:
            if self._killed:
                proc.kill()
                return None
            if line.startswith("out_time_us=") and self.on_progress and self.duration > 0:
                try:
                    us = int(line.split("=")[1])
                    pct = min(us / 1_000_000 / self.duration * 100, 100)
                    self.on_progress(pct)
                except ValueError:
                    pass
        proc.wait()
        return tmp.name if proc.returncode == 0 else None

    def kill(self):
        self._killed = True

    def cleanup(self):
        self.kill()
        for f in self._tmp_files:
            try:
                os.unlink(f)
            except OSError:
                pass


class HLSTranscode:
    """Transcode to HLS segments for immediate streaming.

    Produces .ts segments and an .m3u8 playlist that grows as transcoding
    progresses. Chromecast plays segments as they become available — no
    file swap needed.

    Usage:
        ht = HLSTranscode(src)
        ht.start()
        ht.ready.wait()  # first segment available
        # ht.output_dir contains stream.m3u8 + seg_NNNN.ts files
    """

    SEGMENT_SECS = 10

    def __init__(self, src, on_progress=None):
        self.src = src
        self.on_progress = on_progress
        self.vcodec, self.acodec, self.duration = probe(src)
        _, _, self.label = _build_ffmpeg_args(src, self.vcodec, self.acodec, "")
        self.output_dir = tempfile.mkdtemp(prefix="cast_hls_")
        self.playlist_path = os.path.join(self.output_dir, "stream.m3u8")
        self.finished = False
        self.error = None
        self.ready = threading.Event()
        self._thread = None
        self._proc = None
        self._killed = False

        # Pre-generate a complete VOD playlist so Chromecast shows total
        # duration from the start. ffmpeg writes its own live playlist
        # to _live_path; the server serves our VOD playlist.
        if self.duration > 0:
            self._generate_vod_playlist()
            self._live_path = os.path.join(self.output_dir, "_live.m3u8")
        else:
            self._live_path = self.playlist_path

    def _generate_vod_playlist(self):
        """Write a complete VOD playlist with all expected segments."""
        import math
        num_segs = math.ceil(self.duration / self.SEGMENT_SECS)
        lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            f"#EXT-X-TARGETDURATION:{self.SEGMENT_SECS + 1}",
            "#EXT-X-MEDIA-SEQUENCE:0",
        ]
        remaining = self.duration
        for i in range(num_segs):
            dur = min(float(self.SEGMENT_SECS), remaining)
            lines.append(f"#EXTINF:{dur:.6f},")
            lines.append(f"seg_{i:04d}.ts")
            remaining -= dur
        lines.append("#EXT-X-ENDLIST")
        lines.append("")
        with open(self.playlist_path, "w") as f:
            f.write("\n".join(lines))

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            cv, ca, _ = _build_ffmpeg_args(self.src, self.vcodec, self.acodec, "")
            seg_pattern = os.path.join(self.output_dir, "seg_%04d.ts")

            cmd = [
                "ffmpeg", "-y", "-progress", "pipe:1", "-i", self.src,
                *cv, *ca,
                "-f", "hls",
                "-hls_time", str(self.SEGMENT_SECS),
                "-hls_playlist_type", "event",
                "-hls_list_size", "0",
                "-hls_segment_filename", seg_pattern,
                self._live_path,
            ]

            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )

            ready_signaled = False
            for line in self._proc.stdout:
                if self._killed:
                    self._proc.kill()
                    return

                if not ready_signaled and line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        if us >= self.SEGMENT_SECS * 1_000_000:
                            seg0 = os.path.join(self.output_dir, "seg_0000.ts")
                            if os.path.exists(seg0) and os.path.exists(self.playlist_path):
                                self.ready.set()
                                ready_signaled = True
                    except ValueError:
                        pass

                if line.startswith("out_time_us=") and self.on_progress and self.duration > 0:
                    try:
                        us = int(line.split("=")[1])
                        if us > 0:
                            pct = min(us / 1_000_000 / self.duration * 100, 100)
                            self.on_progress(pct)
                    except ValueError:
                        pass

            self._proc.wait()
            if self._proc.returncode != 0 and not self._killed:
                self.error = f"ffmpeg exited with code {self._proc.returncode}"
        except Exception as e:
            self.error = str(e)
        finally:
            if not self._killed:
                self.finished = True
                if self.on_progress:
                    self.on_progress(100)
            if not ready_signaled:
                self.ready.set()

    def kill(self):
        self._killed = True
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass

    def cleanup(self):
        self.kill()
        try:
            shutil.rmtree(self.output_dir, ignore_errors=True)
        except Exception:
            pass
