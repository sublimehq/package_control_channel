from __future__ import annotations

import argparse
from pathlib import Path

from ._channel_json_format import format_channel_json_file


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    files = collect_json_files(args.paths)

    changed: list[Path] = []
    for file_path in files:
        if format_channel_json_file(file_path, check=args.check):
            changed.append(file_path)

    if not changed:
        return 0

    action = "Would reformat" if args.check else "Reformatted"
    for file_path in changed:
        print(f"{action}: {file_path}")

    if args.check:
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Format package_control_channel JSON files with stable in-house style."
        )
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="JSON files and/or directories to format.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if files would change; do not write changes.",
    )
    return parser.parse_args(argv)


def collect_json_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            files.append(path)
            continue

        if path.is_dir():
            files.extend(sorted(path.glob("*.json"), key=lambda item: item.name.casefold()))
            continue

        raise SystemExit(f"format_package_control_channel: path not found: {path}")

    return sorted(files, key=lambda item: item.as_posix().casefold())


if __name__ == "__main__":
    raise SystemExit(main())
