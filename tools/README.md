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

## `report_404_packages.py`

Finds packages in a crawler `workspace.json` that fail with `fatal: 404`
for at least --min-age days (default: 21) and report them.

If --commit is set, it actually removes the packages from the repository and
creates a commit.

If you don't specify a --workspace, it will download one for you from
`packagecontrol/thecrawl`.  (Requires `gh`.)

The default sources are derived from `git origin`; use `--allowed-source`
to override.

Use `--ignore` (name or details URL) and/or `--ignore-file` to skip already
known packages so recurring scheduled runs don't re-report them.

### Usage

Report only (`-z` for machine friendly output):

```bash
uv run -m tools.report_404_packages
uv run -m tools.report_404_packages -z
```

Use a specific workspace file:

```bash
uv run -m tools.report_404_packages --workspace ./workspace.json
```

Ignore specific package details URLs (or names):

```bash
uv run -m tools.report_404_packages \
  --ignore "https://github.com/axsuul/sublime-0x0" \
  --ignore "SublimeLinter,AnotherPackage"
```

Ignore via file:

```bash
uv run -m tools.report_404_packages --ignore-file ./tools/known-404s.txt
```

Apply removals and commit:

```bash
uv run -m tools.report_404_packages --commit
```

Build PR message files (`pr_title.txt`, `pr_body.md`) from the report. This
is for the CI.

```bash
uv run -m tools.report_404_packages --build-pr-message
```

### Tests

```bash
uvx pytest
```
