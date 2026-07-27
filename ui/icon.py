"""Uygulama ikonu.

Önemli ayrıntı: ikonu QIcon.fromTheme ile kurarsak Qt, sistem tepsisine
(StatusNotifierItem) ikonun kendisini değil *adını* gönderiyor. Plasma o adı
kendi ikon önbelleğinden çözmeye çalışıyor ve yeni kurulmuş bir ikonu
bulamayınca tepside boş kare çıkıyor.

Bu yüzden ikon her zaman dosyadan kuruluyor ve önceden üretilmiş PNG'ler
eklenerek gerçek piksel verisi taşınıyor. Böylece tepsi ikonu, tema önbelleği
ne durumda olursa olsun görünüyor.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from . import theme

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SVG_PATH = ASSETS / "deste.svg"
PNG_DIR = ASSETS / "icons"
PNG_SIZES = (16, 22, 24, 32, 48, 64, 96, 128, 256)

_cached: QIcon | None = None


def _fallback_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    scale = size / 64.0
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.BACKGROUND))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 13, 13)
    painter.setBrush(QColor(theme.MANA_BLUE))
    painter.drawRoundedRect(QRectF(16, 14, 24, 34), 4, 4)
    painter.setBrush(QColor(theme.ACCENT))
    painter.drawRoundedRect(QRectF(25, 13, 25, 36), 4, 4)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    global _cached
    if _cached is not None:
        return _cached

    icon = QIcon()
    added = False

    for size in PNG_SIZES:
        png = PNG_DIR / f"deste-{size}.png"
        if png.exists():
            pixmap = QPixmap(str(png))
            if not pixmap.isNull():
                icon.addPixmap(pixmap)
                added = True

    if not added and SVG_PATH.exists():
        source = QIcon(str(SVG_PATH))
        for size in PNG_SIZES:
            pixmap = source.pixmap(QSize(size, size))
            if not pixmap.isNull():
                icon.addPixmap(pixmap)
                added = True

    if not added:
        for size in PNG_SIZES:
            icon.addPixmap(_fallback_pixmap(size))

    _cached = icon
    return _cached
