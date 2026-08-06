from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


LABEL = "com.asimovia.quantlab"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def domain() -> str:
    return f"gui/{os.getuid()}"


def deploy_runtime(workspace: Path) -> Path:
    runtime = Path.home() / "Library" / "Application Support" / "QuantLab"
    runtime.mkdir(parents=True, exist_ok=True)
    for directory in (
        "backtester",
        "trading-system",
        "orchestrator-manager",
        "scripts",
        "config",
        "schemas",
    ):
        shutil.copytree(
            workspace / directory,
            runtime / directory,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for filename in (
        "ARCHITECTURE.md",
        "ROADMAP.md",
        "README.md",
        "AUTONOMOUS_DEVELOPMENT.md",
        "ADVERSARIAL_REVIEW.md",
        "SYSTEM_CRITERIA.md",
        "RESEARCH_CHARTER.md",
        "SECURITY_REVIEW.md",
        "pyproject.toml",
    ):
        shutil.copy2(workspace / filename, runtime / filename)
    runtime_research = runtime / "research"
    if not runtime_research.exists():
        shutil.copytree(
            workspace / "research",
            runtime_research,
            ignore=shutil.ignore_patterns("*.log", "*.db-wal", "*.db-shm"),
        )
    return runtime


def install(workspace: Path, config: Path) -> Path:
    runtime = deploy_runtime(workspace)
    config = runtime / "config" / config.name
    target = plist_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    logs = runtime / "research"
    logs.mkdir(parents=True, exist_ok=True)
    # The Apple system interpreter starts reliably in a LaunchAgent session. The
    # Homebrew 3.14 app-wrapper can remain suspended during interpreter startup.
    daemon_python = (
        Path("/usr/bin/python3")
        if Path("/usr/bin/python3").exists()
        else Path(sys.executable)
    )
    # A LaunchAgent gets no login-shell PATH, so the MeshKore Wall bridge could
    # not find node and every public post failed silently. Include the newest
    # nvm bin directory alongside the usual package-manager prefixes.
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
    # Monitor publish value: prefer the local credentials copy, fall back to
    # the public file the operator chose to keep in-tree so any contributor
    # can publish without a private hand-off. See
    # .meshkore/public/MIRROR_PUBLISH.md. Injected only into the LaunchAgent
    # environment; the plist stays owner-readable.
    token_path = workspace / ".meshkore" / "credentials" / "public-mirror-token"
    public_publish = workspace / ".meshkore" / "public" / "mirror-publish"
    publish_value = ""
    for candidate in (token_path, public_publish):
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
    payload: dict[str, Any] = {
        "Label": LABEL,
        "ProgramArguments": [
            str(daemon_python),
            str(runtime / "scripts" / "run_daemon.py"),
            "--config",
            str(config),
            "daemon",
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


def status() -> tuple[bool, str]:
    result = subprocess.run(
        ["launchctl", "print", f"{domain()}/{LABEL}"], capture_output=True, text=True
    )
    return (
        result.returncode == 0,
        result.stdout if result.returncode == 0 else result.stderr,
    )
