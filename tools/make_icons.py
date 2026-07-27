"""assets/deste.svg dosyasından PNG ikon boyutlarını üretir.

Plasma'nın tepsisi ve uygulama menüsü ikonu isimle çözüyor ve bazı yollarda
SVG yerine hazır PNG bekliyor. install.sh bunları hicolor temasına kopyalar.

Kullanım: python -m tools.make_icons
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SIZES = (16, 22, 24, 32, 48, 64, 96, 128, 256)
ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "deste.svg"
OUT_DIR = ROOT / "assets" / "icons"


def main() -> int:
    from PyQt6.QtCore import QSize, Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    if not SVG_PATH.exists():
        print(f"SVG yok: {SVG_PATH}", file=sys.stderr)
        return 1

    # Referans tutulmazsa QApplication hemen toplanıyor ve ilk QPixmap
    # çağrısında Qt "önce QGuiApplication kur" diyip abort ediyor.
    app = QApplication(sys.argv)  # noqa: F841
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon = QIcon(str(SVG_PATH))
    for size in SIZES:
        pixmap = icon.pixmap(QSize(size, size))
        if pixmap.isNull():
            print(f"{size}px üretilemedi", file=sys.stderr)
            continue
        # Yüksek DPI ölçeklemesi devrede olabilir, istenen boyuta indir.
        # Not: enum yerine düz sayı geçilirse PyQt6 sessizce abort ediyor.
        if pixmap.width() != size:
            pixmap = pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        target = OUT_DIR / f"deste-{size}.png"
        pixmap.save(str(target))
        print(f"  {target.name}  {pixmap.width()}x{pixmap.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
