"""Textual dashboard over the same core API the CLI uses."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar

from rich.console import Group, RenderableType
from rich.style import Style
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static
from verkit.theme import DEFAULT as theme

from fleet_registry import __version__
from fleet_registry.core import FleetError
from fleet_registry.core import inventory as inv
from fleet_registry.core.audit import AuditResult, audit_node
from fleet_registry.core.models import Inventory
from fleet_registry.core.reconcile import diff, reconcile
from fleet_registry.core.ssh import ping
from fleet_registry.render import (
    audit_detail,
    changes_table,
    device_detail,
    reach_text,
    status_text,
)


def _theme_header_bg() -> str:
    """Translate the verkit Rich header style (e.g. "on grey23") to a CSS color."""
    bg = Style.parse(theme.header_style).bgcolor
    return bg.get_truecolor().hex if bg else "#3a3a3a"


COLUMNS = ("ID", "Hostname", "Model", "CPU", "RAM", "Tailscale IP", "Status", "SSH")


class FleetApp(App[None]):
    TITLE = "fleet-registry"
    CSS = """
    #devices { width: 3fr; }
    #detail-scroll { width: 2fr; border-left: solid $panel; padding: 0 1; }
    DataTable > .datatable--header { background: HEADER_BG; text-style: bold; }
    """.replace("HEADER_BG", _theme_header_bg())

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("a", "audit", "Audit"),
        Binding("A", "audit_all", "Audit all"),
        Binding("u", "update", "Apply audit"),
        Binding("p", "ping_all", "Ping"),
        Binding("r", "reload", "Reload"),
        Binding("q", "quit", "Quit"),
        # Vim-style navigation, shared with the other Textual TUIs.
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "focus_table", "Focus table", show=False),
        Binding("l", "focus_detail", "Focus detail", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("ctrl+d", "page_down", "Page down", show=False),
        Binding("ctrl+u", "page_up", "Page up", show=False),
    ]

    def __init__(self, inventory_path: Path) -> None:
        super().__init__()
        self.inventory_path = inventory_path
        self.inventory = Inventory()
        self.audits: dict[str, AuditResult] = {}
        self.audit_errors: dict[str, str] = {}
        self.reach: dict[str, bool | None] = {}

    # ------------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="devices", cursor_type="row", zebra_stripes=False)
            with VerticalScroll(id="detail-scroll"):
                yield Static(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"v{__version__} · {self.inventory_path}"
        table = self.query_one(DataTable)
        for col in COLUMNS:
            table.add_column(col, key=col)
        self.action_reload()
        self.action_ping_all()

    # ------------------------------------------------------------------ helpers

    @property
    def table(self) -> DataTable[RenderableType]:
        return self.query_one(DataTable)

    @property
    def detail_scroll(self) -> VerticalScroll:
        return self.query_one("#detail-scroll", VerticalScroll)

    def _table_focused(self) -> bool:
        return self.focused is not self.detail_scroll

    def selected_id(self) -> str | None:
        t = self.table
        if not t.row_count:
            return None
        return str(t.coordinate_to_cell_key(t.cursor_coordinate).row_key.value)

    def _row(self, dev_id: str) -> list[RenderableType]:
        d = self.inventory.find(dev_id)
        assert d is not None
        cpu = f"{d.specs.cores}c/{d.specs.threads}t" if d.specs.cores else "—"
        ram = f"{d.specs.ram_total_gb} GB" if d.specs.ram_total_gb else "—"
        return [
            Text(d.id, style="bold"),
            d.hostname or "—",
            d.model or "—",
            cpu,
            ram,
            d.network.tailscale_ip or "—",
            status_text(d.status),
            Text("…", style="dim")
            if d.id in self.reach and self.reach[d.id] is None
            else reach_text(self.reach.get(d.id)),
        ]

    def refresh_row(self, dev_id: str) -> None:
        for col, value in zip(COLUMNS, self._row(dev_id), strict=True):
            self.table.update_cell(dev_id, col, value)

    def show_detail(self) -> None:
        dev_id = self.selected_id()
        detail = self.query_one("#detail", Static)
        device = self.inventory.find(dev_id) if dev_id else None
        if device is None:
            detail.update("")
            return
        parts: list[RenderableType] = [device_detail(device)]
        if dev_id in self.audit_errors:
            parts += [Text(), Text(self.audit_errors[dev_id], style="red")]
        if (result := self.audits.get(device.id)) is not None:
            parts += [
                Text(),
                audit_detail(result),
                Text(),
                changes_table(diff(device, result), "pending changes (u to apply)"),
            ]
        detail.update(Group(*parts))

    def on_data_table_row_highlighted(self, _: DataTable.RowHighlighted) -> None:
        self.show_detail()

    # ------------------------------------------------------------------ navigation
    # Keys act on the focused pane: the device table moves its row cursor, the
    # detail pane scrolls.

    def action_cursor_down(self) -> None:
        if self._table_focused():
            self.table.action_cursor_down()
        else:
            self.detail_scroll.scroll_down()

    def action_cursor_up(self) -> None:
        if self._table_focused():
            self.table.action_cursor_up()
        else:
            self.detail_scroll.scroll_up()

    def action_cursor_top(self) -> None:
        if self._table_focused():
            self.table.move_cursor(row=0)
        else:
            self.detail_scroll.scroll_home()

    def action_cursor_bottom(self) -> None:
        if self._table_focused():
            self.table.move_cursor(row=self.table.row_count - 1)
        else:
            self.detail_scroll.scroll_end()

    def action_page_down(self) -> None:
        if self._table_focused():
            self.table.action_page_down()
        else:
            self.detail_scroll.scroll_page_down()

    def action_page_up(self) -> None:
        if self._table_focused():
            self.table.action_page_up()
        else:
            self.detail_scroll.scroll_page_up()

    def action_focus_table(self) -> None:
        self.table.focus()

    def action_focus_detail(self) -> None:
        self.detail_scroll.focus()

    # ------------------------------------------------------------------ actions

    def action_reload(self) -> None:
        try:
            self.inventory = inv.load(self.inventory_path)
        except FleetError as e:
            self.notify(str(e), severity="error", timeout=10)
            return
        table = self.table
        table.clear()
        for d in self.inventory.devices:
            table.add_row(*self._row(d.id), key=d.id)
        self.show_detail()

    @work(group="ssh")
    async def action_ping_all(self) -> None:
        devices = [d for d in self.inventory.devices if d.is_addressable]
        for d in devices:
            self.reach[d.id] = None
            self.refresh_row(d.id)

        async def one(dev_id: str, host: str) -> None:
            self.reach[dev_id] = await ping(host)
            self.refresh_row(dev_id)

        await asyncio.gather(*(one(d.id, d.ssh_target) for d in devices))

    async def _audit(self, dev_id: str) -> None:
        device = self.inventory.find(dev_id)
        if device is None:
            return
        self.notify(f"Auditing {dev_id} ...")
        try:
            self.audits[dev_id] = await audit_node(device.ssh_target)
            self.audit_errors.pop(dev_id, None)
            n = len(diff(device, self.audits[dev_id]))
            self.notify(f"{dev_id}: {n} pending change(s)" if n else f"{dev_id}: inventory matches")
        except FleetError as e:
            self.audit_errors[dev_id] = str(e)
            self.notify(str(e), severity="error", timeout=8)
        if dev_id == self.selected_id():
            self.show_detail()

    @work(group="ssh")
    async def action_audit(self) -> None:
        if dev_id := self.selected_id():
            await self._audit(dev_id)

    @work(group="ssh")
    async def action_audit_all(self) -> None:
        ids = [d.id for d in self.inventory.devices if d.is_addressable]
        await asyncio.gather(*(self._audit(i) for i in ids))

    def action_update(self) -> None:
        dev_id = self.selected_id()
        if not dev_id or dev_id not in self.audits:
            self.notify("Audit this node first (a).", severity="warning")
            return
        _, changes = reconcile(self.inventory, dev_id, self.audits[dev_id])
        if not changes:
            self.notify(f"{dev_id}: nothing to apply")
            return
        inv.save(self.inventory, self.inventory_path)
        self.refresh_row(dev_id)
        self.show_detail()
        self.notify(f"{dev_id}: applied {len(changes)} change(s) and saved inventory")
