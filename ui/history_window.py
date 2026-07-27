"""Maç geçmişi penceresi.

Üç bölüm: üstte toplam döküm, ortada deste ve rakip sınıfı kırılımları, altta
son maçlar. Sayı yerine çubuk çizmenin sebebi, "hangi eşleşme kötü gidiyor"
sorusunun listeye bakar bakmaz cevaplanması.

Panelin aksine bu pencere saydam değil ve üstte durmaz: oyunun üstünde değil,
oyun dışında okunuyor.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import config
from data.cards import CLASS_HEROES
from data.images import RENDER

from . import i18n, theme
from .i18n import t
from .icon import app_icon
from .widgets import color_dot, hero_portrait

RECENT_LIMIT = 300
ROW_HEIGHT = 24
ICON_SIZE = 18
# Portreler arka planda indiyor, geldiklerinde tabloyu yeniden kurmadan
# yalnızca ikonları değiştiriyoruz.
ART_POLL_MS = 700
WINRATE_WIDTH = 132
# Kırılım tabloları içeriği kadar yer kaplar, uzunsa kaydırılır. Böylece iki
# satırlık deste listesinin altında koca bir boşluk kalmıyor. Sınır oyundaki
# sınıf sayısı: rakip kırılımı hiç kaydırılmadan okunabilsin.
GROUP_MAX_ROWS = 11

# Hücrenin gizli verileri: sıralama anahtarı, sınıf (ikon için), oran (çubuk).
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
RATE_ROLE = Qt.ItemDataRole.UserRole + 2
# Sonuç sütununun sıralaması işaretin harfine göre olmasın.
RESULT_ORDER = {"WON": 2, "TIED": 1, "LOST": 0}


def mode_label(mode: str) -> str:
    """GT_ öneki atılmış mod adını okunur biçime çevirir."""
    key = f"mode_{mode}"
    if i18n.has(key):
        return t(key)
    return mode.replace("_", " ").title() if mode else "?"


def date_label(played_at: str) -> str:
    try:
        stamp = datetime.strptime(played_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return played_at
    return stamp.strftime(t("date_format"))


def class_label(player_class: str) -> str:
    return theme.CLASS_NAMES.get(player_class, player_class or "?")


class ClassIcons:
    """Sınıf portrelerini üretir ve saklar.

    Portre, sınıfın temel kahramanının kart görselinden kesiliyor; görsel henüz
    inmediyse yerini sınıf renginde bir daire tutuyor. Böylece liste ilk açılışta
    da ikonlu görünüyor, indikçe portreye dönüyor.
    """

    def __init__(self, images=None):
        self.images = images
        self.generation = -1
        self._cache: dict[str, QIcon] = {}

    def refreshed(self) -> bool:
        """Yeni görsel indiyse önbelleği boşaltır ve True döner."""
        generation = self.images.generation if self.images is not None else 0
        if generation == self.generation:
            return False
        self.generation = generation
        self._cache.clear()
        return True

    def get(self, player_class: str) -> QIcon:
        icon = self._cache.get(player_class)
        if icon is None:
            icon = QIcon(self._pixmap(player_class))
            self._cache[player_class] = icon
        return icon

    def _pixmap(self, player_class: str):
        card_id = CLASS_HEROES.get(player_class, "")
        path = self.images.get(card_id, RENDER) if self.images and card_id else None
        # İkon iki katı boyutta üretiliyor, yoğun ekranlarda bulanıklaşmasın.
        if path is not None:
            portrait = hero_portrait(path, ICON_SIZE * 2)
            if portrait is not None:
                return portrait
        return color_dot(theme.CLASS_COLORS.get(player_class, theme.TEXT_DIM), ICON_SIZE * 2)


class WinrateDelegate(QStyledItemDelegate):
    """Galibiyet oranını hücrenin içine çubuk olarak çizer.

    Hücre widget'ı (setCellWidget) yerine delegate olmasının sebebi sıralama:
    widget'lar satırla birlikte taşınmıyor, tablo sıralanınca çubuklar yanlış
    satırda kalıyor. Delegate hücrenin verisinden çizdiği için bu sorun yok.
    """

    def paint(self, painter, option, index) -> None:
        rate = index.data(RATE_ROLE)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(6, 0, -6, 0)

        # Yazı alanı en uzun değere göre ölçülüyor: "%100" sığmazsa yüzde
        # kırpılıyor ve %77 ile %7 aynı görünüyor.
        text_width = painter.fontMetrics().horizontalAdvance(t("percent", value="100")) + 2
        bar_width = float(max(rect.width() - text_width - 8, 10))
        thickness = 6.0
        top = rect.y() + (rect.height() - thickness) / 2

        track = QPainterPath()
        track.addRoundedRect(float(rect.x()), top, bar_width, thickness, 3.0, 3.0)
        painter.fillPath(track, QColor(theme.BORDER))

        if rate is not None:
            fill = QPainterPath()
            # En küçük dolgu bile görünsün: %0 da bir bilgidir.
            fill.addRoundedRect(
                float(rect.x()), top, max(bar_width * rate / 100.0, 3.0), thickness, 3.0, 3.0
            )
            painter.fillPath(fill, QColor(theme.WIN if rate >= 50 else theme.LOSS))
            text = t("percent", value=f"{rate:.0f}")
        else:
            text = "–"

        painter.setPen(QPen(QColor(theme.TEXT if rate is not None else theme.TEXT_DIM)))
        painter.drawText(
            QRect(rect.x() + int(bar_width) + 8, rect.y(), text_width, rect.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            text,
        )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(WINRATE_WIDTH, ROW_HEIGHT)


class Cell(QTableWidgetItem):
    """Görünen metne değil, gizli anahtara göre sıralanan hücre.

    Tarih "27.07 22:41" biçiminde yazılıyor, tur bir sayı, sonuç bir işaret:
    üçünü de metne göre sıralamak yanlış sonuç verir.
    """

    def __lt__(self, other) -> bool:
        mine, theirs = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        return mine < theirs


def _table(column_count: int, stretch: int = 0) -> QTableWidget:
    table = QTableWidget(0, column_count)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionsClickable(True)
    for column in range(column_count):
        header.setSectionResizeMode(
            column,
            QHeaderView.ResizeMode.Stretch
            if column == stretch
            else QHeaderView.ResizeMode.ResizeToContents,
        )
    return table


def _fit(table: QTableWidget, max_rows: int) -> None:
    """Tabloyu satır sayısı kadar yükseltir, taşarsa kaydırma çubuğuna bırakır."""
    rows = min(max(table.rowCount(), 1), max_rows)
    table.setFixedHeight(table.horizontalHeader().height() + rows * ROW_HEIGHT + 2)


def _align_right(table: QTableWidget, columns) -> None:
    """Sayı sütunlarının başlığı da sağa yaslansın, veriyle hizalansın."""
    for column in columns:
        item = table.horizontalHeaderItem(column)
        if item is not None:
            item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )


def _item(
    text: str,
    color: str = "",
    align_right: bool = False,
    player_class: str | None = None,
    sort=None,
) -> Cell:
    item = Cell(text)
    if color:
        item.setForeground(QColor(color))
    if align_right:
        item.setTextAlignment(
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        )
    if player_class is not None:
        # İkonun kendisi sonradan basılıyor: portre indiğinde satırı yeniden
        # kurmadan değiştirebilmek için hücre hangi sınıfı gösterdiğini saklıyor.
        item.setData(Qt.ItemDataRole.UserRole, player_class)
    if sort is not None:
        item.setData(SORT_ROLE, sort)
    return item


def _section(title: str, table: QTableWidget, fill: bool = False) -> tuple[QWidget, QLabel]:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    label = QLabel(title)
    label.setObjectName("section")
    layout.addWidget(label)
    layout.addWidget(table)
    if not fill:
        # Boyu içeriğine sabitlenmiş tablo yukarı yaslansın.
        layout.addStretch(1)
    return box, label


class HistoryWindow(QWidget):
    def __init__(self, store, settings: dict, images=None, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.store = store
        self.settings = settings
        self.icons = ClassIcons(images)
        self.mode_filter = ""
        # Tablo -> (sütun, yön). Kullanıcının seçtiği sıralama, tablo yeniden
        # dolduğunda (mod süzgeci, yeni maç, dil değişimi) korunuyor.
        self._sort: dict[QTableWidget, tuple[int, Qt.SortOrder]] = {}
        self._desc_first: dict[QTableWidget, set[int]] = {}
        self._headers: dict[QTableWidget, list[str]] = {}
        self.setObjectName("history")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.STYLESHEET + theme.TABLE_STYLESHEET)
        self._art_timer = QTimer(self)
        self._art_timer.timeout.connect(self._check_art)
        self._build()
        self._restore_geometry()
        self.reload()

    # --- kurulum --------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("title")
        top.addWidget(self.title_label)
        self.totals_label = QLabel()
        self.totals_label.setObjectName("total")
        top.addWidget(self.totals_label, 1)
        self.mode_box = QComboBox()
        self.mode_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.mode_box.currentIndexChanged.connect(self._on_mode_changed)
        top.addWidget(self.mode_box)
        outer.addLayout(top)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("empty")
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(False)
        outer.addWidget(self.empty_label)

        groups = QHBoxLayout()
        groups.setSpacing(14)
        self.deck_table = _table(3)
        self.deck_box, self.deck_title = _section("", self.deck_table)
        groups.addWidget(self.deck_box, 1)
        self.opponent_table = _table(3)
        self.opponent_box, self.opponent_title = _section("", self.opponent_table)
        groups.addWidget(self.opponent_box, 1)
        for table in (self.deck_table, self.opponent_table):
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            table.setColumnWidth(2, WINRATE_WIDTH)
            table.setItemDelegateForColumn(2, WinrateDelegate(table))
            # Varsayılan: en çok oynanan üstte.
            self._init_sort(table, 1, Qt.SortOrder.DescendingOrder, desc_first=(1, 2))
        outer.addLayout(groups)

        # Esneyen sütun rakip: tarih, mod, deste ve rakip solda birbirine
        # yapışık kalıyor, artan yer sonuçtan önceye düşüyor.
        self.recent_table = _table(6, stretch=3)
        self.recent_box, self.recent_title = _section("", self.recent_table, fill=True)
        outer.addWidget(self.recent_box, 1)
        self._init_sort(
            self.recent_table, 0, Qt.SortOrder.DescendingOrder, desc_first=(0, 4, 5)
        )

        # Tablolar gizlendiğinde artan yeri bu boş dolgu yutar, yoksa Qt boşluğu
        # başlık ile mesaj arasına dağıtıp ikisini pencerenin ortasına itiyor.
        self._tail = QWidget()
        outer.addWidget(self._tail)

    # --- sıralama -------------------------------------------------------

    def _init_sort(
        self, table: QTableWidget, column: int, order: Qt.SortOrder, desc_first=()
    ) -> None:
        """Sıralamayı Qt'ye bırakmıyoruz.

        Qt her sütuna artan sırayla başlıyor, oysa sayı sütunlarında beklenen
        "önce en iyisi": galibiyete tıklayınca en iyi eşleşme, tura tıklayınca
        en uzun maç üstte olmalı. Yön seçimi bu yüzden burada.
        """
        self._sort[table] = (column, order)
        self._desc_first[table] = set(desc_first)
        table.horizontalHeader().sectionClicked.connect(
            lambda index, target=table: self._on_header_clicked(target, index)
        )

    def _on_header_clicked(self, table: QTableWidget, column: int) -> None:
        current, order = self._sort[table]
        if column == current:
            order = (
                Qt.SortOrder.AscendingOrder
                if order == Qt.SortOrder.DescendingOrder
                else Qt.SortOrder.DescendingOrder
            )
        elif column in self._desc_first[table]:
            order = Qt.SortOrder.DescendingOrder
        else:
            order = Qt.SortOrder.AscendingOrder
        self._sort[table] = (column, order)
        self._apply_sort(table)

    def _apply_sort(self, table: QTableWidget) -> None:
        column, order = self._sort[table]
        table.sortItems(column, order)
        self._mark_sorted_header(table)

    def _mark_sorted_header(self, table: QTableWidget) -> None:
        """Sıralı sütunu başlıktaki okla gösterir.

        Qt'nin kendi sıralama ibresi, başlığa stil verildiğinde çizilmiyor.
        Oku metnin parçası yapmak hem her temada görünüyor hem de panelin deste
        düğmesindeki dille aynı.
        """
        column, order = self._sort[table]
        arrow = " ▾" if order == Qt.SortOrder.DescendingOrder else " ▴"
        for index, label in enumerate(self._headers.get(table, [])):
            item = table.horizontalHeaderItem(index)
            if item is not None:
                item.setText(label + (arrow if index == column else ""))

    def _set_headers(self, table: QTableWidget, labels: list[str], right=()) -> None:
        self._headers[table] = labels
        table.setHorizontalHeaderLabels(labels)
        _align_right(table, right)
        self._mark_sorted_header(table)

    # --- veri -----------------------------------------------------------

    def reload(self) -> None:
        """Metinleri ve verileri baştan kurar. Dil değişiminde de çağrılır."""
        self.setWindowTitle(t("history_title"))
        self.title_label.setText(t("history_title"))
        self.deck_title.setText(t("history_by_deck"))
        self.opponent_title.setText(t("history_by_opponent"))
        self.recent_title.setText(t("history_recent"))
        self.empty_label.setText(t("history_empty"))
        self._set_headers(
            self.deck_table,
            [t("column_deck"), t("column_record"), t("column_winrate")],
            right=(1,),
        )
        self._set_headers(
            self.opponent_table,
            [t("column_opponent"), t("column_record"), t("column_winrate")],
            right=(1,),
        )
        self._set_headers(
            self.recent_table,
            [
                t("column_date"),
                t("column_mode"),
                t("column_deck"),
                t("column_opponent"),
                t("column_result"),
                t("column_turns"),
            ],
            right=(4, 5),
        )
        self._fill_modes()

        totals = self.store.totals(self.mode_filter)
        self.totals_label.setText(
            t("history_totals", total=totals.total, wins=totals.wins, losses=totals.losses)
            + ("   " + t("percent", value=f"{totals.winrate:.0f}") if totals.winrate is not None else "")
        )
        # Hiç maç yoksa boş tablo iskeleti göstermek yerine tek cümle kalsın.
        empty = totals.total == 0
        self.empty_label.setVisible(empty)
        for box in (self.deck_box, self.opponent_box, self.recent_box):
            box.setVisible(not empty)
        self.layout().setStretchFactor(self._tail, 1 if empty else 0)

        deck_classes = self.store.deck_classes()
        self._fill_groups(
            self.deck_table,
            self.store.summary("deck", self.mode_filter),
            lambda key: key or t("history_no_deck"),
            lambda key: deck_classes.get(key, ""),
        )
        self._fill_groups(
            self.opponent_table,
            self.store.summary("opponent_class", self.mode_filter),
            class_label,
            lambda key: key,
        )
        self._fill_recent()
        self._apply_icons()

    def _fill_modes(self) -> None:
        modes = self.store.modes()
        self.mode_box.blockSignals(True)
        self.mode_box.clear()
        self.mode_box.addItem(t("history_all_modes"), "")
        for mode in modes:
            self.mode_box.addItem(mode_label(mode), mode)
        index = self.mode_box.findData(self.mode_filter)
        # Süzgeçteki mod artık veride yoksa (mesela silinmişse) hepsine dön.
        if index < 0:
            index, self.mode_filter = 0, ""
        self.mode_box.setCurrentIndex(index)
        self.mode_box.blockSignals(False)
        self.mode_box.setVisible(bool(modes))

    def _on_mode_changed(self, _index: int) -> None:
        self.mode_filter = self.mode_box.currentData() or ""
        self.reload()

    def _fill_groups(self, table, stats, label_for, class_for) -> None:
        table.setRowCount(len(stats))
        for row, stat in enumerate(stats):
            player_class = class_for(stat.key)
            table.setItem(
                row,
                0,
                _item(
                    label_for(stat.key),
                    theme.CLASS_COLORS.get(player_class, ""),
                    player_class=player_class,
                ),
            )
            record = f"{stat.wins}-{stat.losses}"
            if stat.ties:
                record += f"-{stat.ties}"
            # Sıralama anahtarları çift: G-M sütunu maç sayısına göre sıralanır
            # (satırın ağırlığı bu), eşitlikte orana bakılır, oran sütununda tersi.
            # Hiç sonuçlanmamış satırın oranı yok, en dibe insin diye -1.
            rate_key = stat.winrate if stat.winrate is not None else -1.0
            table.setItem(
                row, 1, _item(record, theme.TEXT_DIM, True, sort=(stat.total, rate_key))
            )
            rate = _item("", align_right=True, sort=(rate_key, stat.total))
            rate.setData(RATE_ROLE, stat.winrate)
            table.setItem(row, 2, rate)
        self._apply_sort(table)
        _fit(table, GROUP_MAX_ROWS)

    def _fill_recent(self) -> None:
        records = self.store.matches(RECENT_LIMIT, self.mode_filter)
        table = self.recent_table
        table.setRowCount(len(records))
        for row, record in enumerate(records):
            deck = record.deck or class_label(record.my_class)
            opponent = class_label(record.opponent_class)
            # Her anahtarın ikinci parçası zaman damgası: aynı sınıfa karşı ya da
            # aynı tur sayısında oynanan maçlar kendi içinde tarihe göre dizilsin,
            # sıra tesadüfe kalmasın. Tarih sütununda ekrandaki kısa yazı değil
            # tam damga sıralanıyor.
            when = record.played_at
            table.setItem(
                row, 0, _item(date_label(when), theme.TEXT_DIM, sort=when)
            )
            mode = mode_label(record.mode)
            table.setItem(row, 1, _item(mode, theme.TEXT_DIM, sort=(mode, when)))
            table.setItem(
                row, 2, _item(deck, player_class=record.my_class, sort=(deck, when))
            )
            table.setItem(
                row,
                3,
                _item(
                    opponent,
                    theme.CLASS_COLORS.get(record.opponent_class, ""),
                    player_class=record.opponent_class,
                    sort=(opponent, when),
                ),
            )
            mark, color = theme.RESULT_MARKS.get(record.result, ("?", theme.TEXT_DIM))
            result_item = _item(
                mark, color, True, sort=(RESULT_ORDER.get(record.result, -1), when)
            )
            result_item.setToolTip(
                t(i18n.RESULT_KEYS.get(record.result, "result_tied"))
                + " · "
                + t("coin_first" if record.went_first else "coin_second")
            )
            table.setItem(row, 4, result_item)
            table.setItem(
                row,
                5,
                _item(str(record.turns), theme.TEXT_DIM, True, sort=(record.turns, when)),
            )
        self._apply_sort(table)

    # --- ikonlar --------------------------------------------------------

    def _apply_icons(self) -> None:
        """Sınıf saklayan hücrelere portreyi basar.

        Portre diskte yoksa ClassIcons indirmeye alıyor, o ana kadar sınıf
        renginde daire duruyor.
        """
        for table in (self.deck_table, self.opponent_table, self.recent_table):
            for row in range(table.rowCount()):
                for column in range(table.columnCount()):
                    item = table.item(row, column)
                    if item is None:
                        continue
                    player_class = item.data(Qt.ItemDataRole.UserRole)
                    if player_class:
                        item.setIcon(self.icons.get(player_class))

    def _check_art(self) -> None:
        """Yeni portre indiyse yalnızca ikonları değiştir.

        Tabloyu yeniden kurmuyoruz: kullanıcı listeyi kaydırmışken kendiliğinden
        başa dönmesi rahatsız edici.
        """
        if self.icons.refreshed():
            self._apply_icons()

    def showEvent(self, event) -> None:  # noqa: N802
        self._art_timer.start(ART_POLL_MS)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._art_timer.stop()
        super().hideEvent(event)

    # --- geometri -------------------------------------------------------

    def _restore_geometry(self) -> None:
        saved = self.settings.get("geometry", {}).get("history")
        if saved and len(saved) == 2:
            self.resize(max(saved[0], 520), max(saved[1], 380))
        else:
            self.resize(760, 620)

    def closeEvent(self, event) -> None:  # noqa: N802
        geometry = self.settings.setdefault("geometry", {})
        rect = self.geometry()
        geometry["history"] = [rect.width(), rect.height()]
        config.save(self.settings)
        super().closeEvent(event)
