"""Görsel tema. Koyu, yarı saydam, oyunun üstünde okunaklı."""

from __future__ import annotations

BACKGROUND = "#0d0f16"
SURFACE = "#171a25"
SURFACE_ALT = "#222738"
ROW_BASE = "#12151f"
TEXT = "#eceef5"
TEXT_DIM = "#8b90a3"
ACCENT = "#e0a63c"
BORDER = "#2b3145"
MANA_BLUE = "#1f4e8c"
WIN = "#5fbf6a"
LOSS = "#d0605a"

# Maç sonucu: yazı yerine işaret. Hem panelde hem maç geçmişinde aynı dil.
RESULT_MARKS = {"WON": ("✓", WIN), "LOST": ("✗", LOSS), "TIED": ("=", TEXT_DIM)}

RARITY_COLORS = {
    "COMMON": "#c9cedb",
    "FREE": "#c9cedb",
    "RARE": "#3f7fd8",
    "EPIC": "#a951d8",
    "LEGENDARY": "#e0a63c",
}

CLASS_COLORS = {
    "DEATHKNIGHT": "#4a6fa5",
    "DEMONHUNTER": "#5c9c48",
    "DRUID": "#8b5a2b",
    "HUNTER": "#3f8f4f",
    "MAGE": "#4aa3c7",
    "PALADIN": "#d4b84a",
    "PRIEST": "#c9cedb",
    "ROGUE": "#7d8494",
    "SHAMAN": "#3355aa",
    "WARLOCK": "#8a5fbf",
    "WARRIOR": "#a5453c",
    "NEUTRAL": "#8b90a3",
}

CLASS_NAMES = {
    "DEATHKNIGHT": "Death Knight",
    "DEMONHUNTER": "Demon Hunter",
    "DRUID": "Druid",
    "HUNTER": "Hunter",
    "MAGE": "Mage",
    "PALADIN": "Paladin",
    "PRIEST": "Priest",
    "ROGUE": "Rogue",
    "SHAMAN": "Shaman",
    "WARLOCK": "Warlock",
    "WARRIOR": "Warrior",
    "NEUTRAL": "Neutral",
}


def rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-size: 12px;
}}
QWidget#topbar {{
    background: rgba(28, 33, 49, 170);
    border-bottom: 1px solid {BORDER};
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
}}
QLabel#header {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#subheader {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
QLabel#section {{
    color: {TEXT_DIM};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QLabel#dim {{
    color: {TEXT_DIM};
}}
QLabel#count {{
    color: {ACCENT};
    font-weight: 600;
}}
QLabel#empty {{
    color: {TEXT_DIM};
    padding: 10px 4px;
}}
QComboBox, QPushButton, QToolButton {{
    background: rgba(35, 40, 58, 200);
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 8px;
}}
QComboBox:hover, QPushButton:hover, QToolButton:hover {{
    background: {SURFACE_ALT};
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 16px; }}
QToolButton#menu {{ padding: 2px 6px; font-size: 15px; }}
QToolButton#menu::menu-indicator {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE_ALT};
    outline: none;
}}
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 3px; }}
QMenu::item:selected {{ background: {SURFACE_ALT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}
QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{ background: transparent; width: 5px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; min-height: 20px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""

# Maç geçmişi penceresi. Panelin aksine saydam değil: oyunun üstünde değil,
# yanında okunan bir pencere.
TABLE_STYLESHEET = f"""
QWidget#history {{ background: {BACKGROUND}; }}
QLabel#title {{ font-size: 15px; font-weight: 600; }}
QLabel#total {{ color: {TEXT_DIM}; font-size: 12px; }}
QTableWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QTableWidget::item {{ padding: 2px 6px; border: none; }}
QTableWidget::item:selected {{ background: {SURFACE_ALT}; color: {TEXT}; }}
QHeaderView::section {{
    background: transparent;
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px 6px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}}
/* Başlıklar tıklanınca sıralıyor, imleç üstüne gelince belli olsun. */
QHeaderView::section:hover {{ color: {TEXT}; }}
QHeaderView::down-arrow, QHeaderView::up-arrow {{ width: 9px; height: 9px; }}
"""
