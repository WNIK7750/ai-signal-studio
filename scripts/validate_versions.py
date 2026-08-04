from __future__ import annotations

import json
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    expected = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    root_package = read_json(PROJECT_ROOT / "package.json")
    web_package = read_json(PROJECT_ROOT / "apps/web/package.json")

    versions = {
        "VERSION": expected,
        "pyproject.toml": pyproject["project"]["version"],
        "package.json": root_package["version"],
        "apps/web/package.json": web_package["version"],
    }
    mismatches = {
        source: version
        for source, version in versions.items()
        if version != expected
    }
    if mismatches:
        print(f"VERSION-001: project versions differ: {mismatches}")
        return 1

    python_version = (
        PROJECT_ROOT / ".python-version"
    ).read_text(encoding="utf-8").strip()
    running_python = ".".join(map(str, sys.version_info[:3]))
    if running_python != python_version:
        print(
            "VERSION-002: Python runtime differs: "
            f"expected {python_version}, got {running_python}"
        )
        return 1

    package_manager = root_package.get("packageManager")
    if package_manager != "pnpm@11.9.0":
        print(
            "VERSION-003: package manager differs: "
            f"expected pnpm@11.9.0, got {package_manager}"
        )
        return 1

    for line in (
        PROJECT_ROOT / "requirements.lock"
    ).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        package, expected_package_version = line.split("==", maxsplit=1)
        try:
            installed_package_version = version(package)
        except PackageNotFoundError:
            print(f"VERSION-005: Python dependency is missing: {package}")
            return 1
        if installed_package_version != expected_package_version:
            print(
                "VERSION-006: Python dependency differs: "
                f"{package} expected {expected_package_version}, "
                f"got {installed_package_version}"
            )
            return 1

    for section in ("dependencies", "devDependencies"):
        for name, value in web_package.get(section, {}).items():
            if isinstance(value, str) and value.startswith(("^", "~", ">")):
                print(
                    "VERSION-004: web dependency is not pinned: "
                    f"{name}={value}"
                )
                return 1

    print(
        f"Version {expected}; Python {running_python}; "
        "pnpm 11.9.0; Python and web dependencies pinned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
