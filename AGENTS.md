# AGENTS.md

Conventions for AI agents (and people) working in this repository.

## Overview

dymonite prints text and QR code labels on a DYMO LabelWriter through CUPS.

- `src/dymonite/label.py`: rendering. Media keyword to pixels, the Wi-Fi QR payload, text fitting, the layout.
- `src/dymonite/cli.py`: the `dymonite` command. `label`, `wifi`, `sizes`; CSV rows; saving or `lp`.
- `tests/`: pytest. QR codes are checked by decoding the rendered label with zxing-cpp.
- `.github/workflows/ci.yml`: lint, tests (Linux and macOS), wheel and sdist, PyInstaller binaries, releases.

## Verification

Run all of it before calling a change done. CI runs the same.

```sh
pip install -e '.[test]' ruff==0.17.0
ruff check . && ruff format --check .
pytest
```

A change to the layout: render the samples in `ci.yml`'s build job with `-o` and look at them.

## Ponytail

This repo works in [ponytail](https://github.com/DietrichGebert/ponytail) mode (v5.2.0, MIT,
Dietrich Gebert): lazy senior dev. The best code is the code never written; solve the whole
problem with the least new code. `.claude/settings.json` enables the plugin for local Claude Code
sessions (cloud sessions and other agents don't load it, so the rules are here too). Its
marketplace is pinned to a tag: `v5.2.0` was `2961b52` when its hooks were read. A bump re-reads them.

Before writing, read the task and the code it touches, and list every place the change must reach:
callers, tests, fixtures, config, exports. That is scope; extra features are not.

Take the first option that fully works:

1. Does it need to exist? Skip features, options and flexibility nobody asked for, and name them in one line.
2. Already in this codebase? Use it the way the surrounding code does.
3. Standard library or a platform feature (CUPS, Pillow's font lookup)? Use it.
4. An installed dependency? Use it. Never add a dependency for a few lines.
5. Can it be one line a reader gets at a glance? One line.
6. Otherwise: the minimum code that works.

- Be lazy about the solution, never about the change: finish every part it needs, tests included.
- No abstraction, wrapper, option, config or "for later" code nobody asked for. Deletion beats addition.
- Comment only the why the code can't show, in one line.
- Bug fix: grep every caller first, then fix the root cause once.
- New non-trivial logic (a branch, a parser, a layout rule) leaves one small test.
- A shortcut with a known limit gets a comment: `shortcut: <the limit>, <when to upgrade>`.
- End a reply with one or two lines: what you skipped or didn't check, and any risk.

Never cut: validation at trust boundaries (CSV rows, CLI arguments), security, anything the user
asked for, or the calibration real hardware needs (below).

## Invariants: do not break these

- **300 dpi, in the media's own orientation.** A label is laid out landscape, then turned 90 degrees
  when the media is taller than wide, so `lp ... -o fit-to-page` never has to rotate or crop it.
- **Sizes are CUPS keywords.** `wNhM` is points (1/72 in), width across the print head; a trailing
  `.N` only tells duplicates apart. `-o media=` gets the keyword exactly as `lpoptions -l` lists it.
- **QR codes print crisp and scan.** Whole-pixel modules, at least `MIN_MODULE` px. The code shrinks
  only when the text otherwise doesn't fit; tests decode every layout they render.
- **Text is readable or an error.** Never below `MIN_FONT` px; too much text fails with a message.
- **`lp` gets an argument list, never a shell string.** Labels hold arbitrary text and passwords.
- **Wi-Fi payloads escape `\ ; , : "`** (`wifi_qr`), or phones join the wrong network or none.

## CI and releases

- External actions by major tag (`actions/checkout@v5` and so on); tools pinned by version in `ci.yml`.
- Every run uploads `release-*` artifacts and `samples`. The release gets: wheel, sdist,
  `dymonite-<os>-<arch>.tar.gz` (installed: a folder, quick to start) and `dymonite-<os>-<arch>-portable`
  (one bare executable to download and `chmod +x`; it unpacks itself on every run).
- A release is a `v<version>` tag, or the workflow run on `main` with `release` ticked; the version is
  `__version__` in `src/dymonite/__init__.py`, and a tag that doesn't match it fails the release.
