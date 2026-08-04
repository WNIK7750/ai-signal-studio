from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from start_app import (
    LOG_ROOT,
    PROJECT_ROOT,
    WEB_ROOT,
    port_available,
    ready,
    start_process,
    status,
    terminate_tree,
)


def main() -> int:
    api_port = 8010
    web_port = 3010
    if not port_available("127.0.0.1", api_port):
        status("ERROR", "API test port busy")
        return 1
    if not port_available("127.0.0.1", web_port):
        status("ERROR", "WEB test port busy")
        return 1

    node = shutil.which("node")
    next_cli = WEB_ROOT / "node_modules" / "next" / "dist" / "bin" / "next"
    playwright_cli = (
        WEB_ROOT / "node_modules" / "@playwright" / "test" / "cli.js"
    )
    if node is None or not next_cli.exists() or not playwright_cli.exists():
        status("ERROR", "Web test dependencies missing")
        return 1

    processes: list[subprocess.Popen[bytes]] = []
    logs: list[object] = []
    with tempfile.TemporaryDirectory(
        prefix="ai-signal-studio-e2e-",
        ignore_cleanup_errors=True,
    ) as temp:
        database_path = (Path(temp) / "e2e.db").as_posix()
        model_config_path = (Path(temp) / "models.local.json").as_posix()
        model_secrets_path = (
            Path(temp) / "model-secrets.local.json"
        ).as_posix()
        env = os.environ.copy()
        env.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "AI_SIGNAL_DATABASE_URL": f"sqlite:///{database_path}",
                "AI_SIGNAL_LLM_PROVIDER": "heuristic",
                "AI_SIGNAL_SOURCE_SEED_MODE": "demo",
                "AI_SIGNAL_MODEL_CONFIG_PATH": model_config_path,
                "AI_SIGNAL_MODEL_SECRETS_PATH": model_secrets_path,
                "AI_SIGNAL_CORS_ORIGINS": '["http://127.0.0.1:3010"]',
                "NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8010/api",
                "NEXT_DIST_DIR": ".next-e2e",
                "PLAYWRIGHT_EXTERNAL_SERVERS": "1",
            }
        )
        try:
            status("START", "E2E API")
            api, api_log = start_process(
                [
                    str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
                    "-m",
                    "uvicorn",
                    "ai_signal_api.main:app",
                    "--app-dir",
                    str(PROJECT_ROOT / "apps" / "api" / "src"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
                cwd=PROJECT_ROOT,
                env=env,
                log_name="e2e-api.log",
            )
            processes.append(api)
            logs.append(api_log)
            if not ready("http://127.0.0.1:8010/api/health", 25):
                status("ERROR", "E2E API - see logs/e2e-api.log")
                return 1
            status("READY", "E2E API")

            status("START", "E2E WEB")
            web, web_log = start_process(
                [
                    node,
                    str(next_cli),
                    "dev",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=WEB_ROOT,
                env=env,
                log_name="e2e-web.log",
            )
            processes.append(web)
            logs.append(web_log)
            if not ready("http://127.0.0.1:3010/timeline", 30):
                status("ERROR", "E2E WEB - see logs/e2e-web.log")
                return 1
            status("READY", "E2E WEB")

            LOG_ROOT.mkdir(parents=True, exist_ok=True)
            with (LOG_ROOT / "e2e.log").open("wb") as test_log:
                status("TEST", "Playwright")
                result = subprocess.run(
                    [
                        node,
                        str(playwright_cli),
                        "test",
                        "--config",
                        str(WEB_ROOT / "playwright.config.ts"),
                    ],
                    cwd=WEB_ROOT,
                    env=env,
                    stdout=test_log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            if result.returncode:
                status("ERROR", "Playwright - see logs/e2e.log")
                return result.returncode
            status("PASS", "Playwright")
            return 0
        finally:
            for process in reversed(processes):
                terminate_tree(process)
            for log in logs:
                log.close()


if __name__ == "__main__":
    raise SystemExit(main())
