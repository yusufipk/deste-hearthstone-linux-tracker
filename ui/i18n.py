"""Arayüz metinleri: Türkçe ve İngilizce.

Qt Linguist yerine düz bir sözlük: metin sayısı az, derleme adımı istemiyoruz
ve dil menüden anında değişebiliyor. Anahtar bulunamazsa anahtarın kendisi
dönüyor, uygulama metin yüzünden çökmesin.
"""

from __future__ import annotations

import os

LANGUAGES = ("tr", "en")
LANGUAGE_NAMES = {"tr": "Türkçe", "en": "English"}

STRINGS: dict[str, dict[str, str]] = {
    "waiting_match": {"tr": "Maç bekleniyor", "en": "Waiting for a match"},
    "deck_empty": {
        "tr": "Maça girdiğinde destendeki kartlar burada görünecek.",
        "en": "Your deck will show up here once a match starts.",
    },
    "opponent_empty": {
        "tr": "Rakip henüz kart göstermedi.",
        "en": "The opponent has not revealed a card yet.",
    },
    "opponent_title": {"tr": "RAKİP", "en": "OPPONENT"},
    "opponent_counts": {
        "tr": "el {hand}   deste {deck}",
        "en": "hand {hand}   deck {deck}",
    },
    "deck_auto": {"tr": "Otomatik", "en": "Automatic"},
    "deck_tooltip": {"tr": "Takip edilen deste", "en": "Tracked deck"},
    "menu_to_window": {"tr": "Pencere moduna geç", "en": "Switch to window mode"},
    "menu_to_overlay": {"tr": "Overlay moduna geç", "en": "Switch to overlay mode"},
    "menu_opacity": {"tr": "Saydamlık", "en": "Opacity"},
    "opacity_full": {"tr": "Tam", "en": "Full"},
    "opacity_step": {"tr": "%{value}", "en": "{value}%"},
    "menu_draw_chance": {"tr": "Çekme yüzdesi", "en": "Draw chance"},
    "menu_language": {"tr": "Dil", "en": "Language"},
    "menu_reload_decks": {"tr": "Desteleri yeniden yükle", "en": "Reload decks"},
    "menu_hide": {"tr": "Gizle (tepsiye)", "en": "Hide to tray"},
    "menu_quit": {"tr": "Çıkış", "en": "Quit"},
    "tray_toggle": {"tr": "Göster / Gizle", "en": "Show / Hide"},
    "tray_mode": {"tr": "Overlay / Pencere", "en": "Overlay / Window"},
    "result_won": {"tr": "Kazandın", "en": "You won"},
    "result_lost": {"tr": "Kaybettin", "en": "You lost"},
    "result_tied": {"tr": "Berabere", "en": "Tie"},
    "error_no_install": {
        "tr": "Hearthstone kurulumu bulunamadı.",
        "en": "Hearthstone installation not found.",
    },
    "error_no_install_hint": {
        "tr": "Yolu ~/.config/deste/config.json içinde game_dir olarak belirtin.",
        "en": "Set the path as game_dir in ~/.config/deste/config.json.",
    },
    "error_log_config": {
        "tr": "Log yapılandırması eksik: ",
        "en": "Log configuration is incomplete: ",
    },
    "error_log_config_hint": {
        "tr": "Oyunun logları eksik yazılıyor olabilir.",
        "en": "The game may not be writing complete logs.",
    },
}

_current = "en"


def detect(preference: str = "auto") -> str:
    """Ayardaki dili çözer. "auto" ise ortamın diline bakar."""
    if preference in LANGUAGES:
        return preference
    locale = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
    return "tr" if locale.lower().startswith("tr") else "en"


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else detect(code)


def current() -> str:
    return _current


def t(key: str, **kwargs) -> str:
    text = STRINGS.get(key, {}).get(_current, key)
    return text.format(**kwargs) if kwargs else text
