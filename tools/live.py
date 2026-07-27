"""Terminalde canlı takip. Arayüzden önce boru hattını doğrulamak için.

Kullanım:
    python -m tools.live            # oyunun ortasından itibaren takip
    python -m tools.live --full     # mevcut oturum logunu baştan oku
    python -m tools.live --once     # tek seferlik anlık durum yazdır
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import logdir
from core.state import Game
from core.watcher import Watcher
from data.cards import CardDB
from data.decks import DeckLibrary

CLASS_SHORT = {
    "DEATHKNIGHT": "DK",
    "DEMONHUNTER": "DH",
    "DRUID": "Druid",
    "HUNTER": "Hunter",
    "MAGE": "Mage",
    "PALADIN": "Paladin",
    "PRIEST": "Priest",
    "ROGUE": "Rogue",
    "SHAMAN": "Shaman",
    "WARLOCK": "Warlock",
    "WARRIOR": "Warrior",
}


def render(game: Game | None, library: DeckLibrary, cards: CardDB) -> str:
    if game is None:
        return "Maç yok. Oyunda bir maça girildiğinde burası dolacak."

    def class_of(player_id):
        hero = game.hero_card_id(player_id)
        return CLASS_SHORT.get(cards.card_class(hero), cards.card_class(hero) or "?")

    lines: list[str] = []
    mode = game.meta.get("GameType", "?").removeprefix("GT_")
    lines.append(
        f"{class_of(game.local_player_id)} vs {class_of(game.opponent_player_id)} "
        f"({game.opponent_name})  {mode}  tur {game.game_turn}"
        + (f"  SONUÇ: {game.result}" if game.result else "")
    )

    deck = library.match(game)
    if deck is not None:
        remaining = game.remaining_deck(deck.cards)
        total = sum(remaining.values())
        lines.append(f"\nDestem: {deck.name}  ({total} kart kaldı, oyun sayacı {game.my_deck_count})")
        ordered = sorted(
            remaining.items(), key=lambda kv: (cards.cost(kv[0]), cards.name(kv[0]))
        )
        for card_id, count in ordered:
            chance = 100.0 * count / total if total else 0.0
            lines.append(
                f"  [{cards.cost(card_id)}] {cards.name(card_id):<28} x{count}   %{chance:.0f}"
            )
    else:
        lines.append(f"\nDestem: eşleşmedi ({game.my_deck_count} kart kaldı)")

    lines.append(
        f"\nRakip: elinde {game.opponent_hand_count}, destesinde {game.opponent_deck_count}"
    )
    seen: dict[str, int] = {}
    for event in game.opponent_events:
        if event.card_id:
            seen[event.card_id] = seen.get(event.card_id, 0) + 1
    for card_id, count in sorted(seen.items(), key=lambda kv: cards.cost(kv[0])):
        lines.append(f"  [{cards.cost(card_id)}] {cards.name(card_id)}" + (f" x{count}" if count > 1 else ""))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    install = logdir.detect()
    if install is None:
        print("Hearthstone kurulumu bulunamadı.", file=sys.stderr)
        return 1

    problems = logdir.check_log_config(install.log_config) + logdir.check_client_config(
        install.client_config
    )
    if problems:
        print("log yapılandırma uyarıları: " + ", ".join(problems), file=sys.stderr)

    cards = CardDB.load()
    library = DeckLibrary(cards, install.game_dir).load()
    print(f"{len(library.decks)} deste yüklendi: {', '.join(d.name for d in library.decks)}")

    watcher = Watcher(install, start_at_end="--full" not in argv)
    if "--full" in argv:
        # Mevcut oturumu baştan okuyup güncel duruma gel.
        for _ in range(200):
            if not watcher.poll():
                break

    if "--once" in argv:
        watcher.poll()
        print(render(watcher.game, library, cards))
        return 0

    print("Canlı takip başladı, çıkmak için Ctrl+C.\n")
    try:
        while True:
            if watcher.poll():
                print("\033[2J\033[H", end="")
                print(render(watcher.game, library, cards))
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
