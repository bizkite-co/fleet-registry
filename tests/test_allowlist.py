from fleet_registry.core.allowlist import generate_baked_rules, get_fleet_hosts
from fleet_registry.core.models import Inventory


def test_get_fleet_hosts() -> None:
    inv = Inventory.model_validate(
        {
            "devices": [
                {
                    "id": "node01",
                    "hostname": "Node01",
                    "network": {"tailscale_ip": "100.1.1.1", "lan_ip": "192.168.1.10"},
                }
            ]
        }
    )
    hosts = get_fleet_hosts(inv)
    assert "node01" in hosts
    assert "100.1.1.1" in hosts
    assert "192.168.1.10" in hosts


def test_generate_baked_rules() -> None:
    rules = generate_baked_rules(["nuc01", "100.88.63.109"])
    assert len(rules) == 6
    ssh_rule = rules[0]["rule"]
    assert "nuc01" in ssh_rule
    assert "100\\.88\\.63\\.109" in ssh_rule
