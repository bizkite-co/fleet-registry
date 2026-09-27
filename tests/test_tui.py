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


def test_tui_vim_navigation(tmp_path: Path) -> None:
    inv = {"fleet_name": "Test", "devices": [{"id": i} for i in ("a", "b", "c")]}
    path = tmp_path / "devices.json"
    path.write_text(json.dumps(inv), encoding="utf-8")

    async def run() -> None:
        app = FleetApp(path)
        async with app.run_test() as pilot:
            await pilot.press("j", "j")
            assert app.selected_id() == "c"
            await pilot.press("k")
            assert app.selected_id() == "b"
            await pilot.press("g")
            assert app.selected_id() == "a"
            await pilot.press("G")
            assert app.selected_id() == "c"
            await pilot.press("l")
            assert app.focused is app.detail_scroll
            await pilot.press("j")  # scrolls the detail pane, not the table
            assert app.selected_id() == "c"
            await pilot.press("h")
            assert app.focused is app.table

    asyncio.run(run())
