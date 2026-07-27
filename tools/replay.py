"""Kayıtlı log dizinini baştan sona işleyip maç özetlerini basar.

Geliştirmenin tamamı bunun üstünde döner: oyunu açmadan, gerçek log verisiyle
parser ve durum makinesi doğrulanır.

Kullanım:
    python -m tools.replay                    # en son oturum
    python -m tools.replay <log_dizini>
    python -m tools.replay <log_dizini> --cards   # kart isimlerini de göster
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import logdir, logtail
from core.parser_power import parse_lines
from core.state import Game, Tracker

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


def summarize(game: Game, cards=None) -> str:
    mode = game.meta.get("GameType", "?").removeprefix("GT_")
    fmt = game.meta.get("FormatType", "?").removeprefix("FT_")

    def class_of(player_id):
        hero = game.hero_card_id(player_id)
        if cards is None or not hero:
            return hero or "?"
        return CLASS_SHORT.get(cards.card_class(hero), cards.card_class(hero) or "?")

    coin = "önce" if game.first_player_id == game.local_player_id else "sonra"
    result = game.result or "?"
    return (
        f"{game.started_ts[:8]}  {mode:<8} {fmt:<9} "
        f"{class_of(game.local_player_id):<8} vs {class_of(game.opponent_player_id):<8} "
        f"{result:<5} tur {game.game_turn:<3} {coin:<5} "
        f"rakip açığa çıkan {len(game.opponent_events):<3} "
        f"benim çektiğim {sum(1 for e in game.my_events if e.kind == 'drawn')}"
    )


def print_deck_detail(game: Game, library, cards) -> None:
    """Maç için seçilen desteyi ve destede kalanları yazdırır."""
    deck = library.match(game)
    if deck is None:
        print("      deste eşleşmedi")
        return
    remaining = game.remaining_deck(deck.cards)
    total_remaining = sum(remaining.values())
    mismatch = game.deck_list_mismatch(deck.cards)
    status = "" if mismatch == 0 else f", listede olmayan {mismatch} kart çıktı"
    print(
        f"      deste: {deck.name} ({deck.source}) | "
        f"kalan liste {total_remaining}, oyunun deste sayacı {game.my_deck_count}"
        f"{status}"
    )
    if cards is None:
        return
    ordered = sorted(remaining.items(), key=lambda kv: (cards.cost(kv[0]), cards.name(kv[0])))
    line = ", ".join(f"{cards.name(c)}x{n}" for c, n in ordered[:8])
    if line:
        print(f"      kalanlar: {line}{' ...' if len(ordered) > 8 else ''}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    want_cards = "--cards" in argv or "--deck" in argv
    want_deck = "--deck" in argv

    if args:
        log_dir = Path(args[0]).expanduser()
    else:
        install = logdir.detect()
        if install is None:
            print("Hearthstone kurulumu bulunamadı.", file=sys.stderr)
            return 1
        found = logdir.latest_log_dir(install.logs_dir)
        if found is None:
            print(f"Log dizini yok: {install.logs_dir}", file=sys.stderr)
            return 1
        log_dir = found

    power_log = log_dir / "Power.log"
    if not power_log.exists():
        print(f"Power.log yok: {power_log}", file=sys.stderr)
        return 1

    cards = None
    library = None
    if want_cards or want_deck:
        from data.cards import CardDB

        cards = CardDB.load()
    if want_deck:
        from data.decks import DeckLibrary

        install = logdir.detect()
        library = DeckLibrary(cards, install.game_dir if install else None).load()

    games: list[Game] = []
    tracker = Tracker(on_game_end=games.append)
    tracker.feed(parse_lines(logtail.read_file_lines(power_log)))
    tracker.close()

    print(f"Log dizini: {log_dir}")
    print(f"Power.log: {power_log.stat().st_size / 1_000_000:.1f} MB")
    print(f"Maç sayısı: {len(games)}\n")
    for index, game in enumerate(games, start=1):
        print(f"{index:>3}. {summarize(game, cards)}")
        if library is not None:
            print_deck_detail(game, library, cards)

    wins = sum(1 for g in games if g.result == "WON")
    losses = sum(1 for g in games if g.result == "LOST")
    unknown = len(games) - wins - losses
    print(f"\nGaliyet: {wins}G {losses}M" + (f" ({unknown} sonuçsuz)" if unknown else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
