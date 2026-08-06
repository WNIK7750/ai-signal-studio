from scripts.check_release_safety import (
    PROJECT_ROOT,
    _content_findings,
    _path_findings,
)
import subprocess


def test_release_guard_rejects_local_paths_and_unapproved_media() -> None:
    assert _path_findings("nested/config/models.local.json")
    assert _path_findings("data/private.db")
    assert _path_findings("screenshots/private.png")
    assert not _path_findings("apps/web/public/file.svg")


def test_release_guard_reports_location_without_secret_value() -> None:
    content = (
        b"safe\nAuthor"
        + b"ization: Bearer "
        + b"unsafe-fixture-value\n"
    )

    findings = _content_findings("sample.txt", content)

    assert [(item.rule_id, item.path, item.line) for item in findings] == [
        ("SECRET_AUTH_HEADER", "sample.txt", 2)
    ]
    assert all(
        "unsafe-fixture-value" not in repr(item)
        for item in findings
    )


def test_gitignore_covers_nested_local_config_and_runtime_data() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "--stdin",
        ],
        cwd=PROJECT_ROOT,
        input=(
            b"nested/config/models.local.json\n"
            b"nested/config/deeper/provider.local.json\n"
            b"data/private.db\n"
            b"logs/runtime.log\n"
        ),
        stdout=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 4
