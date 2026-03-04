# Cast Control — demo recording
# Run: vhs docs/demo.tape

Output docs/demo.gif

Set Shell "zsh"
Set FontSize 16
Set FontFamily "SF Mono"
Set Width 1200
Set Height 700
Set Theme "Catppuccin Frappe"
Set WindowBar Colorful
Set TypingSpeed 80ms
Set Padding 10

# Launch the TUI
Type "cast-tui"
Sleep 500ms
Enter
Sleep 10s

# Navigate in file browser — go into a folder with videos
# (adjust these keystrokes to match your actual file paths)
Down
Down
Down
Down
Down
Sleep 300ms
Enter
Sleep 1s
Down
Down
Down
Down
Down
Down
Down
Sleep 300ms
Enter
Sleep 1s
Down
Sleep 300ms
Enter
Sleep 1s
# Browse files — highlight a video file
Down
Down
Down
Sleep 500ms


# Switch to device pane
Tab
Sleep 1s

# Open a device (enter its "folder")
Enter
Sleep 1s

# Switch back to file pane
Tab
Sleep 500ms

# Show file info (F3 = ESC O R)
Escape
Type "OR"
Sleep 3s
Escape
Sleep 500ms


# Cast the file (F5 = ESC [ 1 5 ~)
Escape
Type "[15~"
Sleep 2s
Enter
Sleep 5s

# Quit
Sleep 2s
Ctrl+C
Sleep 1s
