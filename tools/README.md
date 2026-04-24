# tools

Utilities for maintaining the `package_control_channel`.

## `format_package_control_channel.py`

Stable formatter for `repository/*.json` files with our
custom, in-house style.

### Usage

From repository root (usage shown with `uv`):

```bash
uv run -m tools.format_package_control_channel ./repository
```

Check-only mode (non-zero exit code if any file would be changed):

```bash
uv run -m tools.format_package_control_channel ./repository --check
```

### Tests

```bash
uvx pytest tools/test_channel_json_format.py
```
