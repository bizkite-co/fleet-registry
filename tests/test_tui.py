import asyncio
import json
from pathlib import Path

from textual.widgets import DataTable

from fleet_registry.tui.app import FleetApp


def test_tui_lists_devices(tmp_path: Path) -> None:
    # No addresses → the on-mount ping has nothing to reach, so no real SSH runs.
    inv = {"fleet_name": "Test", "devices": [{"id": "a"}, {"id": "b", "hostname": "B"}]}
    path = tmp_path / "devices.json"
    path.write_text(json.dumps(inv), encoding="utf-8")

    async def run() -> None:
        app = FleetApp(path)
        async with app.run_test() as pilot:
            table = app.query_one(DataTable)
            assert table.row_count == 2
            await pilot.press("down")
            assert app.selected_id() == "b"
            await pilot.press("u")  # no audit yet → warning, no crash

    asyncio.run(run())
