# GTM Execution Playbook

## Pre-Launch Checklist

- [ ] Verify `cast-control` name is available on PyPI (`pip index versions cast-control`)
- [ ] Replace `YuriKovalov22` in pyproject.toml and docs with actual GitHub username
- [ ] Record demo GIF (see below)
- [ ] Create GitHub repo and push code
- [ ] Enable GitHub Pages (Settings → Pages → Source: `/docs`)

## Step 1: Record the Demo GIF

This is your #1 marketing asset. Use [vhs](https://github.com/charmbracelet/vhs) or [asciinema](https://asciinema.org/):

```bash
brew install vhs     # recommended — produces GIFs directly
```

Script to show:
1. Run `cast-tui` → show the dual-pane UI loading
2. Navigate to a video file (arrow keys)
3. Tab to device pane → show discovered device
4. F5 to cast → show transcode progress dialog
5. Show playback dialog with progress bar

Save as `docs/demo.gif`, uncomment the img tag in README.md and index.html.

## Step 2: Publish to PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

Verify: `pip install cast-control && cast --help`

## Step 3: Submit to Homebrew (after PyPI)

Create a tap first (easier than homebrew-core for new packages):

```bash
# Create repo: homebrew-tap on GitHub
# Add formula (see docs/cast-control.rb template)
# Users install with:
brew tap YuriKovalov22/tap
brew install cast-control
```

For homebrew-core submission (later, once you have stars/downloads):
https://docs.brew.sh/Adding-Software-to-Homebrew

## Step 4: Show HN Post

**Title:** `Show HN: Cast Control – Stream any local video to Chromecast from your terminal`

**Body:**
```
I built a CLI and TUI for casting local video files to Chromecast devices.

The problem: VLC's Chromecast support has been broken for years. Chrome tab
casting murders quality. I wanted something that just works from the terminal.

Cast Control auto-discovers devices, probes the video format, and if it's not
natively supported (MKV, AVI, etc.), transcodes on-the-fly using ffmpeg with
HLS segmentation — so playback starts in seconds, not minutes.

The TUI is a dual-pane Far Manager-style interface (nostalgia included). Left
pane browses files, right pane shows devices as folders. F5 to cast.

Built with Python, pychromecast, Textual, and ffmpeg.

pip install cast-control

https://github.com/YuriKovalov22/cast-control
```

**Best times to post:** Tuesday–Thursday, 8-10am ET

## Step 5: Awesome Lists Submissions

Submit PRs to these repos (one PR each, follow their contribution guidelines):

| List | URL | Why |
|------|-----|-----|
| awesome-selfhosted | github.com/awesome-selfhosted/awesome-selfhosted | Media streaming section |
| awesome-python | github.com/vinta/awesome-python | Video category |
| awesome-cli-apps | github.com/agarrharr/awesome-cli-apps | Media section |
| awesome-tuis | github.com/rothgar/awesome-tuis | Media/Video |
| awesome-chromecast | github.com/marcosero/awesome-chromecast | Tools section |
| awesome-terminal-apps | github.com/toolleeo/cli-apps | Multimedia |
| awesome-python-applications | github.com/mahmoud/awesome-python-applications | Multimedia |

**PR format:** One-liner with description matching the list's style. Example:
```
- [cast-control](https://github.com/YuriKovalov22/cast-control) - Cast local video files to Chromecast with CLI/TUI and automatic transcoding.
```

## Step 6: Reddit Posts

Post to these subreddits (space them 2-3 days apart, not all at once):

1. **r/selfhosted** — "I made a terminal tool to cast any video format to Chromecast"
2. **r/commandline** — "Far Manager-style TUI for Chromecast casting"
3. **r/Python** — "Built a Textual TUI for casting videos to Chromecast"
4. **r/Chromecast** — "Open source CLI for casting local files (any format)"

## Step 7: Ongoing (week 2+)

- Tweet/X thread showing the TUI with screenshots (retro aesthetics go viral)
- dev.to post: "How I replaced VLC Chromecast casting with Python"
- Monitor GitHub issues — first users' bugs = highest priority
- Add `pipx install cast-control` to README once confirmed working

## Revenue Path (if traction appears)

1. **GitHub Sponsors** — enable immediately
2. **Pro features** (gate behind license key):
   - Playlist / queue management
   - Subtitle file support (.srt, .ass)
   - Multi-device simultaneous casting
   - Resume playback from last position
3. **Desktop GUI** (Tauri wrapper) — sell at $14.99 on Gumroad
