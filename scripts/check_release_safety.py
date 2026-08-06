from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_SCAN_BYTES = 2_000_000
LOCAL_SEGMENTS = {
    "data",
    "logs",
    "artifacts",
    "uploads",
    "exports",
    "backups",
}
LOCAL_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
MEDIA_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".har",
    ".zip",
}
MEDIA_ALLOW_PREFIXES = (
    "docs/05-platform/assets/",
    "apps/web/public/",
)
CONTENT_RULES = (
    (
        "SECRET_PRIVATE_KEY",
        re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    (
        "SECRET_PROVIDER_TOKEN",
        re.compile(
            rb"(?:sk-(?=[A-Za-z0-9_-]{20,})"
            rb"(?=[A-Za-z0-9_-]*[0-9])[A-Za-z0-9_-]{20,}|"
            rb"gh[pousr]_[A-Za-z0-9]{20,}|"
            rb"AKIA[A-Z0-9]{16})"
        ),
    ),
    (
        "SECRET_AUTH_HEADER",
        re.compile(
            rb"(?i)authorization\s*:\s*(?:bearer|basic)\s+[^\s\"']+"
        ),
    ),
    (
        "SECRET_CREDENTIAL_URL",
        re.compile(rb"https?://[^/\s:@]+:[^/\s@]+@"),
    ),
    (
        "LOCAL_ABSOLUTE_PATH",
        re.compile(
            rb"(?i)(?:[A-Z]:\\Users\\[^\\\r\n]+|"
            rb"/(?:home|Users)/[^/\s]+/)"
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int


def _git(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git command failed: {message}")
    return result.stdout


def _path_findings(path: str) -> list[Finding]:
    normalized = path.replace("\\", "/").lstrip("./")
    pure = PurePosixPath(normalized)
    lower_parts = {part.lower() for part in pure.parts}
    lower_name = pure.name.lower()
    findings: list[Finding] = []
    if (
        lower_parts.intersection(LOCAL_SEGMENTS)
        or "agent-packs/local/" in f"{normalized.lower()}/"
        or ".local.json" in lower_name
        or lower_name == ".env"
        or (
            lower_name.startswith(".env.")
            and lower_name != ".env.example"
        )
        or pure.suffix.lower() in LOCAL_SUFFIXES
        or ".db-" in lower_name
    ):
        findings.append(Finding("LOCAL_PATH_FORBIDDEN", normalized, 1))
    if (
        pure.suffix.lower() in MEDIA_SUFFIXES
        and not normalized.startswith(MEDIA_ALLOW_PREFIXES)
    ):
        findings.append(Finding("MEDIA_NOT_APPROVED", normalized, 1))
    return findings


def _content_findings(path: str, content: bytes) -> list[Finding]:
    if b"\0" in content[:4096]:
        return []
    findings: list[Finding] = []
    for rule_id, pattern in CONTENT_RULES:
        for match in pattern.finditer(content[:MAX_SCAN_BYTES]):
            line = content.count(b"\n", 0, match.start()) + 1
            line_start = content.rfind(b"\n", 0, match.start()) + 1
            line_end = content.find(b"\n", match.end())
            if line_end < 0:
                line_end = len(content)
            if b"test-only-" in content[line_start:line_end]:
                continue
            findings.append(Finding(rule_id, path, line))
    return findings


def _filesystem_entries(paths: Iterable[str]) -> Iterable[tuple[str, bytes]]:
    for path in paths:
        candidate = (PROJECT_ROOT / path).resolve()
        if not candidate.is_relative_to(PROJECT_ROOT) or not candidate.is_file():
            continue
        if candidate.stat().st_size > MAX_SCAN_BYTES:
            yield path, b""
            continue
        yield path, candidate.read_bytes()


def _mode_entries(mode: str) -> list[tuple[str, bytes]]:
    if mode == "worktree":
        paths = (
            _git("ls-files", "-co", "--exclude-standard")
            .decode("utf-8")
            .splitlines()
        )
        return list(_filesystem_entries(paths))
    if mode == "tracked":
        paths = _git("ls-files").decode("utf-8").splitlines()
        return list(_filesystem_entries(paths))
    if mode == "staged":
        paths = (
            _git(
                "diff",
                "--cached",
                "--name-only",
                "--diff-filter=ACMR",
            )
            .decode("utf-8")
            .splitlines()
        )
        entries: list[tuple[str, bytes]] = []
        for path in paths:
            try:
                content = _git("show", f":{path}")
            except RuntimeError:
                continue
            entries.append((path, content[:MAX_SCAN_BYTES]))
        return entries
    # Codex may create private checkpoint refs under refs/codex. They are not
    # part of the branch/tag history that can be pushed or reviewed.
    objects = _git(
        "rev-list",
        "--objects",
        "--branches",
        "--remotes",
        "--tags",
    ).decode(
        "utf-8",
        errors="replace",
    )
    entries = []
    seen: set[tuple[str, str]] = set()
    for line in objects.splitlines():
        sha, separator, path = line.partition(" ")
        if not separator or not path or (sha, path) in seen:
            continue
        seen.add((sha, path))
        if _git("cat-file", "-t", sha).strip() != b"blob":
            continue
        size = int(_git("cat-file", "-s", sha))
        content = (
            _git("cat-file", "blob", sha)[:MAX_SCAN_BYTES]
            if size <= MAX_SCAN_BYTES
            else b""
        )
        entries.append((path, content))
    return entries


def _example_findings() -> list[Finding]:
    path = PROJECT_ROOT / "config/model-secrets.example.json"
    try:
        values = json.loads(path.read_text(encoding="utf-8"))["secrets"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        return [Finding("EXAMPLE_SECRET_FORMAT_INVALID", path.name, 1)]
    if any(value != "" for value in values.values()):
        return [
            Finding(
                "EXAMPLE_SECRET_NOT_EMPTY",
                "config/model-secrets.example.json",
                1,
            )
        ]
    return []


def scan(mode: str) -> list[Finding]:
    findings = _example_findings()
    for path, content in _mode_entries(mode):
        findings.extend(_path_findings(path))
        findings.extend(_content_findings(path, content))
    return sorted(
        set(findings),
        key=lambda item: (item.path, item.line, item.rule_id),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("worktree", "tracked", "staged", "history"):
        modes.add_argument(
            f"--{mode}",
            dest="mode",
            action="store_const",
            const=mode,
        )
    arguments = parser.parse_args()
    findings = scan(arguments.mode)
    if findings:
        for finding in findings:
            print(
                f"{finding.rule_id}\t{finding.path}\tline {finding.line}"
            )
        return 1
    print(f"release-safety --{arguments.mode}: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
