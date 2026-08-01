from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Container
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import urlparse

from ._channel_json_format import format_channel_json


@dataclass(frozen=True)
class UnreachablePackage:
    name: str
    details: str | None
    failing_since: datetime
    age_days: int
    source: str


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = datetime.now(UTC)

    workspace_path = resolve_workspace_path(args.workspace)
    if args.workspace is None:
        refresh_workspace_if_stale(workspace_path, now=now)

    workspace = load_workspace(workspace_path)
    print_workspace_age_note_if_needed(workspace_path, workspace=workspace, now=now)

    allowed_sources = resolve_allowed_sources(args.allowed_source)
    ignored_identifiers = resolve_ignored_identifiers(
        ignore_values=args.ignore,
        ignore_files=args.ignore_file,
    )
    unreachable_packages = collect_unreachable_packages(
        workspace,
        allowed_sources=allowed_sources,
        min_age_days=args.min_age,
        ignored_identifiers=ignored_identifiers,
        now=now,
    )

    planned_files, removed_names = remove_packages_from_repository(
        repository_root=Path("."),
        unreachable_packages=unreachable_packages,
        apply_changes=False,
    )
    packages_to_report = [
        package
        for package in unreachable_packages
        if package.name in removed_names
    ]

    if args.build_pr_message and packages_to_report:
        write_pr_message_files(packages_to_report, root=Path("."))

    if args.commit and packages_to_report:
        ensure_paths_are_clean(planned_files)

        changed_files, _ = remove_packages_from_repository(
            repository_root=Path("."),
            unreachable_packages=unreachable_packages,
            apply_changes=True,
        )

        commit_message = render_commit_message(packages_to_report)
        create_git_commit(changed_files=changed_files, commit_message=commit_message)

        if args.z:
            sys.stdout.write(render_machine_report(packages_to_report))
        else:
            print_last_commit_patch()
        return 0

    if args.z:
        sys.stdout.write(render_machine_report(packages_to_report))
    else:
        sys.stdout.write(render_human_report(packages_to_report))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report packages that fail with fatal 404 errors for at least "
            "a configurable number of days."
        )
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply the removals to the repository and create a commit.",
    )
    parser.add_argument(
        "-z",
        action="store_true",
        help=(
            "Machine-readable output as newline-delimited records with "
            "NUL-separated fields: <name>\\0<url>\\0<failing_since_utc>"
        ),
    )
    parser.add_argument(
        "--min-age",
        type=int,
        default=21,
        metavar="DAYS",
        help="Minimum failing age in full days (default: 21).",
    )
    parser.add_argument(
        "--allowed-source",
        action="append",
        default=None,
        help=(
            "Allowed source URL prefix. Can be passed multiple times. "
            "By default this is computed from git origin."
        ),
    )
    parser.add_argument(
        "--workspace",
        nargs="?",
        const="workspace.json",
        default=None,
        help=(
            "Use a workspace file. Without a value, defaults to workspace.json. "
            "If omitted, workspace.json is auto-refreshed via gh when older "
            "than 1 hour."
        ),
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=None,
        help=(
            "Ignore package identifiers (name or details URL). Can be passed "
            "multiple times and supports comma-separated values."
        ),
    )
    parser.add_argument(
        "--ignore-file",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Read ignored package identifiers (name or details URL) from file. "
            "One value per line, with optional comma-separated values. "
            "Blank lines and lines starting with # are ignored."
        ),
    )
    parser.add_argument(
        "--build-pr-message",
        action="store_true",
        help="Write pr_title.txt and pr_body.md for the current report.",
    )
    return parser.parse_args(argv)


def resolve_workspace_path(workspace_arg: str | None) -> Path:
    if workspace_arg is None:
        return Path("workspace.json")
    return Path(workspace_arg)


def refresh_workspace_if_stale(workspace_path: Path, *, now: datetime) -> None:
    if workspace_path.exists() and workspace_is_fresh(workspace_path, now=now):
        return

    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    run([
        "gh",
        "-R",
        "packagecontrol/thecrawl",
        "release",
        "download",
        "crawler-status",
        "--pattern",
        "workspace.json",
        "--output",
        str(workspace_path),
        "--clobber",
    ])


def workspace_is_fresh(workspace_path: Path, *, now: datetime) -> bool:
    modified_at = datetime.fromtimestamp(workspace_path.stat().st_mtime, tz=UTC)
    return now - modified_at < timedelta(hours=1)


def load_workspace(workspace_path: Path) -> dict[str, Any]:
    if not workspace_path.exists():
        raise SystemExit(f"Workspace file not found: {workspace_path}")

    try:
        return json.loads(workspace_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Failed to parse workspace JSON: {workspace_path}: {error}") from error


def print_workspace_age_note_if_needed(
    workspace_path: Path,
    *,
    workspace: dict[str, Any],
    now: datetime,
) -> None:
    newest_last_seen = newest_last_seen_timestamp(workspace)
    if newest_last_seen is None:
        return

    parsed_newest_last_seen = parse_timestamp(newest_last_seen)
    if parsed_newest_last_seen is None:
        return

    if now - parsed_newest_last_seen < timedelta(days=1):
        return

    print(
        (
            f"Note: your {workspace_path} file is rather old, consider downloading "
            "a fresh one using\n"
            "gh -R packagecontrol/thecrawl release download crawler-status "
            "--pattern workspace.json --output workspace.json --clobber"
        ),
        file=sys.stderr,
    )


def resolve_allowed_sources(override_sources: list[str] | None) -> list[str]:
    if override_sources is not None:
        return override_sources
    return compute_allowed_sources_from_origin()


def resolve_ignored_identifiers(
    *,
    ignore_values: list[str] | None,
    ignore_files: list[str] | None,
) -> set[str]:
    identifiers: set[str] = set()

    for ignore_value in ignore_values or []:
        identifiers.update(split_ignored_values(ignore_value))

    for ignore_file in ignore_files or []:
        identifiers.update(load_ignored_values_file(Path(ignore_file)))

    return identifiers


def split_ignored_values(raw_value: str) -> set[str]:
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def load_ignored_values_file(path: Path) -> set[str]:
    if not path.exists():
        raise SystemExit(f"Ignore file not found: {path}")

    return {
        value
        for raw_line in path.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip())
        if not line.startswith("#")
        for value in split_ignored_values(line)
    }


def compute_allowed_sources_from_origin() -> list[str]:
    origin_url = run_output(["git", "config", "--get", "remote.origin.url"]).strip()
    if not origin_url:
        raise SystemExit(
            "Failed to determine git origin. Provide --allowed-source explicitly."
        )

    try:
        owner, repo = parse_github_origin_owner_repo(origin_url)
    except ValueError as error:
        raise SystemExit(
            f"Unsupported git origin URL: {origin_url}. "
            "Provide --allowed-source explicitly."
        ) from error

    owner_repo_pairs = equivalent_origin_repositories(owner, repo)
    return [
        f"https://raw.githubusercontent.com/{source_owner}/{source_repo}/"
        for source_owner, source_repo in owner_repo_pairs
    ]


def parse_github_origin_owner_repo(origin_url: str) -> tuple[str, str]:
    http_url = remote_to_url(origin_url)
    if "://github.com/" not in http_url:
        raise ValueError("Origin is not github.com")
    return parse_owner_repo(http_url)


def equivalent_origin_repositories(owner: str, repo: str) -> list[tuple[str, str]]:
    if (
        repo == "package_control_channel"
        and owner in ("wbond", "sublimehq")
    ):
        return [("sublimehq", repo), ("wbond", repo)]

    return [(owner, repo)]


def newest_last_seen_timestamp(workspace: dict[str, Any]) -> str | None:
    last_seens = (
        last_seen
        for package in workspace.get("packages").values()
        if (last_seen := package.get("last_seen"))
    )
    return max(last_seens, default=None)


def collect_unreachable_packages(
    workspace: dict[str, Any],
    *,
    allowed_sources: list[str],
    min_age_days: int,
    ignored_identifiers: Container[str] = (),
    now: datetime,
) -> list[UnreachablePackage]:
    unreachable: list[UnreachablePackage] = []
    for package in workspace.get("packages").values():
        source = package.get("source")
        if not isinstance(source, str):
            continue
        if not any(source.startswith(allowed_source) for allowed_source in allowed_sources):
            continue

        name = package["name"]
        if name in ignored_identifiers:
            continue

        details = package.get("details")
        if details and details in ignored_identifiers:
            continue

        fail_reason = package.get("fail_reason", "")
        if "fatal: 404" not in fail_reason.lower():
            continue

        raw_failing_since = package.get("failing_since")
        if not raw_failing_since:
            continue

        failing_since = parse_timestamp(raw_failing_since)
        if failing_since is None:
            continue

        age_days = (now - failing_since).days
        if age_days < min_age_days:
            continue

        unreachable.append(
            UnreachablePackage(
                name=name,
                details=details,
                failing_since=failing_since,
                age_days=age_days,
                source=source,
            )
        )

    return sorted(
        unreachable,
        key=lambda package: (package.failing_since, package.name.casefold()),
    )


def remove_packages_from_repository(
    *,
    repository_root: Path,
    unreachable_packages: list[UnreachablePackage],
    apply_changes: bool = True,
) -> tuple[list[Path], set[str]]:
    changed_files: list[Path] = []
    removed_names: set[str] = set()
    unreachable_names = {package.name for package in unreachable_packages}
    root = repository_root.resolve()

    source_urls = unique(package.source for package in unreachable_packages)
    package_files = (
        package_file
        for source_url in source_urls
        for package_file in iter_channel_package_files(source_url, root=root)
    )
    for json_file in package_files:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
        packages = payload.get("packages", [])

        kept_packages: list[Any] = []
        file_changed = False
        for package in packages:
            package_name = extract_package_name(package)
            if package_name is None or package_name not in unreachable_names:
                kept_packages.append(package)
                continue

            removed_names.add(package_name)
            file_changed = True

        if not file_changed:
            continue

        changed_files.append(json_file)
        if apply_changes:
            payload["packages"] = kept_packages
            json_file.write_text(
                format_channel_json(payload),
                encoding="utf-8",
            )

    return changed_files, removed_names


def iter_channel_package_files(
    source_url: str, *, root: Path
) -> Iterator[Path]:
    source_file = resolve_source_file_path(source_url, root=root)
    main_file = (root / source_file).resolve()
    yield main_file

    payload = json.loads(main_file.read_text(encoding="utf-8"))
    for include_entry in payload.get("includes", []):
        channel_file = (main_file.parent / include_entry).resolve()

        try:
            channel_file.relative_to(root)
        except ValueError as error:
            raise SystemExit(
                "Channel file escapes repository root: "
                f"{channel_file} (source: {source_url})"
            ) from error

        if not channel_file.is_file():
            raise SystemExit(
                "Channel file listed by source/includes is missing: "
                f"{channel_file} (source: {source_url})"
            )

        yield channel_file


def resolve_source_file_path(source_url: str, *, root: Path) -> Path:
    """Map a crawler source URL to a channel file path in this checkout."""

    for candidate in unique(candidate_source_file_paths(source_url)):
        if (root / candidate).is_file():
            return candidate

    raise SystemExit(
        f"Failed to map source URL to local file: {source_url}"
    )


def candidate_source_file_paths(source_url: str) -> Iterator[Path]:
    parsed = urlparse(source_url)
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    if not path_parts:
        return []

    # Known GitHub URL layout is translated directly first. If that does not
    # resolve to an existing file, fall back to trying progressively shorter URL
    # path suffixes. That fallback keeps custom/self-hosted source URLs working
    # without having to model every possible URL layout.

    if github_raw_path := resolve_github_source_url(parsed.netloc, path_parts):
        yield github_raw_path

    yield from (
        Path(*path_parts[split_index:])
        for split_index in range(len(path_parts))
    )


def resolve_github_source_url(
    netloc: str,
    path_parts: list[str],
) -> Path | None:
    if netloc != "raw.githubusercontent.com" or len(path_parts) < 4:
        return None

    if (
        len(path_parts) >= 6
        and path_parts[2] == "refs"
        and path_parts[3] in {"heads", "tags"}
    ):
        return Path(*path_parts[5:])

    return Path(*path_parts[3:])


def unique(paths: Iterable[Path]) -> Iterator[Path]:
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        yield path


def ensure_paths_are_clean(paths: list[Path]) -> None:
    if not paths:
        return

    status = run_output(["git", "diff", "--name-only", "--", *[str(path) for path in paths]])
    if not status.strip():
        return

    raise SystemExit(
        "Refusing to commit because target files are dirty:\n"
        f"{status.rstrip()}"
    )


def render_commit_message(packages: list[UnreachablePackage]) -> str:
    singular = len(packages) == 1
    if singular:
        package = packages[0]
        subject = f"Remove unreachable package {package.name}"
        intro = (
            f"Remove {package.name} which responds with a 404 since "
            f"{format_date(package.failing_since)}."
        )
        body_lines = [intro]
    else:
        subject = "Remove unreachable packages"
        intro = "Remove the following packages which respond with 404s."
        bullets = [
            f"- {package.name} [since {format_date(package.failing_since)}]"
            for package in packages
        ]
        body_lines = [
            intro,
            "",
            *bullets,
        ]

    return f"{subject}\n\n{'\n'.join(body_lines)}\n"


def render_human_report(packages: list[UnreachablePackage]) -> str:
    if not packages:
        return "<nothing to report>\n"

    max_name_width = max(len(package.name) for package in packages)
    lines = [
        f"{package.name.ljust(max_name_width)}  "
        f"[since {format_date(package.failing_since)}; {format_age(package.age_days)}]"
        for package in packages
    ]
    return "\n".join(lines) + "\n"


def render_machine_report(packages: list[UnreachablePackage]) -> str:
    if not packages:
        return ""

    return "\n".join(
        f"{package.name}\0{package.details or ''}\0{format_timestamp(package.failing_since)}"
        for package in packages
    )


def write_pr_message_files(
    packages: list[UnreachablePackage],
    *,
    root: Path,
) -> None:
    (root / "pr_title.txt").write_text(render_pr_title(packages) + "\n", encoding="utf-8")
    (root / "pr_body.md").write_text(render_pr_body(packages), encoding="utf-8")


def render_pr_title(packages: list[UnreachablePackage]) -> str:
    if len(packages) == 1:
        return f"Remove unreachable {packages[0].name}"
    return "Remove unreachable packages"


def render_pr_body(packages: list[UnreachablePackage]) -> str:
    if len(packages) == 1:
        subject = "The following package responds with a 404:"
        status_line = "You can check the current [status](https://packages.sublimetext.io/status)."
        outro = "This PR removes the package from the registry."
    else:
        subject = "The following packages respond with 404s:"
        status_line = "You can check their current [status](https://packages.sublimetext.io/status)."
        outro = "This PR removes the packages from the registry."

    bullets = [
        f"- **{package.name}** [since {format_date(package.failing_since)}; {format_age(package.age_days)}]"
        for package in packages
    ]

    return "\n".join([
        "Hi, thecrawl bot here! 👋",
        "",
        subject,
        "",
        *bullets,
        "",
        status_line,
        "",
        outro,
        "",
    ])


def format_date(value: datetime) -> str:
    return value.astimezone(UTC).date().isoformat()


def format_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_age(days: int) -> str:
    if days > 7:
        weeks = days // 7
        return f"{weeks} {pluralize(weeks, 'week')}"
    return f"{days} {pluralize(days, 'day')}"


def pluralize(count: int, singular: str) -> str:
    if count == 1:
        return singular
    return f"{singular}s"


def parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def extract_package_name(package: Mapping[str, Any]) -> str | None:
    """
    Extract the package name from a package entry.
    Tries 'name' key first, then parses the repo name from 'details' if it's a *Hub URL.
    """
    if name := package.get("name"):
        return name

    if details := package.get("details"):
        try:
            _, repo = parse_owner_repo(details)
        except ValueError:
            return None
        else:
            return repo
    return None


def parse_owner_repo(url: str) -> tuple[str, str]:
    """
    Extract owner and repo name from a *Hub URL.
    Example: https://github.com/timbrel/GitSavvy -> ("timbrel", "GitSavvy")
             https://github.com/timbrel/GitSavvy/tree/dev -> ("timbrel", "GitSavvy")
             https://github.com/timbrel/GitSavvy/releases/tag/2.50.0 -> ("timbrel", "GitSavvy")
             https://gitlab.com/jiehong/sublime_jq -> ("jiehong", "sublime_jq")
             https://bitbucket.org/hmml/jsonlint -> ("hmml", "jsonlint")
             https://codeberg.org/TobyGiacometti/SublimeDirectorySettings
               -> ("TobyGiacometti", "SublimeDirectorySettings")
    """
    parts = urlparse(url)
    path_parts = parts.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError("Invalid *Hub repo URL")
    return path_parts[0], path_parts[1]


def remote_to_url(remote_url: str) -> str:
    """
    Parse out a Github HTTP URL from a remote URI:

    r1 = remote_to_url("git://github.com/timbrel/GitSavvy.git")
    assert r1 == "https://github.com/timbrel/GitSavvy"

    r2 = remote_to_url("git@github.com:divmain/GitSavvy.git")
    assert r2 == "https://github.com/timbrel/GitSavvy"

    r3 = remote_to_url("https://github.com/timbrel/GitSavvy.git")
    assert r3 == "https://github.com/timbrel/GitSavvy"
    """

    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]

    if remote_url.startswith("git@"):
        return remote_url.replace(":", "/").replace("git@", "https://")
    elif remote_url.startswith("git://"):
        return remote_url.replace("git://", "https://")
    elif remote_url.startswith("http"):
        return remote_url
    else:
        raise ValueError('Cannot parse remote "{}" and transform to url'.format(remote_url))


def create_git_commit(*, changed_files: list[Path], commit_message: str) -> None:
    if not changed_files:
        return

    file_args = [str(file) for file in changed_files]
    run(["git", "add", "--", *file_args])
    run(
        ["git", "commit", "--quiet", "-F", "-", "--only", "--", *file_args],
        input_text=commit_message
    )


def print_last_commit_patch() -> None:
    patch = run_output(["git", "show", "--no-color", "--format=fuller", "--stat", "--patch"])
    sys.stdout.write(patch)


def run(command: list[str], *, input_text: str | None = None) -> None:
    subprocess.run(
        command,
        check=True,
        text=True,
        input=input_text,
    )


def run_output(command: list[str], *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        input=input_text,
        capture_output=True,
    )
    return completed.stdout


if __name__ == "__main__":
    raise SystemExit(main())
