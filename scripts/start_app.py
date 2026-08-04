from __future__ import annotations

import argparse
import os
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
API_PYTHON = (
    PROJECT_ROOT
    / ".venv"
    / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
)


def status(stage: str, service: str) -> None:
    print(f"[{stage}] {service}", flush=True)


def port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex((host, port)) != 0


def ready(url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.2) as response:
                if response.status < 500:
                    return True
        except (OSError, TimeoutError):
            time.sleep(0.35)
    return False


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
    log_file = (LOG_ROOT / log_name).open("ab", buffering=0)
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


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(add_help=True)
    value.add_argument("--host", default="127.0.0.1")
    value.add_argument("--api-port", type=int, default=8000)
    value.add_argument("--web-port", type=int, default=3000)
    value.add_argument("--production", action="store_true")
    value.add_argument("--no-browser", action="store_true")
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

    api_url = f"http://{args.host}:{args.api_port}"
    web_url = f"http://{args.host}:{args.web_port}"
    api_port_free = port_available(args.host, args.api_port)
    web_port_free = port_available(args.host, args.web_port)
    if not api_port_free and not web_port_free:
        if ready(f"{api_url}/api/health", 2) and ready(
            f"{web_url}/timeline",
            2,
        ):
            status("READY", f"E0000（应用已在运行）{web_url}")
            if not args.no_browser:
                webbrowser.open(web_url)
            return 0
    if not api_port_free:
        status(
            "ERROR",
            f"E1003（后端端口 {args.api_port} 已被其他程序占用）",
        )
        return 1
    if not web_port_free:
        status(
            "ERROR",
            f"E1004（前端端口 {args.web_port} 已被其他程序占用）",
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
        if not args.production:
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

        if not ready(f"{api_url}/api/health", 25):
            status("ERROR", "E1005（后端启动失败）请查看 logs/api.log")
            return 1
        status("READY", f"API {api_url}")

        status("START", "WEB")
        mode = "start" if args.production else "dev"
        if args.production and not (WEB_ROOT / ".next" / "BUILD_ID").exists():
            status("ERROR", "E1006（前端生产构建不存在）")
            return 1
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

        if not ready(f"{web_url}/timeline", 30):
            status("ERROR", "E1007（前端启动失败）请查看 logs/web.log")
            return 1
        status("READY", f"WEB {web_url}")

        if not args.no_browser:
            webbrowser.open(web_url)

        status("RUNNING", "Press Ctrl+C to stop")
        while True:
            for process in processes:
                if process.poll() is not None:
                    status("ERROR", "E1008（应用服务意外停止）请查看 logs/")
                    return process.returncode or 1
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
