"""Network utilities: local IP detection and Wi-Fi SSID."""

import socket
import subprocess


def local_ip():
    """Get local IP address by connecting to an external address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def wifi_name():
    """Get current Wi-Fi SSID on macOS."""
    for cmd in [
        ["networksetup", "-getairportnetwork", "en0"],
        ["networksetup", "-getairportnetwork", "en1"],
    ]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
            if "not associated" not in out.lower():
                return out.split(": ", 1)[-1]
        except Exception:
            pass
    try:
        import objc  # noqa
        from CoreWLAN import CWWiFiClient
        iface = CWWiFiClient.sharedWiFiClient().interface()
        if iface and iface.ssid():
            return iface.ssid()
    except Exception:
        pass
    return "unknown"
