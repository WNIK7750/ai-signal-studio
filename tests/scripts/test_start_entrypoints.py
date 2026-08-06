from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = (
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32"
    / "WindowsPowerShell"
    / "v1.0"
    / "powershell.exe"
)


@pytest.mark.skipif(os.name != "nt", reason="Windows launch entrypoints")
def test_direct_powershell_failure_keeps_diagnostics_visible() -> None:
    completed = subprocess.run(
        [
            str(POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "start.ps1"),
            "--api-port",
            "70000",
        ],
        cwd=PROJECT_ROOT,
        input="\n",
        capture_output=True,
        text=True,
        errors="replace",
        timeout=20,
        check=False,
    )

    assert completed.returncode != 0
    assert "[PAUSE]" in completed.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows launch entrypoints")
def test_powershell_no_pause_mode_is_automation_safe() -> None:
    completed = subprocess.run(
        [
            str(POWERSHELL),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PROJECT_ROOT / "start.ps1"),
            "--no-pause",
            "--api-port",
            "70000",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=20,
        check=False,
    )

    assert completed.returncode != 0
    assert "[PAUSE]" not in completed.stdout
