from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "start_app.py"


def load_start_app():
    spec = importlib.util.spec_from_file_location("start_app_under_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_healthy_instance_is_a_success(monkeypatch, capsys) -> None:
    start_app = load_start_app()
    monkeypatch.setattr(sys, "argv", ["start_app.py", "--no-browser"])
    monkeypatch.setattr(start_app, "port_available", lambda _host, _port: False)
    monkeypatch.setattr(start_app, "ready", lambda _url, _timeout: True)

    assert start_app.main() == 0
    assert "E0000（应用已在运行）" in capsys.readouterr().out


def test_missing_python_reports_numbered_chinese_error(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    start_app = load_start_app()
    monkeypatch.setattr(sys, "argv", ["start_app.py", "--no-browser"])
    monkeypatch.setattr(start_app, "API_PYTHON", tmp_path / "missing-python.exe")

    assert start_app.main() == 1
    assert "E1001（后端虚拟环境不存在）" in capsys.readouterr().out
