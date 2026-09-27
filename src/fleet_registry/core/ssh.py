"""Run commands on fleet nodes through the system OpenSSH client.

Shelling out (rather than using an SSH library) reuses ``~/.ssh/config`` host
aliases and whatever agent the client already talks to. Under WSL the Windows
``ssh.exe`` is preferred so the 1Password / Windows Hello agent on the
``\\\\.\\pipe\\openssh-ssh-agent`` named pipe works without a socket bridge.
Override with ``$FLEET_SSH`` or ``ssh`` in the user config.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from fleet_registry.core import FleetError
from fleet_registry.core.config import ENV_SSH, load_user_config


class SshError(FleetError):
    pass


@dataclass(frozen=True)
class SshResult:
    host: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@cache
def is_wsl() -> bool:
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    except OSError:
        return False


def _windows_openssh() -> str | None:
    """Path to the Windows OpenSSH client (the one that talks to the named-pipe agent).

    Prefer it over whatever ``ssh.exe`` is first on PATH, which is often Git for
    Windows' MSYS build and ignores the Windows agent.
    """
    if sys.platform == "win32":
        root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    elif is_wsl():
        root = Path("/mnt/c/Windows")
    else:
        return None
    candidate = root / "System32" / "OpenSSH" / "ssh.exe"
    return str(candidate) if candidate.is_file() else None


def ssh_executable() -> str:
    if env := os.environ.get(ENV_SSH):
        return env
    if configured := load_user_config().get("ssh"):
        return str(configured)
    if win := _windows_openssh():
        return win
    if is_wsl() and shutil.which("ssh.exe"):
        return "ssh.exe"
    return "ssh"


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")


async def run_script(
    host: str,
    script: str,
    *,
    timeout: float = 60,
    connect_timeout: int = 10,
    ssh: str | None = None,
) -> SshResult:
    """Run a bash script on ``host`` by piping it to ``bash -s`` (no quoting pitfalls)."""
    exe = ssh or ssh_executable()
    argv = [
        exe,
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={connect_timeout}",
        host,
        "bash -s",
    ]  # fmt: skip
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise SshError(f"SSH client '{exe}' not found on PATH (set ${ENV_SSH}).") from e
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(script.replace("\r\n", "\n").encode()), timeout
        )
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise SshError(f"{host}: timed out after {timeout:.0f}s") from e
    rc = proc.returncode if proc.returncode is not None else -1
    return SshResult(host, rc, _decode(out), _decode(err))


async def ping(host: str, *, timeout: float = 15) -> bool:
    """True if an SSH session to ``host`` can be opened non-interactively."""
    try:
        result = await run_script(host, "true\n", timeout=timeout, connect_timeout=5)
    except SshError:
        return False
    return result.ok


async def ping_many(hosts: list[str]) -> dict[str, bool]:
    results = await asyncio.gather(*(ping(h) for h in hosts))
    return dict(zip(hosts, results, strict=True))
