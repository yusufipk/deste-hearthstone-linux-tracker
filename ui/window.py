"""Tracker penceresi.

İki mod:
  overlay : çerçevesiz, üstte duran, sürüklenebilir, yarı saydam panel
  window  : sıradan pencere (başlık çubuğu, Alt+Tab)

Wayland'da uygulama kendini "her zaman üstte" yapamaz, bunu pencere yöneticisi
belirler; install.sh bunun için bir KWin kuralı yazıyor.
"""

from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import config, history
from core.state import Game
from data.images import TILE, ImageCache

from . import i18n, theme
from .i18n import LANGUAGE_NAMES, LANGUAGES, t
from .icon import app_icon
from .widgets import CardList, CardPreview, ElidedLabel

POLL_INTERVAL_MS = 400
MIN_WIDTH = 210
MIN_HEIGHT = 260
OPACITY_STEPS = [1.00, 0.90, 0.75, 0.60, 0.45]


class ClassDot(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self.set_class("NEUTRAL")

    def set_class(self, player_class: str) -> None:
        color = theme.CLASS_COLORS.get(player_class, theme.TEXT_DIM)
        self.setStyleSheet(f"background: {color}; border-radius: 4px;")


class TrackerWindow(QWidget):
    def __init__(self, watcher, library, cards, settings: dict):
        super().__init__()
        self.watcher = watcher
        self.library = library
        self.cards = cards
        self.settings = settings
        self.mode = settings.get("window_mode", "overlay")
        self.images = ImageCache()
        self.history = history.History()
        self.history_window = None
        # En son geçmişe yazılan maç. Sonuç geldikten sonra panel daha birkaç
        # kez tazeleniyor, aynı maçı her seferinde yazmaya kalkmayalım.
        self._recorded_key: tuple[str, str] | None = None
        # Önizleme pencereye bağlı: Wayland'da konumlandırılabilmesi için
        # bir ebeveyne bağlı popup olması gerekiyor, başıboş pencere taşınamaz.
        self.preview = CardPreview(self.images, self)
        self._last_signature = None
        # Boyut ve konum değişikliklerini hemen değil, kısa bir gecikmeyle
        # kaydediyoruz: sürükleme sırasında her pikselde dosyaya yazmayalım.
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.timeout.connect(self._save_geometry)
        self._last_image_generation = -1

        self.setWindowTitle("deste")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(theme.STYLESHEET)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build()
        self._build_tray()
        self._apply_mode(self.mode, first=True)

        self._apply_opacity()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(POLL_INTERVAL_MS)
        self._refresh(force=True)

    # --- kurulum --------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        # Yerleşimin minimum boyutu pencereye dayatılmasın: maç sonucu gibi
        # yeni bir yazı geldiğinde pencere kendiliğinden genişliyordu ve
        # kullanıcı her maçta boyutu elle düzeltmek zorunda kalıyordu.
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)

        # Üst çubuk: başlık ve deste seçimi ayrı bir zeminde dursun ki panel
        # düz bir liste yığını gibi görünmesin.
        topbar = QWidget()
        topbar.setObjectName("topbar")
        outer.addWidget(topbar)
        top_layout = QVBoxLayout(topbar)
        top_layout.setContentsMargins(10, 8, 8, 8)
        top_layout.setSpacing(6)

        body = QWidget()
        outer.addWidget(body, 1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(9, 8, 9, 9)
        layout.setSpacing(6)

        # Başlık: sınıf noktaları, tur, menü
        header = QHBoxLayout()
        header.setSpacing(6)
        self.my_dot = ClassDot()
        header.addWidget(self.my_dot)
        self.header_label = ElidedLabel(t("waiting_match"))
        self.header_label.setObjectName("header")
        header.addWidget(self.header_label, 1)
        # Sabit genişlik: "T12" ile "T12 ✓" arasındaki fark pencereyi büyütmesin.
        self.turn_label = QLabel("")
        self.turn_label.setObjectName("dim")
        self.turn_label.setFixedWidth(48)
        self.turn_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header.addWidget(self.turn_label)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("menu")
        self.menu_button.setText("⋮")
        self.menu = self._build_menu()
        self.menu_button.clicked.connect(
            lambda: self._popup(self.menu_button, self.menu, align_right=True)
        )
        header.addWidget(self.menu_button)
        top_layout.addLayout(header)

        # Deste satırı
        deck_row = QHBoxLayout()
        deck_row.setSpacing(6)
        self.deck_button = QToolButton()
        self.deck_button.setToolTip(t("deck_tooltip"))
        self.deck_button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.deck_button.clicked.connect(
            lambda: self._popup(self.deck_button, self.deck_menu, align_right=False)
        )
        deck_row.addWidget(self.deck_button, 1)
        # Elimdeki kart sayısı destede kalanın solunda: rakip satırındaki
        # "el N deste N" ile aynı sıra, aynı okuma yönü.
        self.my_hand_label = QLabel("")
        self.my_hand_label.setObjectName("dim")
        self.my_hand_label.setToolTip(t("hand_tooltip"))
        deck_row.addWidget(self.my_hand_label)
        self.deck_count_label = QLabel("")
        self.deck_count_label.setObjectName("count")
        self.deck_count_label.setToolTip(t("deck_count_tooltip"))
        deck_row.addWidget(self.deck_count_label)
        top_layout.addLayout(deck_row)
        self._rebuild_deck_menu()

        # Kendi destem
        self.my_list = CardList(self.images)
        self.my_list.set_empty_text(t("deck_empty"))
        layout.addWidget(self._scrollable(self.my_list), 3)

        # Rakip
        opponent_header = QHBoxLayout()
        opponent_header.setSpacing(6)
        self.opponent_dot = ClassDot()
        opponent_header.addWidget(self.opponent_dot)
        self.opponent_title = QLabel(t("opponent_title"))
        self.opponent_title.setObjectName("section")
        opponent_header.addWidget(self.opponent_title, 1)
        self.opponent_counts = QLabel("")
        self.opponent_counts.setObjectName("dim")
        opponent_header.addWidget(self.opponent_counts)
        layout.addLayout(opponent_header)

        self.opponent_list = CardList(self.images)
        self.opponent_list.set_empty_text(t("opponent_empty"))
        layout.addWidget(self._scrollable(self.opponent_list), 2)

        # Overlay modunda pencere çerçevesi yok, boyutlandırmak için köşede
        # bir tutamak gerekiyor. Wayland'da startSystemResize üzerinden çalışır.
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(14, 14)
        self.size_grip.installEventFilter(self)
        grip_row.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(grip_row)

    @staticmethod
    def _scrollable(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        area.viewport().setAutoFillBackground(False)
        return area

    def _build_menu(self) -> QMenu:
        menu = QMenu(self)
        self.mode_action = QAction(
            t("menu_to_window") if self.mode == "overlay" else t("menu_to_overlay"), self
        )
        self.mode_action.triggered.connect(self._toggle_mode)
        menu.addAction(self.mode_action)

        opacity_menu = menu.addMenu(t("menu_opacity"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = float(self.settings.get("opacity", 0.90))
        for value in OPACITY_STEPS:
            label = (
                t("opacity_full")
                if value >= 1.0
                else t("opacity_step", value=round(value * 100))
            )
            action = QAction(label, self, checkable=True)
            action.setChecked(abs(value - current) < 0.01)
            action.triggered.connect(lambda _checked, v=value: self._set_opacity(v))
            group.addAction(action)
            opacity_menu.addAction(action)

        self.chance_action = QAction(t("menu_draw_chance"), self, checkable=True)
        self.chance_action.setChecked(bool(self.settings.get("show_draw_chance", True)))
        self.chance_action.triggered.connect(self._toggle_chance)
        menu.addAction(self.chance_action)

        language_menu = menu.addMenu(t("menu_language"))
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        for code in LANGUAGES:
            action = QAction(LANGUAGE_NAMES[code], self, checkable=True)
            action.setChecked(code == i18n.current())
            action.triggered.connect(lambda _checked, c=code: self._set_language(c))
            language_group.addAction(action)
            language_menu.addAction(action)

        menu.addSeparator()
        history_action = QAction(t("menu_history"), self)
        history_action.triggered.connect(self._show_history)
        menu.addAction(history_action)
        reload_action = QAction(t("menu_reload_decks"), self)
        reload_action.triggered.connect(self._reload_decks)
        menu.addAction(reload_action)

        menu.addSeparator()
        hide_action = QAction(t("menu_hide"), self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)
        quit_action = QAction(t("menu_quit"), self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        return menu

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("deste")
        self.tray_menu = QMenu()
        self._fill_tray_menu()
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _fill_tray_menu(self) -> None:
        self.tray_menu.clear()
        show_action = QAction(t("tray_toggle"), self)
        show_action.triggered.connect(self._toggle_visible)
        self.tray_menu.addAction(show_action)
        mode_action = QAction(t("tray_mode"), self)
        mode_action.triggered.connect(self._toggle_mode)
        self.tray_menu.addAction(mode_action)
        self.tray_menu.addSeparator()
        quit_action = QAction(t("menu_quit"), self)
        quit_action.triggered.connect(self._quit)
        self.tray_menu.addAction(quit_action)

    def _set_language(self, code: str) -> None:
        """Dili anında değiştirir: menüler ve sabit metinler yeniden kurulur."""
        if code == i18n.current():
            return
        i18n.set_language(code)
        self.settings["language"] = code
        config.save(self.settings)
        self.menu = self._build_menu()
        self._fill_tray_menu()
        self.deck_button.setToolTip(t("deck_tooltip"))
        self.my_hand_label.setToolTip(t("hand_tooltip"))
        self.deck_count_label.setToolTip(t("deck_count_tooltip"))
        self.my_list.set_empty_text(t("deck_empty"))
        self.opponent_list.set_empty_text(t("opponent_empty"))
        self.opponent_title.setText(t("opponent_title"))
        self._rebuild_deck_menu()
        if self.history_window is not None:
            self.history_window.reload()
        self._refresh(force=True)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visible()

    def _toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def _quit(self) -> None:
        self._save_geometry()
        self.images.shutdown()
        self.history.close()
        if self.history_window is not None:
            self.history_window.close()
        self.tray.hide()
        from PyQt6.QtWidgets import QApplication

        QApplication.quit()

    def _rebuild_deck_menu(self) -> None:
        menu = QMenu(self)
        group = QActionGroup(self)
        group.setExclusive(True)
        selected = self.settings.get("selected_deck", "")
        auto_label = t("deck_auto")
        for name in [auto_label] + [d.name for d in self.library.decks]:
            action = QAction(name, self, checkable=True)
            action.setChecked((name == auto_label and not selected) or name == selected)
            action.triggered.connect(lambda _checked, n=name: self._select_deck(n))
            group.addAction(action)
            menu.addAction(action)
        self.deck_menu = menu
        self._set_deck_text(selected or auto_label)

    def _set_deck_text(self, name: str) -> None:
        # Ok işareti metnin parçası: menü düğmeye setMenu ile bağlı olmadığı
        # için Qt'nin kendi göstergesi çizilmiyor.
        self.deck_button.setText(f"{name}  ▾")

    def _set_turn_text(self, game: Game | None) -> None:
        """Tur sayısı ve maç sonucu.

        Sonuç "WON" yazısıyla değil renkli bir işaretle gösteriliyor: etiket
        sabit genişlikte kalsın, yazı geldiğinde panel büyümesin diye.
        """
        if game is None:
            self.turn_label.setText("")
            self.turn_label.setToolTip("")
            return
        mark, color = theme.RESULT_MARKS.get(game.result, ("", ""))
        if mark:
            self.turn_label.setText(
                f'T{game.game_turn} <span style="color:{color}">{mark}</span>'
            )
            self.turn_label.setToolTip(t(i18n.RESULT_KEYS[game.result]))
        else:
            self.turn_label.setText(f"T{game.game_turn}")
            self.turn_label.setToolTip("")

    def _popup(self, button: QToolButton, menu: QMenu, align_right: bool) -> None:
        """Menüyü düğmenin altında açar.

        Qt'nin kendi yerleştirmesi menüyü ekrana sığdırmaya çalışırken
        pencerenin gerçek konumunu bildiğini varsayıyor. Wayland'da bilmiyor,
        o yüzden menü ekranın dibine düşüyordu. Konumu düğmeden türetince
        menü her zaman düğmenin altında açılıyor.
        """
        width = menu.sizeHint().width()
        x = button.width() - width if align_right else 0
        menu.popup(button.mapToGlobal(QPoint(x, button.height() + 3)))

    def _show_history(self) -> None:
        from .history_window import HistoryWindow

        if self.history_window is None:
            self.history_window = HistoryWindow(self.history, self.settings, self.images)
        else:
            self.history_window.reload()
        self.history_window.show()
        self.history_window.raise_()
        self.history_window.activateWindow()

    def _reload_decks(self) -> None:
        self.library.load()
        self._rebuild_deck_menu()
        self._refresh(force=True)

    def _select_deck(self, name: str) -> None:
        self.settings["selected_deck"] = "" if name == t("deck_auto") else name
        config.save(self.settings)
        self._set_deck_text(name)
        self._refresh(force=True)

    def _set_opacity(self, value: float) -> None:
        self.settings["opacity"] = value
        config.save(self.settings)
        self._apply_opacity()

    def _apply_opacity(self) -> None:
        value = float(self.settings.get("opacity", 0.90))
        self.my_list.set_opacity(value)
        self.opponent_list.set_opacity(value)
        self.update()

    def _toggle_chance(self) -> None:
        self.settings["show_draw_chance"] = self.chance_action.isChecked()
        config.save(self.settings)
        self._refresh(force=True)

    # --- zemin ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        """Yarı saydam, yuvarlatılmış zemin. Oyun arkadan görünsün diye."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = int(255 * float(self.settings.get("opacity", 0.90)))
        path = QPainterPath()
        radius = 10.0 if self.mode == "overlay" else 6.0
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), radius, radius)
        painter.fillPath(path, QColor(*theme.rgb(theme.BACKGROUND), alpha))
        pen_color = QColor(*theme.rgb(theme.BORDER), min(alpha + 40, 255))
        painter.setPen(pen_color)
        painter.drawPath(path)
        painter.end()

    # --- mod yönetimi ---------------------------------------------------

    def _toggle_mode(self) -> None:
        self._save_geometry()
        self._apply_mode("window" if self.mode == "overlay" else "overlay")

    def _apply_mode(self, mode: str, first: bool = False) -> None:
        self.mode = mode
        self.settings["window_mode"] = mode
        config.save(self.settings)

        if mode == "overlay":
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowStaysOnTopHint
            )
            self.mode_action.setText(t("menu_to_window"))
        else:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
            self.mode_action.setText(t("menu_to_overlay"))

        self.size_grip.setVisible(mode == "overlay")
        self._restore_geometry()
        self.show()

    def _save_geometry(self) -> None:
        # Yalnızca boyut saklanır. Wayland'da pencerenin konumunu bileşik
        # yönetici belirliyor ve uygulamaya söylemiyor; buradan okunan konum
        # gerçeği yansıtmıyor, kaydedip geri yüklersek pencere ekran dışına
        # düşmüş gibi davranıyor ve menüler yanlış yere açılıyor.
        geometry = self.settings.setdefault("geometry", {})
        rect = self.geometry()
        geometry[self.mode] = [rect.width(), rect.height()]
        config.save(self.settings)

    def _restore_geometry(self) -> None:
        saved = self.settings.get("geometry", {}).get(self.mode)
        if saved and len(saved) == 4:  # eski biçim: x, y, w, h
            saved = saved[2:]
        if saved and len(saved) == 2:
            self.resize(max(saved[0], MIN_WIDTH), max(saved[1], MIN_HEIGHT))
        else:
            self.resize(310, 640)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Taşımayı pencere yöneticisi yapar. Kendi move() çağrımız Wayland'da
        # pencereyi kıpırdatmıyor, sadece Qt'nin konum bilgisini bozuyordu.
        if self.mode == "overlay" and event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()

    def eventFilter(self, obj, event):  # noqa: N802
        # Boyut tutamağı bırakıldığında yeni boyutu kaydet. Pencere yöneticisi
        # ya da tiling script'i boyutu değiştirdiğinde kaydetmiyoruz, yoksa
        # bizim tercihimiz onların dayattığı boyutla eziliyor.
        if obj is self.size_grip and event.type() == QEvent.Type.MouseButtonRelease:
            self._geometry_timer.start(200)
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Kapatma tepsiye gizler, uygulama arka planda kalır.
        self._save_geometry()
        if self.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)

    # --- güncelleme -----------------------------------------------------

    def _tick(self) -> None:
        changed = self.watcher.poll()
        if changed:
            self._refresh()
        if self.images.generation != self._last_image_generation:
            self._last_image_generation = self.images.generation
            self.my_list.repaint_rows()
            self.opponent_list.repaint_rows()

    def _selected_deck(self, game: Game | None):
        name = self.settings.get("selected_deck", "")
        if name:
            for deck in self.library.decks:
                if deck.name == name:
                    return deck
        if game is None:
            return None
        return self.library.match(game)

    def _entry(self, card_id: str, count: int, chance=None, faded: bool = False) -> dict:
        return {
            "card_id": card_id,
            "name": self.cards.name(card_id),
            "cost": self.cards.cost(card_id),
            "count": count,
            "rarity": self.cards.rarity(card_id),
            "chance": chance,
            "faded": faded,
        }

    def _refresh(self, force: bool = False) -> None:
        game = self.watcher.game
        signature = self._signature(game)
        if not force and signature == self._last_signature:
            return
        self._last_signature = signature

        if game is None or game.local_player_id is None:
            self.header_label.set_full_text(t("waiting_match"))
            self._set_turn_text(None)
            self.my_dot.set_class("NEUTRAL")
            self.opponent_dot.set_class("NEUTRAL")
            self.my_list.set_cards([])
            self.opponent_list.set_cards([])
            self.my_hand_label.setText("")
            self.deck_count_label.setText("")
            self.opponent_counts.setText("")
            return

        my_class = self.cards.card_class(game.hero_card_id(game.local_player_id))
        opponent_class = self.cards.card_class(game.hero_card_id(game.opponent_player_id))
        self.my_dot.set_class(my_class or "NEUTRAL")
        self.opponent_dot.set_class(opponent_class or "NEUTRAL")
        self.header_label.set_full_text(
            f"{theme.CLASS_NAMES.get(my_class, my_class or '?')}"
            f"   vs   {theme.CLASS_NAMES.get(opponent_class, opponent_class or '?')}"
        )
        self._set_turn_text(game)

        self.my_hand_label.setText(t("hand_count", hand=game.my_hand_count))

        deck = self._selected_deck(game)
        if deck is not None:
            if not self.settings.get("selected_deck"):
                self._set_deck_text(deck.name)
            remaining = game.remaining_deck(deck.cards)
            total = sum(remaining.values())
            self.deck_count_label.setText(str(total))
            show_chance = bool(self.settings.get("show_draw_chance", True))

            # Destede kalmayan kartlar listeden düşmez, solgun gösterilir:
            # "bu kartı çektim/oynadım" bilgisi listeden silinince kayboluyor.
            all_cards = Counter(deck.cards)
            all_cards.update(game.cards_shuffled_in)
            entries = []
            for card_id in sorted(
                all_cards, key=lambda c: (self.cards.cost(c), self.cards.name(c))
            ):
                count = remaining.get(card_id, 0)
                entries.append(
                    self._entry(
                        card_id,
                        count,
                        (100.0 * count / total) if (show_chance and total and count) else None,
                        faded=count == 0,
                    )
                )
            self.my_list.set_cards(entries)
            self.my_list.set_opacity(float(self.settings.get("opacity", 0.90)))
            self.images.prefetch([e["card_id"] for e in entries], TILE)
        else:
            self.deck_count_label.setText(str(game.my_deck_count))
            self.my_list.set_cards([])

        self.opponent_counts.setText(
            t(
                "opponent_counts",
                hand=game.opponent_hand_count,
                deck=game.opponent_deck_count,
            )
        )
        seen: dict[str, int] = {}
        for event in game.opponent_events:
            if event.card_id:
                seen[event.card_id] = seen.get(event.card_id, 0) + 1
        opponent_entries = [
            self._entry(card_id, count)
            for card_id, count in sorted(
                seen.items(), key=lambda kv: (self.cards.cost(kv[0]), self.cards.name(kv[0]))
            )
        ]
        self.opponent_list.set_cards(opponent_entries)
        self.opponent_list.set_opacity(float(self.settings.get("opacity", 0.90)))
        self.images.prefetch([e["card_id"] for e in opponent_entries], TILE)

        self._record_history(game, deck, my_class, opponent_class)

    def _record_history(self, game: Game, deck, my_class: str, opponent_class: str) -> None:
        """Sonucu belli olan maçı geçmişe yazar.

        Tracker bir maçı ancak bir sonraki maç başlayınca kapatıyor, oysa sonuç
        etiketi maçın son anında geliyor; o yüzden maç bitişini beklemeden
        sonucu görür görmez yazıyoruz. Aynı maçın ikinci kez yazılmasını hem
        buradaki anahtar hem de veritabanındaki benzersizlik engelliyor.
        """
        if not game.result:
            return
        source = self.watcher.log_dir.name if self.watcher.log_dir else ""
        key = (source, game.started_ts)
        if key == self._recorded_key:
            return
        self._recorded_key = key
        record = history.from_game(
            game,
            source,
            my_class=my_class,
            opponent_class=opponent_class,
            deck=deck.name if deck is not None else "",
        )
        if self.history.add(record) and self.history_window is not None:
            self.history_window.reload()

    @staticmethod
    def _signature(game: Game | None):
        if game is None:
            return None
        return (
            id(game),
            game.turn,
            game.result,
            len(game.my_events),
            len(game.opponent_events),
            game.my_deck_count,
            game.my_hand_count,
            game.opponent_hand_count,
            game.opponent_deck_count,
        )
