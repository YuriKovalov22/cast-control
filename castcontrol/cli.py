#!/usr/bin/env python3
"""Cast any local video to a Chromecast device — CLI interface."""

import argparse
import atexit
import os
import select
import signal
import sys
import time

from .lib.network import local_ip, wifi_name
from .lib.discovery import scan_devices, connect_device, DiscoveryError
from .lib.transcode import NATIVE_EXTENSIONS, MIME, HLSTranscode
from .lib.server import serve, serve_hls


# ── ANSI helpers ──────────────────────────────────────────────────────────────

CLEAR_LINE = "\033[2K"
CURSOR_UP = "\033[F"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def status_line(msg):
    """Print a single-line status update, overwriting the current line."""
    sys.stdout.write(f"\r{CLEAR_LINE}{msg}")
    sys.stdout.flush()


def fmt_time(secs):
    """Format seconds as H:MM:SS or M:SS."""
    if secs is None or secs < 0:
        return "0:00"
    secs = int(secs)
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def progress_bar(fraction, width=30):
    """Render a progress bar: [████████░░░░░░░░░░░░]"""
    filled = int(fraction * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan(timeout=8):
    ssid = wifi_name()
    ip = local_ip()
    print(f"  Network: {ssid}  ({ip})")

    found_names = []

    def on_found(dev):
        found_names.append(dev.name)
        status_line(f"  Scanning... found {dev.name} ({dev.host})")

    def on_tick(remaining, count):
        if not found_names:
            status_line(f"  Scanning... {remaining}s ({count} found)")

    devices = scan_devices(timeout, on_device_found=on_found, on_tick=on_tick)
    status_line(f"  Scan complete: {len(devices)} device(s) found.\n")
    return devices


def list_devices(timeout=8):
    devices = scan(timeout)
    if not devices:
        print("  No Chromecast devices found.")
    else:
        for dev in devices:
            print(f"  {dev.name}  ({dev.model}, {dev.host}:{dev.port})")
    return devices


def discover(device_name=None, timeout=8):
    devices = scan(timeout)

    if not devices:
        sys.exit("No Chromecast devices found." + (f" (looked for '{device_name}')" if device_name else ""))

    if device_name:
        devices = [d for d in devices if d.name == device_name]
        if not devices:
            sys.exit(f"Device '{device_name}' not found.")

    if len(devices) == 1:
        dev = devices[0]
    else:
        print("\n  Select a device:")
        for i, dev in enumerate(devices):
            print(f"    [{i}] {dev.name}")
        try:
            idx = int(input("  Device number: "))
            dev = devices[idx]
        except (ValueError, IndexError):
            sys.exit("Invalid selection.")

    print(f"  Connecting to {dev.name}...", end="", flush=True)
    try:
        cc = connect_device(dev)
    except DiscoveryError as e:
        sys.exit(f"\n  {e}")
    print(f" connected.")
    return cc, dev


# ── Live playback display ────────────────────────────────────────────────────

def playback_loop(cc, mc, filename, device_name, transcode=None):
    """Live playback display with controls.

    Renders a 3-line block that updates in-place:
      Line 1: filename → device
      Line 2: state + progress bar + time
      Line 3: controls + background transcode status
    """
    import tty, termios

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    sys.stdout.write(HIDE_CURSOR)

    # Real duration from source (Chromecast may not know it for HLS)
    real_duration = transcode.duration if transcode else 0

    # Track transcode progress
    tc_pct = [0.0]
    if transcode:
        def _track(pct):
            tc_pct[0] = max(tc_pct[0], pct)
        transcode.on_progress = _track

    lines_drawn = 0

    def draw():
        nonlocal lines_drawn
        # Move cursor back to start of our 3-line block
        if lines_drawn > 0:
            sys.stdout.write(CLEAR_LINE)  # clear current line (line 3)
            for _ in range(lines_drawn - 1):
                sys.stdout.write(CURSOR_UP + CLEAR_LINE)

        # Get status
        try:
            mc.update_status()
        except Exception:
            pass
        st = mc.status
        cur = st.current_time or 0
        dur = real_duration if real_duration > 0 else (st.duration or 0)
        state = st.player_state or "UNKNOWN"
        frac = cur / dur if dur > 0 else 0

        # State indicator
        if state == "PLAYING":
            indicator = "\u25b6 PLAYING"
        elif state == "PAUSED":
            indicator = "\u23f8 PAUSED "
        elif state == "BUFFERING":
            indicator = "\u23f3 BUFFER "
        elif state == "IDLE":
            indicator = "\u23f9 IDLE   "
        else:
            indicator = f"  {state:8s}"

        # Background transcode status
        tc_status = ""
        if transcode and not transcode.finished:
            tc_status = f"  \u27f3 Transcoding: {tc_pct[0]:.0f}%"
        elif transcode and transcode.finished:
            tc_status = "  \u2713 Transcode complete"

        # Render
        line1 = f"  {filename}  \u2192  {device_name}"
        line2 = f"  {indicator}  [{progress_bar(frac)}]  {fmt_time(cur)} / {fmt_time(dur)}"
        line3 = f"  [p]ause  [f/b] \u00b130s  [+/-] vol  [q]uit{tc_status}"

        sys.stdout.write(f"{line1}\n{line2}\n{line3}")
        sys.stdout.flush()
        lines_drawn = 3

    try:
        # Initial draw
        print()  # blank line separator
        draw()

        while True:
            # select: wait up to 0.5s for keypress, then redraw
            ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            if ready:
                ch = sys.stdin.read(1)
                if ch == "\x1b":
                    # Arrow key escape sequence: \x1b [ A/B/C/D
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        ch2 = sys.stdin.read(1)
                        if ch2 == "[" and select.select([sys.stdin], [], [], 0.05)[0]:
                            ch3 = sys.stdin.read(1)
                            if ch3 == "C":  # right arrow
                                ch = "f"
                            elif ch3 == "D":  # left arrow
                                ch = "b"
                            else:
                                ch = ""
                        else:
                            ch = ""
                    else:
                        ch = ""  # bare escape

                ch = ch.lower()
                if ch in ("p", " "):
                    st = mc.status
                    if st.player_state == "PAUSED":
                        mc.play()
                    else:
                        mc.pause()
                elif ch == "f":
                    mc.seek(mc.status.current_time + 30)
                elif ch == "b":
                    mc.seek(max(0, mc.status.current_time - 30))
                elif ch in ("+", "="):
                    cc.set_volume(min(1.0, (cc.status.volume_level or 0) + 0.1))
                elif ch == "-":
                    cc.set_volume(max(0.0, (cc.status.volume_level or 0) - 0.1))
                elif ch in ("q", "s"):
                    break

            draw()

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        # Clean exit
        sys.stdout.write(SHOW_CURSOR + "\n")
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        try:
            mc.stop()
        except Exception:
            pass
        print("  Stopped.")


# ── Main ─────────────────────────────────────────────────────────────────────

_hls_tc = None


def _cleanup():
    if _hls_tc:
        _hls_tc.cleanup()


def main():
    global _hls_tc

    parser = argparse.ArgumentParser(description="Cast a video to Chromecast")
    parser.add_argument("video", nargs="?", help="Path to video file")
    parser.add_argument("--device", "-d", help="Chromecast device name")
    parser.add_argument("-l", "--list", action="store_true", help="List available Chromecast devices")
    args = parser.parse_args()

    if args.list:
        list_devices()
        return

    if not args.video:
        parser.error("video is required (or use -l to list devices)")

    if not os.path.isfile(args.video):
        sys.exit(f"File not found: {args.video}")

    atexit.register(_cleanup)
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    filepath = os.path.abspath(args.video)
    filename = os.path.basename(args.video)
    ext = os.path.splitext(filepath)[1].lower()

    # ── Transcode if needed (HLS for seamless streaming) ──
    if ext not in NATIVE_EXTENSIONS:
        _hls_tc = HLSTranscode(filepath)
        print(f"  {_hls_tc.label}")
        _hls_tc.start()
        print("  Preparing stream...", end="", flush=True)
        t0 = time.time()
        _hls_tc.ready.wait()
        print(f" ready ({time.time() - t0:.1f}s)")

        server, port = serve_hls(_hls_tc.output_dir, transcode_ref=_hls_tc)
        url = f"http://{local_ip()}:{port}/stream.m3u8"
        content_type = "application/x-mpegURL"
    else:
        content_type = MIME.get(ext, "video/mp4")
        server, port = serve(filepath, content_type)
        url = f"http://{local_ip()}:{port}/video"

    # ── Discover device ──
    cc, dev = discover(args.device)

    # ── Cast ──
    cc.set_volume(1.0)
    print(f"  Serving: {url}")
    mc = cc.media_controller
    # stream_type BUFFERED + explicit duration → TV shows normal progress bar
    real_duration = _hls_tc.duration if _hls_tc else 0
    mc.play_media(
        url, content_type,
        title=filename,
        current_time=0,
        stream_type="BUFFERED",
        media_info={"duration": real_duration} if real_duration > 0 else {},
    )
    mc.block_until_active(timeout=30)

    # ── Live playback ──
    playback_loop(cc, mc, filename, dev.name, _hls_tc)

    # ── Cleanup ──
    if _hls_tc:
        _hls_tc.kill()
        _hls_tc.cleanup()
    server.shutdown()


if __name__ == "__main__":
    main()
