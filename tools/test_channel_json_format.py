from __future__ import annotations

import json

from . import _channel_json_format as fmt
from . import format_package_control_channel as cli


def test_format_channel_json_uses_tabs_inline_scalars_and_trailing_newline():
    payload = {
        "schema_version": "3.0.0",
        "packages": [
            {
                "name": "Alpha",
                "details": "https://example.com/alpha",
                "labels": ["theme", "dark"],
                "releases": [
                    {
                        "sublime_text": "*",
                        "tags": True,
                    }
                ],
            }
        ],
    }

    rendered = fmt.format_channel_json(payload)

    assert rendered.endswith("\n")
    assert rendered.startswith("{\n\t\"schema_version\": \"3.0.0\",")
    assert '"labels": ["theme", "dark"]' in rendered
    assert '"releases": [\n\t\t\t\t{' in rendered


def test_format_channel_json_preserves_key_order():
    payload = {
        "schema_version": "3.0.0",
        "packages": [
            {
                "details": "https://example.com/no-name-first",
                "name": "WeirdOrder",
                "releases": [{"tags": True, "sublime_text": "*"}],
            }
        ],
    }

    rendered = fmt.format_channel_json(payload)

    assert rendered.index('"details"') < rendered.index('"name"')


def test_format_channel_json_file_check_and_write(tmp_path):
    file_path = tmp_path / "a.json"
    file_path.write_text(
        '{\n\t"schema_version": "3.0.0",\n\t"packages": [{"name":"A","labels":["x","y"]}]\n}\n',
        encoding="utf-8",
    )

    changed = fmt.format_channel_json_file(file_path, check=True)
    assert changed is True

    changed = fmt.format_channel_json_file(file_path, check=False)
    assert changed is True

    normalized = file_path.read_text(encoding="utf-8")
    assert '"labels": ["x", "y"]' in normalized
    assert "\t\t{" in normalized


def test_cli_check_mode_returns_nonzero_when_files_would_change(tmp_path, capsys):
    file_path = tmp_path / "a.json"
    file_path.write_text(
        '{\n\t"schema_version": "3.0.0",\n\t"packages": [{"name":"A","labels":["x","y"]}]\n}\n',
        encoding="utf-8",
    )

    rc = cli.main(["--check", str(file_path)])

    assert rc == 1
    out = capsys.readouterr().out
    assert "Would reformat:" in out


def test_cli_formats_directory(tmp_path, capsys):
    repo = tmp_path / "repository"
    repo.mkdir()

    (repo / "a.json").write_text(
        json.dumps({"schema_version": "3.0.0", "packages": [{"name": "A", "labels": ["x"]}]}),
        encoding="utf-8",
    )
    (repo / "b.json").write_text(
        json.dumps({"schema_version": "3.0.0", "packages": []}),
        encoding="utf-8",
    )

    rc = cli.main([str(repo)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Reformatted:" in out
    assert '"labels": ["x"]' in (repo / "a.json").read_text(encoding="utf-8")
