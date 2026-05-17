from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def format_channel_json_file(path: str | os.PathLike[str], *, check: bool = False) -> bool:
    file_path = Path(path)
    current = file_path.read_text(encoding="utf-8")
    payload = json.loads(current)
    formatted = format_channel_json(payload)

    changed = formatted != current
    if changed and not check:
        file_path.write_text(formatted, encoding="utf-8")
    return changed


def format_channel_json(data: Any) -> str:
    formatted = _format_value(data, indent=0)
    return f"{formatted}\n"


def _format_value(value: Any, *, indent: int) -> str:
    if isinstance(value, dict):
        return _format_object(value, indent=indent)
    if isinstance(value, list):
        return _format_array(value, indent=indent)
    return _format_primitive(value)


def _format_object(value: dict[str, Any], *, indent: int) -> str:
    if not value:
        return "{}"

    items = list(value.items())
    lines: list[str] = ["{"]
    for index, (key, item_value) in enumerate(items):
        value_text = _format_value(item_value, indent=indent + 1)
        block = _render_member_block(
            key=key,
            value_text=value_text,
            indent=indent + 1,
            trailing_comma=index < len(items) - 1,
        )
        lines.extend(block)

    lines.append(f"{_tabs(indent)}}}")
    return "\n".join(lines)


def _format_array(value: list[Any], *, indent: int) -> str:
    if not value:
        return "[]"

    if _is_inline_primitive_array(value):
        return f"[{', '.join(_format_primitive(item) for item in value)}]"

    lines: list[str] = ["["]
    for index, item in enumerate(value):
        value_text = _format_value(item, indent=indent + 1)
        block = _render_array_item_block(
            value_text=value_text,
            indent=indent + 1,
            trailing_comma=index < len(value) - 1,
        )
        lines.extend(block)

    lines.append(f"{_tabs(indent)}]")
    return "\n".join(lines)


def _render_member_block(
    *,
    key: str,
    value_text: str,
    indent: int,
    trailing_comma: bool,
) -> list[str]:
    value_lines = value_text.splitlines()
    block = [f"{_tabs(indent)}{json.dumps(key, ensure_ascii=False)}: {value_lines[0]}"]
    block.extend(value_lines[1:])
    if trailing_comma:
        block[-1] = f"{block[-1]},"
    return block


def _render_array_item_block(*, value_text: str, indent: int, trailing_comma: bool) -> list[str]:
    value_lines = value_text.splitlines()
    block = [f"{_tabs(indent)}{value_lines[0]}"]
    block.extend(value_lines[1:])
    if trailing_comma:
        block[-1] = f"{block[-1]},"
    return block


def _is_inline_primitive_array(value: list[Any]) -> bool:
    return all(_is_primitive(item) for item in value)


def _is_primitive(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _format_primitive(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _tabs(indent: int) -> str:
    return "\t" * indent
