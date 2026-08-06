from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
import webbrowser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "apps" / "web"
LOG_ROOT = PROJECT_ROOT / "logs"
GRAPH_SPEC_PATH = (
    PROJECT_ROOT
    / "graph-specs"
    / "02-module-review-agent"
    / "02-agent-task-graph.yaml"
)
API_PYTHON = (
    PROJECT_ROOT
    / ".venv"
    / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
)


def expected_workflow_version() -> str:
    try:
        graph_spec = GRAPH_SPEC_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(
        r"^workflow_version:\s*([^\s#]+)",
        graph_spec,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


EXPECTED_WORKFLOW_VERSION = expected_workflow_version()


def status(stage: str, service: str) -> None:
    print(f"[{stage}] {service}", flush=True)


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        try:
            return probe.connect_ex((host, port)) != 0
        except OSError:
            return False


def ready(
    url: str,
    timeout_seconds: float,
    validator: Callable[[bytes], bool] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.2) as response:
                body = response.read()
                if response.status == 200 and (
                    validator is None or validator(body)
                ):
                    return True
        except (OSError, TimeoutError):
            time.sleep(0.35)
    return False


def api_ready(url: str, timeout_seconds: float) -> bool:
    def valid_health(body: bytes) -> bool:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return (
            payload.get("status") == "ok"
            and payload.get("workflow_version")
            == EXPECTED_WORKFLOW_VERSION
        )

    return ready(url, timeout_seconds, valid_health)


def web_ready(url: str, timeout_seconds: float) -> bool:
    def valid_page(body: bytes) -> bool:
        try:
            html = body.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return bool(
            re.search(
                r"<title>\s*AI Signal Studio\s*</title>",
                html,
                re.IGNORECASE,
            )
        )

    return ready(url, timeout_seconds, valid_page)


def listening_pids(port: int) -> set[int]:
    if os.name != "nt":
        return set()
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    listeners: set[int] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if (
            len(parts) < 5
            or parts[0].upper() != "TCP"
            or parts[-2].upper() != "LISTENING"
            or not parts[-1].isdigit()
        ):
            continue
        local_address = parts[1]
        try:
            local_port = int(local_address.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if local_port == port:
            listeners.add(int(parts[-1]))
    return listeners


def windows_process_info(pid: int) -> dict[str, object] | None:
    if os.name != "nt":
        return None
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    if not powershell.exists():
        return None
    script = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' "
        "-ErrorAction SilentlyContinue;"
        "if ($null -ne $p) {"
        "$p | Select-Object ProcessId,ParentProcessId,Name,"
        "ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        "}"
    )
    result = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def windows_child_process_infos(
    parent_pid: int,
) -> list[dict[str, object]]:
    if os.name != "nt":
        return []
    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    if not powershell.exists():
        return []
    script = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        "$p=Get-CimInstance Win32_Process -Filter "
        f"'ParentProcessId = {parent_pid}' "
        "-ErrorAction SilentlyContinue;"
        "if ($null -ne $p) {"
        "@($p | Select-Object ProcessId,ParentProcessId,Name,"
        "ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
        "}"
    )
    result = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        return []
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)]


def project_service_root(pid: int, service: str) -> int | None:
    project_marker = str(PROJECT_ROOT).casefold()
    current_pid = pid
    root_pid: int | None = None
    visited: set[int] = set()
    for _ in range(10):
        if current_pid in visited:
            break
        visited.add(current_pid)
        info = windows_process_info(current_pid)
        if info is None:
            if service == "api" and root_pid is None:
                reload_children = []
                for child in windows_child_process_infos(current_pid):
                    command_line = str(
                        child.get("CommandLine") or ""
                    ).casefold()
                    process_name = str(
                        child.get("Name") or ""
                    ).casefold()
                    if (
                        process_name in {"python.exe", "python"}
                        and "multiprocessing.spawn" in command_line
                        and f"parent_pid={current_pid}" in command_line
                    ):
                        reload_children.append(
                            int(child.get("ProcessId") or 0)
                        )
                reload_children = [
                    child_pid
                    for child_pid in reload_children
                    if child_pid > 0
                ]
                if len(reload_children) == 1:
                    return reload_children[0]
            break
        command_line = str(info.get("CommandLine") or "").casefold()
        service_marker = (
            "uvicorn" in command_line
            if service == "api"
            else (
                "next" in command_line
                and (
                    "apps\\web" in command_line
                    or "apps/web" in command_line
                    or project_marker in command_line
                )
            )
        )
        if project_marker not in command_line or not service_marker:
            break
        root_pid = current_pid
        parent_pid = int(info.get("ParentProcessId") or 0)
        if parent_pid <= 0:
            break
        current_pid = parent_pid
    return root_pid


def terminate_pid_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def wait_for_ports(ports: list[int], timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if all(port_available("127.0.0.1", port) for port in ports):
            return True
        time.sleep(0.25)
    return False


def repair_project_port_conflicts(services: dict[str, int]) -> bool:
    roots: list[int] = []
    seen: set[int] = set()
    for service, port in services.items():
        owners = listening_pids(port)
        if not owners:
            return False
        for owner in sorted(owners):
            root = project_service_root(owner, service)
            if root is None:
                return False
            if root not in seen:
                seen.add(root)
                roots.append(root)
    status(
        "REPAIR",
        "E0001（检测到本项目残留或半启动进程，正在安全重启）",
    )
    for root in roots:
        terminate_pid_tree(root)
    return wait_for_ports(list(services.values()), 8)


def port_owner_suffix(port: int) -> str:
    owners = sorted(listening_pids(port))
    return f"；PID {', '.join(map(str, owners))}" if owners else ""


def terminate_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    else:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def start_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_name: str,
) -> tuple[subprocess.Popen[bytes], object]:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log_file = (LOG_ROOT / log_name).open("wb", buffering=0)
    log_file.write(
        (
            f"=== AI Signal Studio launch "
            f"{datetime.now().isoformat(timespec='seconds')} ===\n"
        ).encode("utf-8")
    )
    creationflags = (
        subprocess.CREATE_NO_WINDOW
        if os.name == "nt"
        else 0
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return process, log_file


def print_log_tail(log_name: str, line_count: int = 14) -> None:
    path = LOG_ROOT / log_name
    if not path.exists():
        return
    try:
        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return
    if not lines:
        return
    status("DETAIL", f"{path.relative_to(PROJECT_ROOT)} 最后输出：")
    for line in lines[-line_count:]:
        print(f"  {line}", flush=True)


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("端口必须是整数") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 1 到 65535 之间")
    return port


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(add_help=True)
    value.add_argument("--host", default="127.0.0.1")
    value.add_argument("--api-port", type=valid_port, default=8000)
    value.add_argument("--web-port", type=valid_port, default=3000)
    value.add_argument("--production", action="store_true")
    value.add_argument(
        "--reload",
        action="store_true",
        help="enable Uvicorn source reload for an interactive dev session",
    )
    value.add_argument("--no-browser", action="store_true")
    value.add_argument(
        "--smoke-test",
        action="store_true",
        help="start both services, verify readiness, then stop them",
    )
    value.add_argument(
        "--no-repair",
        action="store_true",
        help="do not stop stale processes that are verified as this project",
    )
    return value


def main() -> int:
    args = parser().parse_args()
    status("CHECK", "Runtime")

    node = shutil.which("node")
    next_cli = WEB_ROOT / "node_modules" / "next" / "dist" / "bin" / "next"
    if not API_PYTHON.exists():
        status("ERROR", "E1001（后端虚拟环境不存在）请先运行 setup.cmd")
        return 1
    if node is None or not next_cli.exists():
        status("ERROR", "E1002（前端运行环境不存在）请先运行 setup.cmd")
        return 1
    if args.production and not (WEB_ROOT / ".next" / "BUILD_ID").exists():
        status("ERROR", "E1006（前端生产构建不存在）")
        return 1
    try:
        socket.getaddrinfo(args.host, None)
    except socket.gaierror:
        status("ERROR", f"E1009（主机地址无效）{args.host}")
        return 1

    api_url = f"http://{args.host}:{args.api_port}"
    web_url = f"http://{args.host}:{args.web_port}"
    api_port_free = port_available(args.host, args.api_port)
    web_port_free = port_available(args.host, args.web_port)
    existing_api = not api_port_free and api_ready(
        f"{api_url}/api/health", 2
    )
    existing_web = not web_port_free and web_ready(
        f"{web_url}/timeline", 2
    )
    fully_existing = existing_api and existing_web
    if existing_api and existing_web:
        status("READY", f"E0000（应用已在运行）{web_url}")
    busy_services: dict[str, int] = {}
    if not fully_existing:
        if not api_port_free:
            busy_services["api"] = args.api_port
        if not web_port_free:
            busy_services["web"] = args.web_port
    if (
        busy_services
        and not args.no_repair
        and repair_project_port_conflicts(busy_services)
    ):
        api_port_free = port_available(args.host, args.api_port)
        web_port_free = port_available(args.host, args.web_port)
        existing_api = not api_port_free and api_ready(
            f"{api_url}/api/health",
            2,
        )
        existing_web = not web_port_free and web_ready(
            f"{web_url}/timeline",
            2,
        )
    if not api_port_free and not existing_api:
        status(
            "ERROR",
            (
                f"E1003（后端端口 {args.api_port} 已被其他程序占用"
                f"{port_owner_suffix(args.api_port)}）"
            ),
        )
        return 1
    if not web_port_free and not existing_web:
        status(
            "ERROR",
            (
                f"E1004（前端端口 {args.web_port} 已被其他程序占用"
                f"{port_owner_suffix(args.web_port)}）"
            ),
        )
        return 1

    processes: list[subprocess.Popen[bytes]] = []
    logs: list[object] = []
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "AI_SIGNAL_CORS_ORIGINS": f'["{web_url}"]',
            "NEXT_PUBLIC_API_BASE_URL": f"{api_url}/api",
        }
    )

    try:
        if existing_api:
            status("ATTACH", f"API {api_url}")
        else:
            status("START", "API")
            api_command = [
                str(API_PYTHON),
                "-m",
                "uvicorn",
                "ai_signal_api.main:app",
                "--app-dir",
                str(PROJECT_ROOT / "apps" / "api" / "src"),
                "--host",
                args.host,
                "--port",
                str(args.api_port),
            ]
            if args.reload and not args.production:
                api_command.extend(
                    [
                        "--reload",
                        "--reload-dir",
                        str(PROJECT_ROOT / "apps" / "api" / "src"),
                    ]
                )
            process, log = start_process(
                api_command,
                cwd=PROJECT_ROOT,
                env=env,
                log_name="api.log",
            )
            processes.append(process)
            logs.append(log)

            if not api_ready(f"{api_url}/api/health", 25):
                status(
                    "ERROR",
                    "E1005（后端启动失败）请查看 logs/api.log",
                )
                print_log_tail("api.log")
                return 1
            status("READY", f"API {api_url}")

        if existing_web:
            status("ATTACH", f"WEB {web_url}")
        else:
            status("START", "WEB")
            mode = "start" if args.production else "dev"
            process, log = start_process(
                [
                    node,
                    str(next_cli),
                    mode,
                    "--hostname",
                    args.host,
                    "--port",
                    str(args.web_port),
                ],
                cwd=WEB_ROOT,
                env=env,
                log_name="web.log",
            )
            processes.append(process)
            logs.append(log)

            if not web_ready(f"{web_url}/timeline", 30):
                status(
                    "ERROR",
                    "E1007（前端启动失败）请查看 logs/web.log",
                )
                print_log_tail("web.log")
                return 1
            status("READY", f"WEB {web_url}")

        if args.smoke_test:
            status("PASS", "E0002（启动冒烟测试通过，正在停止测试服务）")
            return 0

        if not args.no_browser:
            webbrowser.open(web_url)

        status("RUNNING", "Press Ctrl+C to stop")
        next_attached_health_check = time.monotonic() + 3
        while True:
            for process in processes:
                if process.poll() is not None:
                    status("ERROR", "E1008（应用服务意外停止）请查看 logs/")
                    return process.returncode or 1
            if time.monotonic() >= next_attached_health_check:
                if existing_api and not api_ready(
                    f"{api_url}/api/health",
                    1,
                ):
                    status("ERROR", "E1010（复用的后端服务已停止）")
                    return 1
                if existing_web and not web_ready(
                    f"{web_url}/timeline",
                    1,
                ):
                    status("ERROR", "E1011（复用的前端服务已停止）")
                    return 1
                next_attached_health_check = time.monotonic() + 3
            time.sleep(0.8)
    except KeyboardInterrupt:
        status("STOP", "Services")
        return 0
    finally:
        for process in reversed(processes):
            terminate_tree(process)
        for log in logs:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
