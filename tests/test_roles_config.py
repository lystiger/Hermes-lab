import json
from pathlib import Path

ROLES = json.loads((Path(__file__).resolve().parent.parent / "config" / "roles.json").read_text())


def test_the_security_role_is_read_only_and_offline():
    security = ROLES["security"]

    assert security["may_edit_product_source"] is False
    assert security["network"] is False
    assert security["may_run_exploits"] is False


def test_every_role_says_what_it_produces_and_when_it_stops():
    for name, profile in ROLES.items():
        for key in ("purpose", "scope", "tools", "output", "stops_when", "authority"):
            assert profile.get(key), f"{name} is missing {key}"
