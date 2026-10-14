import subprocess
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image

from dymonite.cli import main, parse_page_sizes

# `lpoptions -p DYMO_LabelWriter_400 -l` on macOS
LPOPTIONS = (
    "PageSize/Media Size: w154h64 w72h154 w72h72 w162h90 w54h144 w118h252 w167h188 w79h252 w167h252 *w167h288"
    " w154h198 w82h248 w154h64.1 w79h252.1 30334_2-1_4_in_x_1-1_4_in w73h86 Custom.WIDTHxHEIGHT\n"
)


def test_parse_page_sizes():
    names, default = parse_page_sizes("Resolution/Output Resolution: *300dpi\n" + LPOPTIONS)
    assert names[:4] == ["w154h64", "w72h154", "w72h72", "w162h90"]
    assert default == "w167h288"
    assert "Custom.WIDTHxHEIGHT" in names
    assert parse_page_sizes("") == ([], None)


def test_sizes(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, LPOPTIONS))
    main(["sizes", "-p", "DYMO_LabelWriter_400"])
    out = capsys.readouterr().out
    assert "  w162h90                       57.1 x  31.8 mm  2.25 x 1.25 in" in out
    assert "* w167h288" in out
    assert "30334_2-1_4_in_x_1-1_4_in    (named size" in out


def test_save(tmp_path):
    main(["label", "Alex Buie", "-q", "https://packet.boutique", "-o", str(tmp_path / "a.png")])
    img = Image.open(tmp_path / "a.png")
    assert img.size == (675, 375)
    assert round(img.info["dpi"][0]) == 300


def test_csv(tmp_path):
    (tmp_path / "people.csv").write_text(
        "Name,Title,QR\nAlex Buie,Network Engineering,https://packet.boutique\nSam,,\n", "utf-8-sig"
    )
    main(["label", "--csv", str(tmp_path / "people.csv"), "-o", str(tmp_path / "badge.png")])
    assert [r.text for r in zxingcpp.read_barcodes(Image.open(tmp_path / "badge-1.png"))] == ["https://packet.boutique"]
    assert (tmp_path / "badge-2.png").exists()


def test_wifi_csv(tmp_path):
    (tmp_path / "wifi.csv").write_text("ssid,password,security,hidden\nLab,pw;1,wep,Yes\n")
    main(["wifi", "--csv", str(tmp_path / "wifi.csv"), "-o", str(tmp_path / "w.png")])
    assert [r.text for r in zxingcpp.read_barcodes(Image.open(tmp_path / "w.png"))] == [
        r"WIFI:T:WEP;S:Lab;P:pw\;1;H:true;;"
    ]


def test_print(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        assert Image.open(cmd[-1]).size == (675, 375)  # still there while lp runs
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    main(["wifi", "Guest", "Welcome2026!", "-p", "DYMO_LabelWriter_400", "-n", "2"])
    [cmd] = calls
    assert cmd[:-1] == ["lp", "-o", "media=w162h90", "-o", "fit-to-page", "-n", "2", "-d", "DYMO_LabelWriter_400"]
    assert not Path(cmd[-1]).exists()  # temp files cleaned up


def test_dry_run(capsys):
    main(["label", "Box 12", "-s", "w79h252", "--dry-run"])
    assert capsys.readouterr().out.startswith("lp -o media=w79h252 -o fit-to-page -n 1 /")


def test_errors(tmp_path):
    with pytest.raises(SystemExit, match="doesn't fit"):
        main(["label", "x" * 200, "-o", str(tmp_path / "x.png")])
    with pytest.raises(SystemExit, match="wNhM"):
        main(["label", "x", "-s", "57x32mm", "-o", str(tmp_path / "x.png")])
    with pytest.raises(SystemExit, match="font not found"):
        main(["label", "x", "-f", "NoSuchFont.ttf", "-o", str(tmp_path / "x.png")])
