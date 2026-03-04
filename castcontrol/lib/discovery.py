"""Chromecast device discovery with callback-based progress."""

import time
from dataclasses import dataclass, field

import pychromecast
from zeroconf import Zeroconf


class DiscoveryError(Exception):
    pass


@dataclass
class DeviceInfo:
    """Clean wrapper around pychromecast CastInfo."""
    name: str
    model: str
    host: str
    port: int
    uuid: str
    _cast_info: object = field(repr=False)


def scan_devices(timeout=8, on_device_found=None, on_tick=None):
    """Discover Chromecast devices.

    Args:
        timeout: Scan duration in seconds.
        on_device_found: Callback(DeviceInfo) called when a new device appears.
        on_tick: Callback(remaining_seconds, device_count) called each second.

    Returns:
        List of DeviceInfo objects found.
    """
    seen = set()
    devices = []

    class Listener(pychromecast.discovery.AbstractCastListener):
        def add_cast(self, uuid, _service):
            if uuid not in seen:
                seen.add(uuid)
                info = browser.devices.get(uuid)
                if info:
                    dev = DeviceInfo(
                        name=info.friendly_name,
                        model=info.model_name or "",
                        host=info.host,
                        port=info.port,
                        uuid=str(uuid),
                        _cast_info=info,
                    )
                    devices.append(dev)
                    if on_device_found:
                        on_device_found(dev)

        def remove_cast(self, *a):
            pass

        def update_cast(self, *a):
            pass

    zc = Zeroconf()
    browser = pychromecast.discovery.CastBrowser(Listener(), zc)
    browser.start_discovery()

    for remaining in range(timeout, 0, -1):
        if on_tick:
            on_tick(remaining, len(seen))
        time.sleep(1)

    browser.stop_discovery()
    zc.close()
    return devices


def connect_device(device: DeviceInfo):
    """Connect to a Chromecast device. Returns pychromecast.Chromecast.

    Raises DiscoveryError on failure.
    """
    try:
        zc = Zeroconf()
        cc = pychromecast.get_chromecast_from_cast_info(device._cast_info, zc)
        cc.wait()
        return cc
    except Exception as e:
        raise DiscoveryError(f"Failed to connect to {device.name}: {e}") from e
