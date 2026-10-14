import pytest
import zxingcpp

from dymonite.label import PAD, media_size, render, wifi_qr


def scan(img):
    return [r.text for r in zxingcpp.read_barcodes(img)]


def test_media_size():
    assert media_size("w162h90") == (675, 375)
    assert media_size("w154h64.1") == (642, 267)
    with pytest.raises(ValueError):
        media_size("30334_2-1_4_in_x_1-1_4_in")


def test_wifi_qr_escapes():
    assert wifi_qr("My;Net", 'p:a"ss\\,') == r"WIFI:T:WPA;S:My\;Net;P:p\:a\"ss\\\,;;"
    assert wifi_qr("Cafe") == "WIFI:T:nopass;S:Cafe;;"
    assert wifi_qr("Lab", "pw", "WEP", hidden=True) == "WIFI:T:WEP;S:Lab;P:pw;H:true;;"
    with pytest.raises(ValueError):
        wifi_qr("Lab", "pw", "WPA2")


@pytest.mark.parametrize(
    "media, password",
    [
        ("w162h90", "correct-horse-battery"),
        ("w162h90", "correct-horse-battery-staple"),  # too long beside a full-height QR: the QR shrinks
        ("w79h252", "hunter22"),  # portrait media: rotated for lp
    ],
)
def test_wifi_label_scans(media, password):
    payload = wifi_qr("Packet Boutique", password)
    img = render(["Packet Boutique", password], payload, media)
    assert img.size == media_size(media)
    assert scan(img) == [payload]


def test_text_stays_inside_the_margins():
    img = render(["A rather long first line", "and a second"])
    w, h = img.size
    for box in [(0, 0, w, PAD), (0, h - PAD, w, h), (0, 0, PAD, h), (w - PAD, 0, w, h)]:
        assert img.crop(box).getextrema() == (255, 255)
    assert img.getextrema()[0] == 0


def test_too_much():
    with pytest.raises(ValueError, match="doesn't fit"):
        render(["x" * 200], "https://example.com")
    with pytest.raises(ValueError, match="too long"):
        render(["x"], "x" * 1000)
    with pytest.raises(ValueError, match="nothing"):
        render(["", " "])
