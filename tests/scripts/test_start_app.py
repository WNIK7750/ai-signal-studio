from __future__ import annotations

import importlib.util
import io
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
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "start_app.py",
            "--no-browser",
            "--smoke-test",
        ],
    )
    monkeypatch.setattr(start_app, "port_available", lambda _host, _port: False)
    monkeypatch.setattr(
        start_app,
        "api_ready",
        lambda _url, _timeout: True,
        raising=False,
    )
    monkeypatch.setattr(
        start_app,
        "web_ready",
        lambda _url, _timeout: True,
        raising=False,
    )

    assert start_app.main() == 0
    output = capsys.readouterr().out
    assert "E0000（应用已在运行）" in output
    assert "[ATTACH] API http://127.0.0.1:8000" in output
    assert "[ATTACH] WEB http://127.0.0.1:3000" in output


def test_existing_healthy_instance_keeps_the_launcher_open(
    monkeypatch,
    capsys,
) -> None:
    start_app = load_start_app()
    monkeypatch.setattr(sys, "argv", ["start_app.py", "--no-browser"])
    monkeypatch.setattr(start_app, "port_available", lambda _host, _port: False)
    monkeypatch.setattr(
        start_app,
        "api_ready",
        lambda _url, _timeout: True,
    )
    monkeypatch.setattr(
        start_app,
        "web_ready",
        lambda _url, _timeout: True,
    )
    entered_monitor = False

    def stop_monitor(_seconds: float) -> None:
        nonlocal entered_monitor
        entered_monitor = True
        raise KeyboardInterrupt

    monkeypatch.setattr(start_app.time, "sleep", stop_monitor)

    assert start_app.main() == 0
    output = capsys.readouterr().out
    assert entered_monitor
    assert "[RUNNING] Press Ctrl+C to stop" in output
    assert "[STOP] Services" in output


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


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return self._body.read()


def test_health_checks_require_ai_signal_studio_signatures(monkeypatch) -> None:
    start_app = load_start_app()
    monkeypatch.setattr(
        start_app.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            b'{"status":"not-our-api"}'
        ),
    )
    assert not start_app.api_ready("http://127.0.0.1:8000/api/health", 0.1)

    monkeypatch.setattr(
        start_app.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            b"<html><title>Another app</title></html>"
        ),
    )
    assert not start_app.web_ready("http://127.0.0.1:3000/timeline", 0.1)

    monkeypatch.setattr(
        start_app.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            (
                '{"status":"ok","workflow_version":"'
                f'{start_app.EXPECTED_WORKFLOW_VERSION}'
                '"}'
            ).encode()
        ),
    )
    assert start_app.api_ready("http://127.0.0.1:8000/api/health", 0.1)

    monkeypatch.setattr(
        start_app.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            b'{"status":"ok","workflow_version":"0.4.0"}'
        ),
    )
    assert not start_app.api_ready(
        "http://127.0.0.1:8000/api/health",
        0.1,
    )

    monkeypatch.setattr(
        start_app.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            b"<html><title>AI Signal Studio</title></html>"
        ),
    )
    assert start_app.web_ready("http://127.0.0.1:3000/timeline", 0.1)


def test_repair_refuses_to_stop_an_unrelated_port_owner(monkeypatch) -> None:
    start_app = load_start_app()
    stopped: list[int] = []
    monkeypatch.setattr(
        start_app,
        "listening_pids",
        lambda port: {4100 + port},
        raising=False,
    )
    monkeypatch.setattr(
        start_app,
        "project_service_root",
        lambda _pid, _service: None,
        raising=False,
    )
    monkeypatch.setattr(
        start_app,
        "terminate_pid_tree",
        stopped.append,
        raising=False,
    )

    repaired = start_app.repair_project_port_conflicts(
        {"api": 8000, "web": 3000}
    )

    assert not repaired
    assert stopped == []


def test_repair_stops_only_recognized_project_service_roots(
    monkeypatch,
) -> None:
    start_app = load_start_app()
    stopped: list[int] = []
    busy = {8000: {501}, 3000: {601}}
    roots = {(501, "api"): 500, (601, "web"): 600}
    monkeypatch.setattr(
        start_app,
        "listening_pids",
        lambda port: busy.get(port, set()),
        raising=False,
    )
    monkeypatch.setattr(
        start_app,
        "project_service_root",
        lambda pid, service: roots.get((pid, service)),
        raising=False,
    )
    monkeypatch.setattr(
        start_app,
        "terminate_pid_tree",
        stopped.append,
        raising=False,
    )
    monkeypatch.setattr(
        start_app,
        "wait_for_ports",
        lambda _ports, _timeout: True,
        raising=False,
    )

    repaired = start_app.repair_project_port_conflicts(
        {"api": 8000, "web": 3000}
    )

    assert repaired
    assert stopped == [500, 600]


def test_api_reload_orphan_is_recognized_from_its_listener_parent(
    monkeypatch,
) -> None:
    start_app = load_start_app()
    monkeypatch.setattr(
        start_app,
        "windows_process_info",
        lambda _pid: None,
    )
    monkeypatch.setattr(
        start_app,
        "windows_child_process_infos",
        lambda parent_pid: [
            {
                "ProcessId": 7660,
                "ParentProcessId": parent_pid,
                "Name": "python.exe",
                "CommandLine": (
                    "python -c \"from multiprocessing.spawn import "
                    f"spawn_main; spawn_main(parent_pid={parent_pid})\""
                ),
            }
        ],
        raising=False,
    )

    assert start_app.project_service_root(22660, "api") == 7660


def test_healthy_partial_instance_is_reused_when_repair_is_unavailable(
    monkeypatch,
    capsys,
) -> None:
    start_app = load_start_app()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "start_app.py",
            "--no-browser",
            "--smoke-test",
        ],
    )
    monkeypatch.setattr(
        start_app,
        "port_available",
        lambda _host, port: port == 3000,
    )
    monkeypatch.setattr(
        start_app,
        "api_ready",
        lambda _url, _timeout: True,
    )
    monkeypatch.setattr(
        start_app,
        "web_ready",
        lambda _url, _timeout: True,
    )
    monkeypatch.setattr(
        start_app,
        "repair_project_port_conflicts",
        lambda _services: False,
    )
    commands: list[list[str]] = []

    class FakeProcess:
        def poll(self):
            return None

    def fake_start_process(command, **_kwargs):
        commands.append(command)
        return FakeProcess(), io.BytesIO()

    monkeypatch.setattr(start_app, "start_process", fake_start_process)
    monkeypatch.setattr(start_app, "terminate_tree", lambda _process: None)

    assert start_app.main() == 0
    output = capsys.readouterr().out
    assert "[ATTACH] API http://127.0.0.1:8000" in output
    assert len(commands) == 1
    assert "next" in " ".join(commands[0]).casefold()
