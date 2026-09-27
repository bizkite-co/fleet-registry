from fleet_registry.core.models import Inventory
from fleet_registry.core.tailscale import match_device, parse_status

STATUS = {
    "Self": {
        "HostName": "DESKTOP-X",
        "DNSName": "desktop-x.tn.ts.net.",
        "OS": "windows",
        "TailscaleIPs": ["100.1.1.1"],
        "Online": False,
    },
    "Peer": {
        "k1": {
            "HostName": "DESKTOP-X",
            "DNSName": "desktop-x-1.tn.ts.net.",
            "OS": "linux",
            "TailscaleIPs": ["100.1.1.2", "fd7a::2"],
            "Online": True,
        },
        "k2": {
            "HostName": "NUC01",
            "DNSName": "nuc01.tn.ts.net.",
            "OS": "linux",
            "TailscaleIPs": ["100.2.2.2"],
            "Online": True,
            "LastSeen": "0001-01-01T00:00:00Z",
        },
        "k3": {
            "HostName": "cocli5x0",
            "DNSName": "cocli5x0.tn.ts.net.",
            "OS": "linux",
            "TailscaleIPs": ["100.3.3.3"],
            "Online": False,
            "LastSeen": "2026-04-24T10:00:00Z",
        },
        "k4": {
            "HostName": "phone",
            "DNSName": "phone.tn.ts.net.",
            "OS": "android",
            "TailscaleIPs": ["100.4.4.4"],
            "Online": True,
        },
    },
}


def test_parse_status_names_and_flags() -> None:
    nodes = {n.name: n for n in parse_status(STATUS)}
    assert set(nodes) == {"desktop-x", "desktop-x-1", "nuc01", "cocli5x0", "phone"}
    assert nodes["desktop-x"].is_self and nodes["desktop-x"].online
    assert nodes["desktop-x-1"].is_local  # WSL on this machine
    assert nodes["nuc01"].ip == "100.2.2.2" and nodes["nuc01"].last_seen is None
    assert nodes["cocli5x0"].last_seen == "2026-04-24T10:00:00Z"
    candidates = sorted(n.name for n in nodes.values() if n.is_fleet_candidate)
    assert candidates == ["cocli5x0", "nuc01"]


def test_match_device_by_ip_or_name() -> None:
    inv = Inventory.model_validate(
        {"devices": [{"id": "n1", "network": {"tailscale_ip": "100.2.2.2"}}, {"id": "cocli5x0"}]}
    )
    nodes = {n.name: n for n in parse_status(STATUS)}
    assert match_device(inv, nodes["nuc01"]).id == "n1"  # type: ignore[union-attr]
    assert match_device(inv, nodes["cocli5x0"]).id == "cocli5x0"  # type: ignore[union-attr]
    assert match_device(inv, nodes["phone"]) is None
