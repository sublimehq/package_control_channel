from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent

import pytest
from mockito import expect, mock, unstub, when

from . import report_404_packages as script


@pytest.fixture
def lenient_unstub():
    """Same as the built in unstub fixture but doesn't check usage.
    Typical to avoid.
    """
    try:
        yield
    finally:
        unstub()


def test_collect_unreachable_packages_filters_by_source_reason_and_age():
    now = datetime(2026, 4, 22, tzinfo=UTC)
    workspace = {
        "packages": {
            "NoName": {
                "name": "NoName",
                "details": "https://github.com/someone/NoName",
                "source": "https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
                "fail_reason": "fatal: 404 not found",
                "failing_since": "2026-03-10T00:00:00Z",
            },
            "Alpha": {
                "name": "Alpha",
                "source": "https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
                "fail_reason": "fatal: 404 Could not resolve repository",
                "failing_since": "2026-03-20T00:00:00Z",
            },
            "TooYoung": {
                "name": "TooYoung",
                "source": "https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
                "fail_reason": "fatal: 404 not found",
                "failing_since": "2026-04-20T00:00:00Z",
            },
            "WrongSource": {
                "name": "WrongSource",
                "source": "https://raw.githubusercontent.com/other/channel/master/repository.json",
                "fail_reason": "fatal: 404 not found",
                "failing_since": "2026-03-01T00:00:00Z",
            },
            "WrongReason": {
                "name": "WrongReason",
                "source": "https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
                "fail_reason": "403 forbidden",
                "failing_since": "2026-03-01T00:00:00Z",
            },
        }
    }

    result = script.collect_unreachable_packages(
        workspace,
        allowed_sources=[
            "https://raw.githubusercontent.com/wbond/package_control_channel/",
        ],
        min_age_days=21,
        now=now,
    )

    assert [item.name for item in result] == ["NoName", "Alpha"]
    assert result[1].age_days == 33


@pytest.mark.parametrize(
    ("origin_url", "expected"),
    [
        (
            "https://github.com/wbond/package_control_channel.git\n",
            [
                "https://raw.githubusercontent.com/sublimehq/package_control_channel/",
                "https://raw.githubusercontent.com/wbond/package_control_channel/",
            ],
        ),
        (
            "https://github.com/sublimehq/package_control_channel.git\n",
            [
                "https://raw.githubusercontent.com/sublimehq/package_control_channel/",
                "https://raw.githubusercontent.com/wbond/package_control_channel/",
            ],
        ),
        (
            "https://github.com/SublimeLinter/package_control_channel.git\n",
            [
                "https://raw.githubusercontent.com/SublimeLinter/package_control_channel/",
            ],
        ),
    ],
)
def test_computes_allowed_sources_from_origin(
    unstub,
    origin_url: str,
    expected: list[str],
):
    when(script).run_output(
        ["git", "config", "--get", "remote.origin.url"]
    ).thenReturn(origin_url)

    assert script.compute_allowed_sources_from_origin() == expected


@pytest.mark.parametrize(
    ("origin_url", "expected"),
    [
        (
            "https://github.com/wbond/package_control_channel.git",
            ("wbond", "package_control_channel"),
        ),
        (
            "https://github.com/SublimeLinter/package_control_channel",
            ("SublimeLinter", "package_control_channel"),
        ),
        (
            "git@github.com:wbond/package_control_channel.git",
            ("wbond", "package_control_channel"),
        ),
    ],
)
def test_parse_github_origin_owner_repo_parses_supported_forms(
    origin_url: str,
    expected: tuple[str, str],
):
    assert script.parse_github_origin_owner_repo(origin_url) == expected


def test_parse_github_origin_owner_repo_rejects_unsupported_host():
    with pytest.raises(ValueError, match="Origin is not github.com"):
        script.parse_github_origin_owner_repo(
            "https://gitlab.com/wbond/package_control_channel.git"
        )


def test_parse_github_origin_owner_repo_rejects_missing_repo_segment():
    with pytest.raises(ValueError):
        script.parse_github_origin_owner_repo("https://github.com/wbond")


def test_extract_package_name_prefers_name_then_details_repo():
    assert script.extract_package_name({"name": "DirectName"}) == "DirectName"
    assert script.extract_package_name({"details": "https://github.com/user/RepoName"}) == "RepoName"
    assert script.extract_package_name({"details": "https://example.invalid/no-name"}) is None


@pytest.mark.parametrize(
    ("source_url", "expected"),
    [
        (
            "https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
            Path("repository.json"),
        ),
        (
            "https://packages.monokai.pro/packages.json",
            Path("packages.json"),
        ),
        (
            "https://example.com/sublime/channel/packages.json",
            Path("sublime/channel/packages.json"),
        ),
    ],
)
def test_resolve_source_file_path_supports_github_raw_and_custom_hosts(
    unstub,
    source_url: str,
    expected: Path,
):
    root = mock()
    expect(root, between=(0,)).__truediv__(...).is_file().thenReturn(False)
    when(root).__truediv__(expected).is_file().thenReturn(True)
    assert script.resolve_source_file_path(source_url, root=root) == expected


def test_collect_channel_package_files_fails_when_source_url_cannot_be_mapped(tmp_path):
    with pytest.raises(SystemExit, match="Failed to map source URL"):
        script.collect_channel_package_files(
            ["https://example.com/not/in/checkout/packages.json"],
            root=tmp_path,
        )


def test_collect_channel_package_files_fails_when_include_is_missing(tmp_path):
    (tmp_path / "repository.json").write_text(
        json.dumps(
            {
                "schema_version": "3.0.0",
                "packages": [],
                "includes": ["./repository/missing.json"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="is missing"):
        script.collect_channel_package_files(
            [
                "https://raw.githubusercontent.com/wbond/package_control_channel/"
                "refs/heads/master/repository.json"
            ],
            root=tmp_path,
        )


def test_collect_channel_package_files_fails_when_include_escapes_repo_root(tmp_path):
    (tmp_path / "repository.json").write_text(
        json.dumps(
            {
                "schema_version": "3.0.0",
                "packages": [],
                "includes": ["../evil.json"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path.parent / "evil.json").write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit, match="escapes repository root"):
        script.collect_channel_package_files(
            [
                "https://raw.githubusercontent.com/wbond/package_control_channel/"
                "refs/heads/master/repository.json"
            ],
            root=tmp_path,
        )


def test_render_commit_message_supports_singular_and_plural():
    single = [
        script.UnreachablePackage(
            name="KarmaRunner",
            details="https://github.com/knee-cola/KarmaRunner",
            failing_since=datetime(2026, 3, 21, tzinfo=UTC),
            age_days=31,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
        )
    ]
    plural = [
        *single,
        script.UnreachablePackage(
            name="LazyTimeTracker",
            details="https://github.com/Bwata/LazyTimeTracker",
            failing_since=datetime(2026, 3, 28, tzinfo=UTC),
            age_days=24,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
        ),
    ]

    single_commit = script.render_commit_message(single)
    assert single_commit == dedent(
        """\
        Remove unreachable package KarmaRunner

        Remove KarmaRunner which responds with a 404 since 2026-03-21.
        """
    )

    plural_commit = script.render_commit_message(plural)
    assert plural_commit == dedent(
        """\
        Remove unreachable packages

        Remove the following packages which respond with 404s.

        - KarmaRunner [since 2026-03-21]
        - LazyTimeTracker [since 2026-03-28]
        """
    )


def test_render_human_report_and_machine_report():
    packages = [
        script.UnreachablePackage(
            name="KarmaRunner",
            details="https://github.com/knee-cola/KarmaRunner",
            failing_since=datetime(2026, 3, 21, tzinfo=UTC),
            age_days=31,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/",
        ),
        script.UnreachablePackage(
            name="LazyTimeTracker",
            details="https://github.com/Bwata/LazyTimeTracker",
            failing_since=datetime(2026, 3, 28, tzinfo=UTC),
            age_days=24,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/",
        ),
    ]

    assert script.render_human_report(packages) == (
        "KarmaRunner      [since 2026-03-21; 4 weeks]\n"
        "LazyTimeTracker  [since 2026-03-28; 3 weeks]\n"
    )
    assert script.render_human_report([]) == "<nothing to report>\n"

    assert script.render_machine_report(packages) == (
        "KarmaRunner\x002026-03-21T00:00:00Z\n"
        "LazyTimeTracker\x002026-03-28T00:00:00Z"
    )
    assert script.render_machine_report([]) == ""


def test_remove_packages_from_repository_uses_source_and_includes_once(tmp_path):
    repository_root = tmp_path
    (repository_root / "repository").mkdir()

    (repository_root / "repository.json").write_text(
        json.dumps(
            {
                "schema_version": "3.0.0",
                "packages": [
                    {"name": "RootPackage", "details": "https://example.invalid/root"},
                    {"name": "KeepRoot", "details": "https://example.invalid/keep-root"},
                ],
                "includes": ["./repository/a.json"],
            }
        ),
        encoding="utf-8",
    )
    (repository_root / "repository" / "a.json").write_text(
        json.dumps(
            {
                "schema_version": "3.0.0",
                "packages": [
                    {"name": "KarmaRunner", "details": "https://example.invalid/karma"},
                    {"name": "KeepA", "details": "https://example.invalid/keep-a"},
                ],
                "includes": ["./c.json"],
            }
        ),
        encoding="utf-8",
    )
    (repository_root / "repository" / "c.json").write_text(
        json.dumps(
            {
                "schema_version": "3.0.0",
                "packages": [
                    {"name": "LazyTimeTracker", "details": "https://example.invalid/lazy"},
                ],
            }
        ),
        encoding="utf-8",
    )

    unreachable_packages = [
        script.UnreachablePackage(
            name="RootPackage",
            details="https://example.invalid/root",
            failing_since=datetime(2026, 3, 21, tzinfo=UTC),
            age_days=31,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
        ),
        script.UnreachablePackage(
            name="KarmaRunner",
            details="https://example.invalid/karma",
            failing_since=datetime(2026, 3, 21, tzinfo=UTC),
            age_days=31,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
        ),
        script.UnreachablePackage(
            name="LazyTimeTracker",
            details="https://example.invalid/lazy",
            failing_since=datetime(2026, 3, 21, tzinfo=UTC),
            age_days=31,
            source="https://raw.githubusercontent.com/wbond/package_control_channel/refs/heads/master/repository.json",
        ),
    ]

    planned_files, removed_names = script.remove_packages_from_repository(
        repository_root=repository_root,
        unreachable_packages=unreachable_packages,
        apply_changes=False,
    )

    assert planned_files == [
        (repository_root / "repository.json").resolve(),
        (repository_root / "repository" / "a.json").resolve(),
    ]
    assert removed_names == {"RootPackage", "KarmaRunner"}

    changed_files, removed_names = script.remove_packages_from_repository(
        repository_root=repository_root,
        unreachable_packages=unreachable_packages,
        apply_changes=True,
    )

    assert changed_files == [
        (repository_root / "repository.json").resolve(),
        (repository_root / "repository" / "a.json").resolve(),
    ]
    assert removed_names == {"RootPackage", "KarmaRunner"}

    root_payload = json.loads((repository_root / "repository.json").read_text(encoding="utf-8"))
    assert root_payload["packages"] == [
        {"name": "KeepRoot", "details": "https://example.invalid/keep-root"},
    ]

    a_payload = json.loads((repository_root / "repository" / "a.json").read_text(encoding="utf-8"))
    assert a_payload["packages"] == [
        {"name": "KeepA", "details": "https://example.invalid/keep-a"},
    ]

    c_payload = json.loads((repository_root / "repository" / "c.json").read_text(encoding="utf-8"))
    assert c_payload["packages"] == [
        {"name": "LazyTimeTracker", "details": "https://example.invalid/lazy"},
    ]


def test_ensure_paths_are_clean_fails_when_target_files_are_dirty(monkeypatch):
    def fake_run_output(command: list[str], *, input_text: str | None = None) -> str:
        assert command[:3] == ["git", "diff", "--name-only"]
        assert input_text is None
        return "repository/a.json\n"

    monkeypatch.setattr(script, "run_output", fake_run_output)

    with pytest.raises(SystemExit, match="target files are dirty"):
        script.ensure_paths_are_clean([Path("repository/a.json")])
