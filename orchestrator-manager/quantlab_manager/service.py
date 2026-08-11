from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
import json
from typing import Any


LABEL = "com.asimovia.quantlab"
# The research loop is a SECOND agent, not a flag on the first. The monitor
# serves a page and must come back instantly; the loop runs a thirty-minute
# genetic search and must be allowed to finish one. Sharing a plist would mean
# every monitor restart killed an iteration mid-fit.
LOOP_LABEL = "com.asimovia.quantlab.loop"


def plist_path(label: str = LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def domain() -> str:
    return f"gui/{os.getuid()}"


def deploy_runtime(workspace: Path) -> Path:
    runtime = Path.home() / "Library" / "Application Support" / "QuantLab"
    runtime.mkdir(parents=True, exist_ok=True)
    for directory in (
        "backtester",
        "trading-system",
        "orchestrator-manager",
        # The monitor is a folder now, not a string inside this package, so the
        # runtime copy needs it explicitly or the daemon serves a "page not
        # found" placeholder while every API it depends on works perfectly.
        "monitor",
        ".meshkore/scripts",
    ):
        shutil.copytree(
            workspace / directory,
            runtime / directory,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    # Documentation moved into `.meshkore/` when the repository was restructured,
    # so this list named seven files that no longer exist and `service install`
    # died on the first one. Copy what is present and skip what is not: a
    # missing README must not be able to stop the daemon being reinstalled.
    for filename in (
        "README.md",
        "CONTRACT.md",
        "CONTRIBUTING.md",
        "pyproject.toml",
    ):
        source = workspace / filename
        if source.exists():
            shutil.copy2(source, runtime / filename)
    runtime_research = runtime / "research"
    if not runtime_research.exists():
        shutil.copytree(
            workspace / "research",
            runtime_research,
            ignore=shutil.ignore_patterns("*.log", "*.db-wal", "*.db-shm"),
        )
    return runtime


def _daemon_python() -> Path:
    """The Apple system interpreter starts reliably in a LaunchAgent session.

    The Homebrew 3.14 app-wrapper can remain suspended during interpreter
    startup, which looks exactly like a service that installed and then did
    nothing.
    """
    return (
        Path("/usr/bin/python3")
        if Path("/usr/bin/python3").exists()
        else Path(sys.executable)
    )


def _environment(workspace: Path, runtime: Path) -> dict[str, str]:
    """What a LaunchAgent needs that a login shell would have given it.

    Shared by both agents. A LaunchAgent gets no login-shell PATH, so the
    MeshKore Wall bridge could not find node and every public post failed
    silently -- include the newest nvm bin directory alongside the usual
    package-manager prefixes.
    """
    nvm = sorted(
        (Path.home() / ".nvm" / "versions" / "node").glob("*/bin"), reverse=True
    )
    search_path = ":".join(
        [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            *[str(path) for path in nvm[:1]],
            "/usr/bin",
            "/bin",
        ]
    )
    # Publish value: prefer the local credentials copy, fall back to the public
    # file the operator chose to keep in-tree so any contributor can publish
    # without a private hand-off. See .meshkore/public/MIRROR_PUBLISH.md.
    # Injected only into the LaunchAgent environment; the plist stays
    # owner-readable.
    publish_value = ""
    for candidate in (
        workspace / ".meshkore" / "credentials" / "public-mirror-token",
        workspace / ".meshkore" / "public" / "mirror-publish",
    ):
        if candidate.exists():
            publish_value = candidate.read_text().strip()
            if publish_value:
                break
    environment = {
        "PYTHONPATH": ":".join(
            str(runtime / part)
            for part in ("backtester", "trading-system", "orchestrator-manager")
        ),
        "PATH": search_path,
        "QUANTLAB_REPOSITORY_ROOT": str(workspace),
        "QUANTLAB_PUBLIC_LEDGER_ROOT": str(workspace / "research" / "public"),
    }
    if publish_value:
        environment["QUANTLAB_PUBLIC_MIRROR_TOKEN"] = publish_value
    # The refuter's key, on the same terms: a file under `credentials/`, which
    # is gitignored, read into the agent's environment and never into the
    # repository. Absent, the loop runs with the refuter simply off -- which is
    # a supported state and is announced in the startup banner.
    key = workspace / ".meshkore" / "credentials" / "zai-api-key"
    if key.exists():
        value = key.read_text().strip()
        if value:
            environment["ZAI_API_KEY"] = value
    return environment


def install(workspace: Path, config: Path) -> Path:
    runtime = deploy_runtime(workspace)
    config = runtime / "orchestrator-manager" / "config" / config.name
    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    logs = runtime / "research"
    logs.mkdir(parents=True, exist_ok=True)
    daemon_python = _daemon_python()
    environment = _environment(workspace, runtime)
    payload: dict[str, Any] = {
        "Label": LABEL,
        "ProgramArguments": [
            str(daemon_python),
            str(runtime / ".meshkore" / "scripts" / "run_daemon.py"),
            "--config",
            str(config),
            "monitor",
        ],
        "WorkingDirectory": str(runtime),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "service.stdout.log"),
        "StandardErrorPath": str(logs / "service.stderr.log"),
    }
    with target.open("wb") as handle:
        plistlib.dump(payload, handle)
    target.chmod(0o600)
    subprocess.run(["launchctl", "bootout", domain(), str(target)], capture_output=True)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain(), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")
    return target


def install_loop(
    workspace: Path, config: Path, generations: int = 4, population: int = 10
) -> Path:
    """Supervise the research loop, so it survives the session that started it.

    The operator's instruction is that it should not stop until they say stop,
    and until now it was a child of whatever shell launched it: closing a
    terminal ended the research. `KeepAlive` makes launchd own that promise --
    if the process exits for any reason, including a crash mid-iteration, it
    comes straight back and the loop picks up from the state file on disk.

    It runs the DEPLOYED copy under Application Support, like the monitor. A
    service that runs a working tree restarts into whatever was half-saved at
    the moment it died, which is the one state a supervised process must never
    be able to reach. State and ledger still live in the repository, because
    those are the research and they belong in git.
    """
    runtime = deploy_runtime(workspace)
    config = runtime / "orchestrator-manager" / "config" / config.name
    target = plist_path(LOOP_LABEL)
    target.parent.mkdir(parents=True, exist_ok=True)
    logs = runtime / "research"
    logs.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "Label": LOOP_LABEL,
        "ProgramArguments": [
            str(_daemon_python()),
            "-u",
            "-m",
            "quantlab_manager",
            "--config",
            str(config),
            "loop",
            "--generations",
            str(generations),
            "--population",
            str(population),
        ],
        "WorkingDirectory": str(runtime),
        "EnvironmentVariables": _environment(workspace, runtime),
        "RunAtLoad": True,
        "KeepAlive": True,
        # Long, deliberately. A loop that dies on startup should retry slowly
        # enough that a person can read the log, not spin the backtester and
        # the Wall into a hot restart.
        "ThrottleInterval": 60,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "loop.stdout.log"),
        "StandardErrorPath": str(logs / "loop.stderr.log"),
    }
    with target.open("wb") as handle:
        plistlib.dump(payload, handle)
    target.chmod(0o600)
    subprocess.run(["launchctl", "bootout", domain(), str(target)], capture_output=True)
    result = subprocess.run(
        ["launchctl", "bootstrap", domain(), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "launchctl bootstrap failed")
    return target


def start() -> None:
    target = plist_path()
    running, _ = status()
    command = (
        ["launchctl", "kickstart", "-k", f"{domain()}/{LABEL}"]
        if running
        else ["launchctl", "bootstrap", domain(), str(target)]
    )
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "launchctl kickstart failed")


def stop() -> None:
    result = subprocess.run(
        ["launchctl", "bootout", domain(), str(plist_path())],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "launchctl bootout failed")


def status(label: str = LABEL) -> tuple[bool, str]:
    result = subprocess.run(
        ["launchctl", "print", f"{domain()}/{label}"], capture_output=True, text=True
    )
    # `launchctl print` dumps several hundred lines. The caller wants "is it
    # up", and the state line is the one that answers it.
    detail = result.stdout if result.returncode == 0 else result.stderr
    for line in detail.splitlines():
        if line.strip().startswith("state ="):
            detail = line.strip()
            break
    return result.returncode == 0, detail.strip()[:200]


def run(action: str, config: Path) -> int:
    """Dispatch for the `service` subcommand."""
    workspace = Path(__file__).resolve().parents[2]
    if action == "install":
        print(json.dumps({"installed": str(install(workspace, config))}, indent=2))
        return 0
    if action == "install-loop":
        print(json.dumps({"installed": str(install_loop(workspace, config))}, indent=2))
        return 0
    if action == "uninstall":
        stop()
        plist_path().unlink(missing_ok=True)
        print("uninstalled")
        return 0
    if action == "uninstall-loop":
        subprocess.run(
            ["launchctl", "bootout", domain(), str(plist_path(LOOP_LABEL))],
            capture_output=True,
        )
        plist_path(LOOP_LABEL).unlink(missing_ok=True)
        print("loop uninstalled")
        return 0
    running, detail = status()
    loop_running, loop_detail = status(LOOP_LABEL)
    print(
        json.dumps(
            {
                "monitor": {"running": running, "detail": detail},
                "loop": {"running": loop_running, "detail": loop_detail},
            },
            indent=2,
        )
    )
    return 0 if running else 1
