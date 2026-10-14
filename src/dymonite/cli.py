"""dymonite: print text and QR code labels on a DYMO LabelWriter through CUPS."""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from . import __version__
from .label import DPI, load_font, media_size, render, wifi_qr


def parse_page_sizes(lpoptions: str) -> tuple[list[str], str | None]:
    """The PageSize keywords in `lpoptions -l` output, and the default (marked *)."""
    for line in lpoptions.splitlines():
        if line.startswith("PageSize"):
            names = line.split(":", 1)[1].split()
            default = next((n[1:] for n in names if n.startswith("*")), None)
            return [n.lstrip("*") for n in names], default
    return [], None


def sizes(args: argparse.Namespace) -> None:
    cmd = ["lpoptions", *(["-p", args.printer] if args.printer else []), "-l"]
    names, default = parse_page_sizes(run(cmd, capture_output=True).stdout)
    if not names:
        sys.exit("no PageSize option: is that a label printer?")
    for name in names:
        try:
            w, h = media_size(name)
        except ValueError:
            dims = "(named size, not usable with --size)"
        else:
            dims = f"{w / DPI * 25.4:5.1f} x {h / DPI * 25.4:5.1f} mm  {w / DPI:.2f} x {h / DPI:.2f} in"
        print(f"{'*' if name == default else ' '} {name:<28} {dims}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, text=True, **kwargs)
    except FileNotFoundError:
        sys.exit(f"{cmd[0]} not found: printing needs CUPS (macOS or Linux); use --output to save a PNG")
    except subprocess.CalledProcessError as e:
        sys.exit(f"{shlex.join(cmd)} failed: {(e.stderr or '').strip() or f'exit {e.returncode}'}")


def output(images: list[Image.Image], args: argparse.Namespace) -> None:
    """Save the labels to --output, or send them to the printer as one job."""
    if args.output:
        out = Path(args.output)
        paths = [out] if len(images) == 1 else [out.with_stem(f"{out.stem}-{i}") for i in range(1, len(images) + 1)]
    else:
        tmp = Path(tempfile.mkdtemp(prefix="dymonite-"))
        paths = [tmp / f"label-{i}.png" for i in range(1, len(images) + 1)]
    for img, path in zip(images, paths, strict=True):
        img.save(path, dpi=(DPI, DPI))
    if args.output:
        print("\n".join(map(str, paths)))
        return

    cmd = ["lp", "-o", f"media={args.size}", "-o", "fit-to-page", "-n", str(args.copies)]
    cmd += ["-d", args.printer] if args.printer else []
    cmd += map(str, paths)
    if args.dry_run:
        print(shlex.join(cmd))
        return
    run(cmd)  # lp has handed the files to the spooler once it exits
    shutil.rmtree(paths[0].parent)


def read_csv(path: str) -> list[dict[str, str]]:
    """Rows with lower-cased headers; utf-8-sig drops the BOM Excel writes."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def lines_of(texts: list[str]) -> list[str]:
    return [line for text in texts for line in text.splitlines()]


def label(args: argparse.Namespace) -> list[tuple[list[str], str | None]]:
    if args.csv:
        rows = read_csv(args.csv)
        return [(lines_of([v for k, v in row.items() if k != "qr"]), row.get("qr") or None) for row in rows]
    return [(lines_of(args.text), args.qr)]


def wifi(args: argparse.Namespace) -> list[tuple[list[str], str | None]]:
    if args.csv:
        nets = [
            (
                r.get("ssid", ""),
                r.get("password", ""),
                (r.get("security") or "WPA").upper(),
                r.get("hidden", "").lower() in ("1", "true", "yes"),
            )
            for r in read_csv(args.csv)
        ]
    else:
        if not args.ssid:
            sys.exit("give an SSID, or --csv")
        nets = [(args.ssid, args.password, args.security, args.hidden)]
    labels = []
    for ssid, password, security, hidden in nets:
        if not ssid:
            sys.exit("every network needs an ssid")
        labels.append(([ssid, "" if args.hide_password else password], wifi_qr(ssid, password, security, hidden)))
    return labels


def main(argv: list[str] | None = None) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-s",
        "--size",
        default=os.environ.get("DYMONITE_SIZE", "w162h90"),
        help="CUPS media keyword, see 'dymonite sizes' (default: $DYMONITE_SIZE or w162h90, 2.25 x 1.25 in)",
    )
    common.add_argument(
        "-f",
        "--font",
        default=os.environ.get("DYMONITE_FONT"),
        help="font file or name, e.g. MarkerFelt.ttc (default: $DYMONITE_FONT or a bold sans)",
    )
    common.add_argument(
        "-p",
        "--printer",
        default=os.environ.get("DYMONITE_PRINTER"),
        help="CUPS printer (default: $DYMONITE_PRINTER or the system default)",
    )
    common.add_argument("-n", "--copies", type=int, default=1, help="copies of each label")
    common.add_argument("-o", "--output", help="save PNG(s) here instead of printing")
    common.add_argument("--csv", help="one label per row of this CSV file")
    common.add_argument("--dry-run", action="store_true", help="show the lp command instead of running it")

    parser = argparse.ArgumentParser(prog="dymonite", description=__doc__)
    parser.add_argument("--version", action="version", version=f"dymonite {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "label",
        parents=[common],
        help="text, with an optional QR code (badges, boxes, anything)",
        epilog="CSV columns become lines, in order; a column named qr becomes the QR code.",
    )
    p.add_argument("text", nargs="*", help="lines of text; the first is printed largest")
    p.add_argument("-q", "--qr", help="put a QR code of this text or URL on the right")
    p.set_defaults(make=label)

    p = sub.add_parser(
        "wifi",
        parents=[common],
        help="a Wi-Fi sticker: network, password and a join QR code",
        epilog="CSV columns: ssid, password, security (WPA or WEP), hidden (yes/no).",
    )
    p.add_argument("ssid", nargs="?", help="network name")
    p.add_argument("password", nargs="?", default="", help="leave out for an open network")
    p.add_argument("--security", choices=["WPA", "WEP"], default="WPA", help="WPA covers WPA2 and WPA3 (default)")
    p.add_argument("--hidden", action="store_true", help="the network doesn't broadcast its name")
    p.add_argument("--hide-password", action="store_true", help="put the password in the QR code only")
    p.set_defaults(make=wifi)

    p = sub.add_parser("sizes", help="list a printer's label sizes, from lpoptions")
    p.add_argument(
        "-p",
        "--printer",
        default=os.environ.get("DYMONITE_PRINTER"),
        help="CUPS printer (default: $DYMONITE_PRINTER or the system default)",
    )
    p.set_defaults(make=None)

    args = parser.parse_args(argv)
    if args.make is None:
        return sizes(args)
    if args.copies < 1:
        parser.error("--copies must be at least 1")
    try:
        font = load_font(args.font)
        images = [render(lines, qr, args.size, font) for lines, qr in args.make(args)]
    except ValueError as e:
        sys.exit(f"dymonite: {e}")
    if not images:
        sys.exit("dymonite: the CSV has no rows")
    output(images, args)
