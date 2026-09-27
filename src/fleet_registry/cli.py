"""`fr` / `fleet-registry` command line. Run with no subcommand to open the TUI."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from verkit import display_version_info

from fleet_registry import PACKAGE_NAME
from fleet_registry.core import FleetError, config
from fleet_registry.core import inventory as inv
from fleet_registry.core.audit import AuditResult, audit_many
from fleet_registry.core.models import Inventory
from fleet_registry.core.reconcile import diff, reconcile
from fleet_registry.core.ssh import is_wsl, ping_many, ssh_executable
from fleet_registry.core.tailscale import match_device, tailnet_nodes
from fleet_registry.render import (
    audit_detail,
    changes_table,
    device_detail,
    fleet_table,
    tailnet_table,
)

console = Console()
err = Console(stderr=True)

app = typer.Typer(
    help="Fleet inventory, hardware audit, and node management. "
    "Run without a command to open the TUI.",
    no_args_is_help=False,
    rich_markup_mode="rich",
)


@dataclass
class State:
    inventory_opt: Path | None = None
    _path: Path | None = field(default=None, repr=False)

    @property
    def path(self) -> Path:
        if self._path is None:
            self._path = config.resolve_inventory_path(self.inventory_opt)
        return self._path

    def load(self) -> Inventory:
        return inv.load(self.path)


def _state(ctx: typer.Context) -> State:
    return ctx.ensure_object(State)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    inventory: Annotated[
        Path | None,
        typer.Option(
            "--inventory", "-i", help="Path to devices.json.", envvar=config.ENV_INVENTORY
        ),
    ] = None,
) -> None:
    ctx.obj = State(inventory)
    if ctx.invoked_subcommand is None:
        tui(ctx)


@app.command("list")
def list_(
    ctx: typer.Context,
    ping: Annotated[bool, typer.Option("--ping", "-p", help="Check SSH reachability.")] = False,
) -> None:
    """Show the fleet."""
    state = _state(ctx)
    data = state.load()
    reach = None
    if ping:
        targets = {d.id: d.ssh_target for d in data.devices if d.is_addressable}
        with console.status("Pinging nodes over SSH..."):
            by_host = asyncio.run(ping_many(list(targets.values())))
        reach = {dev_id: by_host[host] for dev_id, host in targets.items()}
    console.print(
        f"[bold]{data.fleet_name}[/bold] [dim]({state.path}, updated {data.updated_at})[/dim]"
    )
    console.print(fleet_table(data.devices, reach))


@app.command()
def show(
    ctx: typer.Context, node: Annotated[str, typer.Argument(help="Device id or hostname.")]
) -> None:
    """Show one device's inventory record."""
    device = _state(ctx).load().find(node)
    if device is None:
        raise FleetError(f"No device '{node}' in inventory.")
    console.print(device_detail(device))


@app.command()
def audit(
    ctx: typer.Context,
    nodes: Annotated[list[str] | None, typer.Argument(help="Device ids or SSH hosts.")] = None,
    all_: Annotated[
        bool, typer.Option("--all", "-a", help="Audit every addressable device.")
    ] = False,
    update: Annotated[
        bool, typer.Option("--update", "-u", help="Write measured changes to the inventory.")
    ] = False,
    add: Annotated[
        bool, typer.Option("--add", help="With --update, register nodes not yet in the inventory.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print raw audit results as JSON.")
    ] = False,
) -> None:
    """Audit node hardware/network/OS over SSH and diff against the inventory."""
    state = _state(ctx)
    data = state.load()
    if all_:
        targets = {d.id: d.ssh_target for d in data.devices if d.is_addressable}
    elif nodes:
        targets = {}
        for n in nodes:
            d = data.find(n)
            targets[d.id if d else n] = d.ssh_target if d else n
    else:
        raise typer.BadParameter("Give one or more nodes, or --all.")

    with console.status(f"Auditing {', '.join(targets)} ..."):
        by_host = asyncio.run(audit_many(list(targets.values())))
    results = {node: by_host[host] for node, host in targets.items()}

    if as_json:
        payload = {
            n: r.model_dump(mode="json") if isinstance(r, AuditResult) else {"error": str(r)}
            for n, r in results.items()
        }
        console.print_json(json.dumps(payload))
        return

    dirty = False
    failed = False
    for node, result in results.items():
        console.rule(f"[bold]{node}")
        if not isinstance(result, AuditResult):
            err.print(f"[red]{result}[/red]")
            failed = True
            continue
        console.print(audit_detail(result))
        console.print()
        if update:
            device, changes = reconcile(data, node, result, add_missing=add)
            if device is None:
                console.print(f"[yellow]{node} is not in the inventory; use --add to register it.")
                continue
            console.print(changes_table(changes, "applied" if changes else ""))
            dirty = dirty or bool(changes)
        else:
            existing = data.find(node)
            if existing is None:
                console.print(f"[yellow]{node} is not in the inventory (use --update --add).")
                continue
            changes = diff(existing, result)
            console.print(changes_table(changes, "pending (re-run with --update to apply)"))

    if dirty:
        inv.save(data, state.path)
        console.print(f"[green]Saved {state.path}")
    if failed:
        raise typer.Exit(1)


@app.command()
def discover(
    ctx: typer.Context,
    nodes: Annotated[
        list[str] | None,
        typer.Argument(help="Only consider these tailnet hostnames (default: all candidates)."),
    ] = None,
    add: Annotated[
        bool, typer.Option("--add", help="Audit new online Linux nodes and register them.")
    ] = False,
    user: Annotated[
        str | None,
        typer.Option("--user", "-u", help="SSH user for nodes being added, e.g. mstouffer."),
    ] = None,
    show_all: Annotated[
        bool, typer.Option("--all", "-a", help="Show every tailnet node, not just Linux ones.")
    ] = False,
) -> None:
    """Compare the Tailscale tailnet with the inventory; optionally register new nodes."""
    state = _state(ctx)
    data = state.load()
    tailnet = tailnet_nodes()
    wanted = {n.lower() for n in nodes or []}
    shown = [
        n
        for n in tailnet
        if (show_all or n.is_fleet_candidate) and (not wanted or n.name in wanted)
    ]
    matches = {n.name: match_device(data, n) for n in shown}
    console.print(tailnet_table(shown, {k: d.id if d else None for k, d in matches.items()}))

    new = [n for n in shown if n.is_fleet_candidate and matches[n.name] is None]
    if not add:
        if new:
            names = " ".join(n.name for n in new if n.online)
            console.print()
            console.print(f"[dim]Register with:[/dim] fr discover --add {names} \\[--user USER]")
        return

    offline = [n.name for n in new if not n.online]
    if offline:
        console.print(f"[yellow]Skipping offline: {', '.join(offline)}")
    targets = {n.name: f"{user}@{n.name}" if user else n.name for n in new if n.online}
    if not targets:
        console.print("Nothing to add.")
        return
    with console.status(f"Auditing {', '.join(targets)} ..."):
        by_host = asyncio.run(audit_many(list(targets.values())))

    added = []
    for node_id, host in targets.items():
        result = by_host[host]
        if not isinstance(result, AuditResult):
            err.print(f"[red]{node_id}: not added: {result}[/red]")
            continue
        reconcile(data, node_id, result, add_missing=True, ssh_host=host)
        added.append(node_id)
    if added:
        inv.save(data, state.path)
        console.print(f"[green]Added {', '.join(added)} to {state.path}")
    if len(added) < len(targets):
        raise typer.Exit(1)


@app.command("config")
def config_cmd(
    ctx: typer.Context,
    set_inventory: Annotated[
        Path | None,
        typer.Option("--inventory", help="Remember this devices.json for use anywhere."),
    ] = None,
    set_ssh: Annotated[
        str | None, typer.Option("--ssh", help="SSH client to use, e.g. ssh or ssh.exe.")
    ] = None,
) -> None:
    """Show or set user settings."""
    values = {k: str(v) for k, v in config.load_user_config().items()}
    if set_inventory:
        values["inventory"] = str(set_inventory.expanduser().resolve())
    if set_ssh:
        values["ssh"] = set_ssh
    if set_inventory or set_ssh:
        console.print(f"Saved {config.save_user_config(values)}")
    try:
        resolved = str(_state(ctx).path)
    except FleetError as e:
        resolved = f"[red]{e}[/red]"
    console.print(f"config file : {config.user_config_path()}")
    console.print(f"inventory   : {resolved}")
    console.print(f"ssh client  : {ssh_executable()}" + ("  [dim](WSL)[/dim]" if is_wsl() else ""))


@app.command()
def schema(
    ctx: typer.Context,
    write: Annotated[
        bool, typer.Option("--write", "-w", help="Write inventory/schema.json.")
    ] = False,
) -> None:
    """Print (or write) the JSON Schema for devices.json."""
    text = json.dumps(inv.json_schema(), indent=2) + "\n"
    if write:
        path = _state(ctx).path.parent / "schema.json"
        path.write_text(text, encoding="utf-8", newline="\n")
        console.print(f"Wrote {path}")
    else:
        console.print_json(text)


@app.command("allowlist")
def allowlist_cmd(
    ctx: typer.Context,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply", "-a", help="Apply baked rules to ~/.gemini/antigravity-cli/settings.json."
        ),
    ] = False,
) -> None:
    """Generate or apply Antigravity CLI auto-approval rules for fleet nodes."""
    from fleet_registry.core.allowlist import (
        apply_allowlist,
        generate_baked_rules,
        get_fleet_hosts,
    )

    state = _state(ctx)
    inventory = state.load()
    hosts = get_fleet_hosts(inventory)
    rules = generate_baked_rules(hosts)

    console.print(
        f"[bold green]Discovered {len(hosts)} fleet node identifiers/IPs:[/bold green] "
        f"{', '.join(hosts)}"
    )
    console.print(f"[bold cyan]Generated {len(rules)} generalized allowlist rules:[/bold cyan]")
    for r in rules:
        console.print(f"  [bold]{r['category']}:[/bold]\n    [dim]{r['rule']}[/dim]")

    if apply:
        path = apply_allowlist([r["rule"] for r in rules])
        console.print(f"\n[green]Applied rules to {path}[/green]")


@app.command()
def version() -> None:
    """Show installed, latest PyPI, and local project versions."""
    display_version_info(console, PACKAGE_NAME, upgrade_cmd=f"uv tool upgrade {PACKAGE_NAME}")


@app.command()
def tui(ctx: typer.Context) -> None:
    """Open the interactive fleet dashboard."""
    from fleet_registry.tui.app import FleetApp

    state = _state(ctx)
    FleetApp(state.path).run()


def main() -> None:
    try:
        app()
    except FleetError as e:
        err.print(f"[red]error:[/red] {e}")
        raise SystemExit(1) from None
