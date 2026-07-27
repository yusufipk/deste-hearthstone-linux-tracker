"""Kart satırı, kart listesi ve fareyle üzerine gelince açılan kart önizlemesi.

Satır tasarımı: kart sanatının şeridi (256x59) satırın arka planında durur,
soldan sağa koyu bir gradyanla kararır ki üstündeki yazı okunsun. Solda mana
bedeli, sağda adet. Bu düzen deck tracker'ların oturmuş dili, oyundan gelen
görselle birlikte satır tanınabilir oluyor.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from data.images import RENDER, TILE

from . import theme

ROW_HEIGHT = 26
COST_WIDTH = 26
COUNT_WIDTH = 30
PREVIEW_DELAY_MS = 200
HIDE_DELAY_MS = 140
PREVIEW_GAP = 8


class ElidedLabel(QLabel):
    """Metni kısaltarak gösteren, genişliği pencereye dayatmayan etiket.

    Düz QLabel uzun metinde sizeHint'ini büyütüyor, üst düzey pencerede bu
    minimum genişliğe dönüşüyor ve pencere kendiliğinden genişliyordu (maç
    sonucu yazısı geldiğinde panel şişiyordu). Burada sizeHint yok sayılıyor,
    metin sığmazsa üç noktayla kesiliyor.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._apply()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def set_full_text(self, text: str) -> None:
        if text != self._full:
            self._full = text
            self._apply()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        width = self.width()
        if width <= 0:
            super().setText(self._full)
            return
        super().setText(
            self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, width)
        )


class CardRow(QWidget):
    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.images = images
        self.setFixedHeight(ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.card_id = ""
        self.card_name = ""
        self.cost = 0
        self.count = 1
        self.rarity = ""
        self.chance = None
        self.faded = False
        # Panelin saydamlığı satırlara da uygulanır, yoksa oyun yalnızca
        # kenarlardan görünür ve overlay opak bir blok gibi durur.
        self.opacity = 1.0
        self._pixmap: QPixmap | None = None
        self._pixmap_source = ""

    def set_card(
        self,
        card_id: str,
        name: str,
        cost: int,
        count: int,
        rarity: str = "",
        chance=None,
        faded: bool = False,
    ) -> None:
        changed = card_id != self.card_id
        self.card_id = card_id
        self.card_name = name
        self.cost = cost
        self.count = count
        self.rarity = rarity
        self.chance = chance
        self.faded = faded
        if changed:
            self._pixmap = None
            self._pixmap_source = ""
        self.update()

    def _tile(self) -> QPixmap | None:
        """Sanat şeridi. Diskte yoksa indirmeye alınır, o ana kadar düz zemin."""
        path = self.images.get(self.card_id, TILE) if self.images else None
        if path is None:
            return None
        if self._pixmap is not None and self._pixmap_source == str(path):
            return self._pixmap
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None
        self._pixmap = pixmap
        self._pixmap_source = str(path)
        return pixmap

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt adlandırması)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        width, height = self.width(), self.height() - 2
        if width <= 0 or height <= 0:
            return

        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(width), float(height), 3.0, 3.0)
        painter.setClipPath(path)

        # Zemin ve sanat panel saydamlığını izler, yazı biraz daha opak kalır
        # ki oyunun üstünde okunabilirliği düşmesin.
        base_opacity = self.opacity
        text_opacity = min(1.0, self.opacity + 0.22)

        painter.setOpacity(base_opacity)
        painter.fillRect(0, 0, width, height, QColor(theme.ROW_BASE))

        tile = self._tile()
        if tile is not None:
            # Şerit satırın tamamını kaplar, dikeyde ortadan kırpılır. Sağa
            # yaslamak satırın ortasında sert bir kesik bırakıyordu.
            scaled = tile.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            top = max((scaled.height() - height) // 2, 0)
            painter.setOpacity(base_opacity * (0.62 if self.faded else 0.95))
            painter.drawPixmap(
                QRect(0, 0, width, height), scaled, QRect(0, top, width, height)
            )
            painter.setOpacity(base_opacity)

            # Soldan sağa kararan gradyan: isim her zaman okunur kalsın.
            gradient = QLinearGradient(0, 0, width, 0)
            gradient.setColorAt(0.0, QColor(theme.ROW_BASE))
            gradient.setColorAt(0.30, QColor(*theme.rgb(theme.ROW_BASE), 240))
            gradient.setColorAt(0.62, QColor(*theme.rgb(theme.ROW_BASE), 170))
            gradient.setColorAt(1.0, QColor(*theme.rgb(theme.ROW_BASE), 55))
            painter.fillRect(0, 0, width, height, gradient)

        if self.faded:
            # Kullanılmış kart: listeden düşmez, kararır. Tamamen silmek yerine
            # yerinde bırakmak "bunu çektim" bilgisini görünür tutuyor.
            painter.fillRect(0, 0, width, height, QColor(0, 0, 0, 95))

        # Mana bedeli kutusu
        painter.setOpacity(base_opacity)
        cost_color = QColor(theme.MANA_BLUE)
        painter.fillRect(0, 0, COST_WIDTH, height, cost_color)
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 0.5)
        painter.setFont(font)
        painter.setOpacity(text_opacity)
        painter.setPen(QPen(QColor("#ffffff" if not self.faded else theme.TEXT_DIM)))
        painter.drawText(
            QRect(0, 0, COST_WIDTH, height),
            int(Qt.AlignmentFlag.AlignCenter),
            str(self.cost),
        )

        # Nadirlik şeridi mana kutusunun hemen sağında
        painter.fillRect(
            COST_WIDTH, 0, 2, height, QColor(theme.RARITY_COLORS.get(self.rarity, theme.TEXT_DIM))
        )

        # Adet ve yüzde
        font.setBold(self.count > 1)
        painter.setFont(font)
        right_edge = width - 6
        align_right = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        def draw_badge(rect: QRect, text: str, color: str, strong: bool) -> None:
            """Sayıyı koyu bir kutunun içine yazar.

            Kart sanatının parlak kısımlarında sadece gölge yetmiyordu, sayılar
            kayboluyordu. Arkasına yarı opak bir zemin koyunca her kartta okunur
            oluyor.
            """
            painter.setOpacity(min(1.0, base_opacity + 0.15))
            badge = QPainterPath()
            badge.addRoundedRect(
                float(rect.x() - 3), 3.0, float(rect.width() + 6), float(height - 6), 3.0, 3.0
            )
            painter.fillPath(badge, QColor(8, 10, 16, 215 if strong else 185))
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(color)))
            painter.drawText(rect, align_right, text)

        if self.chance is not None:
            draw_badge(
                QRect(right_edge - 30, 0, 30, height),
                f"%{self.chance:.0f}",
                theme.TEXT if not self.faded else theme.TEXT_DIM,
                False,
            )
            right_edge -= 38
        if self.count > 1:
            draw_badge(
                QRect(right_edge - 16, 0, 16, height),
                str(self.count),
                theme.ACCENT,
                True,
            )
            right_edge -= 26

        # İsim, gölgeli çizilir ki sanatın üstünde kaybolmasın
        name_rect = QRect(COST_WIDTH + 8, 0, max(right_edge - COST_WIDTH - 12, 20), height)
        font.setBold(False)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        elided = metrics.elidedText(self.card_name, Qt.TextElideMode.ElideRight, name_rect.width())
        painter.setPen(QPen(QColor(0, 0, 0, 190)))
        painter.drawText(name_rect.translated(1, 1), int(Qt.AlignmentFlag.AlignVCenter), elided)
        painter.setPen(QPen(QColor(theme.TEXT if not self.faded else theme.TEXT_DIM)))
        painter.drawText(name_rect, int(Qt.AlignmentFlag.AlignVCenter), elided)
        painter.end()

    # --- önizleme -------------------------------------------------------

    def enterEvent(self, event) -> None:  # noqa: N802
        window = self.window()
        preview = getattr(window, "preview", None)
        if preview is not None and self.card_id:
            preview.request(self.card_id, self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        window = self.window()
        preview = getattr(window, "preview", None)
        if preview is not None:
            preview.cancel()
        super().leaveEvent(event)


class CardPreview(QWidget):
    """Fareyle üzerine gelinen kartın tam görseli.

    Kartın kendi render'ı metnini de içerdiği için ayrıca açıklama yazmaya
    gerek kalmıyor. Görsel henüz inmediyse pencere açılmaz, indiği anda çıkar.
    """

    def __init__(self, images, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.images = images
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Önizleme fare olaylarını yutarsa satır "fare çıktı" sanıp gizliyor,
        # sonra fare tekrar satıra giriyor ve açılıp kapanma döngüsü oluşuyor.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label = QLabel(self)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self._card_id = ""
        self._anchor: QWidget | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._show_now)
        # Satırdan satıra geçerken önizleme kapanıp açılmasın diye gizleme
        # kısa bir gecikmeyle yapılıyor; bu arada yeni istek gelirse iptal olur.
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def request(self, card_id: str, anchor: QWidget) -> None:
        self._hide_timer.stop()
        if card_id == self._card_id and self.isVisible():
            self._anchor = anchor
            return
        self._card_id = card_id
        self._anchor = anchor
        self.images.get(card_id, RENDER)
        if self.isVisible():
            # Zaten açıksa gecikmeye gerek yok, doğrudan kartı değiştir.
            self._show_now()
        else:
            self._timer.start(PREVIEW_DELAY_MS)

    def cancel(self) -> None:
        self._timer.stop()
        self._hide_timer.start(HIDE_DELAY_MS)

    def _show_now(self) -> None:
        if not self._card_id or self._anchor is None:
            return
        path = self.images.get(self._card_id, RENDER)
        if path is None:
            # Görsel hâlâ iniyor, birazdan tekrar dene.
            self._timer.start(400)
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self._label.setPixmap(pixmap)
        self.resize(pixmap.size())

        # Konum yalnızca pencerenin kendi koordinatlarından üretilir.
        # Wayland'da uygulama pencerenin gerçek ekran konumunu bilmiyor;
        # ekran kenarına göre kırpma yapmaya kalkarsak (eski "max(y, 0)")
        # önizleme paletin dibine düşüyor. Pencereye göre hesaplayınca
        # aradaki bilinmeyen kayma sadeleşiyor, ekran kenarını da bileşik
        # yönetici kendisi düzeltiyor.
        window = self._anchor.window()
        origin = window.mapToGlobal(QPoint(0, 0))
        anchor = self._anchor.mapToGlobal(QPoint(0, 0))
        x = origin.x() - pixmap.width() - PREVIEW_GAP
        y = anchor.y() + self._anchor.height() // 2 - pixmap.height() // 2
        top = origin.y()
        bottom = max(origin.y() + window.height() - pixmap.height(), top)
        self.move(x, min(max(y, top), bottom))
        if not self.isVisible():
            self.show()
        self.raise_()


class CardList(QWidget):
    """Satırları havuzda tutan liste. Her güncellemede widget yaratmak titretir."""

    def __init__(self, images, parent=None):
        super().__init__(parent)
        self.images = images
        self.opacity = 1.0
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._rows: list[CardRow] = []
        self._empty = QLabel("")
        self._empty.setObjectName("empty")
        self._empty.setWordWrap(True)
        self._empty.setVisible(False)
        self._layout.addWidget(self._empty)
        self._layout.addStretch(1)

    def set_empty_text(self, text: str) -> None:
        self._empty.setText(text)

    def set_opacity(self, value: float) -> None:
        self.opacity = value
        for row in self._rows:
            row.opacity = value
            row.update()

    def set_cards(self, entries: list[dict]) -> None:
        self._empty.setVisible(not entries)
        while len(self._rows) < len(entries):
            row = CardRow(self.images, self)
            row.opacity = self.opacity
            self._rows.append(row)
            self._layout.insertWidget(self._layout.count() - 1, row)
        for index, row in enumerate(self._rows):
            if index < len(entries):
                entry = entries[index]
                row.set_card(
                    entry.get("card_id", ""),
                    entry.get("name", "?"),
                    entry.get("cost", 0),
                    entry.get("count", 1),
                    entry.get("rarity", ""),
                    entry.get("chance"),
                    entry.get("faded", False),
                )
                row.setVisible(True)
            else:
                row.setVisible(False)

    def repaint_rows(self) -> None:
        """Yeni görsel indiğinde satırları tazeler."""
        for row in self._rows:
            if row.isVisible():
                row.update()
