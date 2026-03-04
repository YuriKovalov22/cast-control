# CastLocal

**Cast any local video to Chromecast — from your terminal.**

A CLI and retro TUI (Far Manager-style) for streaming local video files to Chromecast devices. Handles format conversion automatically with hardware-accelerated transcoding.

![castlocal demo](docs/demo.gif)

## Why?

- **VLC's Chromecast support is broken.** Tab casting kills quality. This just works.
- Plays **any format** — MKV, AVI, MOV, WMV, FLV, and more. Transcodes on-the-fly.
- **Hardware-accelerated** H.264 encoding (VideoToolbox on macOS).
- Starts playing in seconds via **HLS streaming** — no waiting for full transcode.
- Two interfaces: quick **CLI** or a keyboard-driven **TUI** with a dual-pane file manager.

## Install

```bash
pipx install castlocal
```

Or with pip:

```bash
pip install castlocal
```

> Requires `ffmpeg` on your system: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux).

## Usage

### CLI — cast a file directly

```bash
cast movie.mkv                  # auto-discovers device
cast movie.mp4 -d "Living Room" # target a specific device
cast -l                         # list available devices
```

**Playback controls:** `[p]ause` `[f/b] ±30s` `[+/-] volume` `[q]uit`

### TUI — Far Manager-style interface

```bash
cast-tui
```

- **Left pane:** browse local files (video files highlighted in green)
- **Right pane:** discovered Chromecast devices (shown as folders)
- **F5** to cast, **F8** to stop, **F9** to rescan, **F3** for file info

Navigate with arrow keys, Tab to switch panes, Enter to select.

## How It Works

1. **Discovers** Chromecast devices on your network via mDNS/Zeroconf
2. **Probes** the video file — if it's already MP4/H.264, streams it directly
3. If not, **transcodes** to H.264+AAC using ffmpeg with HLS segmentation
4. **Serves** segments over HTTP as they're encoded — playback starts in seconds
5. **Casts** to the device with full playback controls

## Supported Formats

| Native (no transcode) | Transcoded on-the-fly |
|----------------------|----------------------|
| `.mp4` `.m4v` `.webm` | `.mkv` `.avi` `.mov` `.wmv` `.flv` `.ts` `.m2ts` |

## License

MIT
