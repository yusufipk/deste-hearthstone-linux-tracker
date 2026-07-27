"""Diskteki oturum loglarını maç geçmişine aktarır.

Uygulama yalnızca kendisi açıkken oynanan maçları kaydeder. Bu araç bütün
oturum dizinlerini baştan okuyup aynı veritabanına yazar. Daha önce yazılmış
maçlar atlanır, istendiği kadar tekrar çalıştırılabilir.

Kullanım:
    python -m tools.import_history                 # bütün oturumlar
    python -m tools.import_history <log_dizini>    # tek oturum
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import history, logdir, logtail
from core.parser_power import parse_lines
from core.state import Game, Tracker


def games_in(log_dir: Path) -> list[Game]:
    games: list[Game] = []
    tracker = Tracker(on_game_end=games.append)
    tracker.feed(parse_lines(logtail.read_file_lines(log_dir / "Power.log")))
    tracker.close()
    return games


def import_dir(log_dir: Path, store: history.History, cards, library) -> tuple[int, int]:
    """(yazılan, aday) maç sayısı. Sonucu bilinmeyen maçlar sayılmaz."""
    if not (log_dir / "Power.log").exists():
        return (0, 0)
    added = candidates = 0
    for game in games_in(log_dir):
        # Yarım kalmış maçlar (bağlantı koptu, oyun kapandı) geçmişi kirletir.
        if not game.result or game.local_player_id is None:
            continue
        candidates += 1
        deck = library.match(game) if library is not None else None
        record = history.from_game(
            game,
            log_dir.name,
            my_class=cards.card_class(game.hero_card_id(game.local_player_id)),
            opponent_class=cards.card_class(game.hero_card_id(game.opponent_player_id)),
            deck=deck.name if deck is not None else "",
        )
        added += int(store.add(record))
    return (added, candidates)


def main(argv: list[str]) -> int:
    install = logdir.detect()
    if argv:
        log_dirs = [Path(argv[0]).expanduser()]
    else:
        if install is None:
            print("Hearthstone kurulumu bulunamadı.", file=sys.stderr)
            return 1
        log_dirs = sorted(
            d
            for d in install.logs_dir.iterdir()
            if d.is_dir() and logdir.LOG_DIR_RE.match(d.name)
        )
        if not log_dirs:
            print(f"Oturum dizini yok: {install.logs_dir}", file=sys.stderr)
            return 1

    from data.cards import CardDB
    from data.decks import DeckLibrary

    cards = CardDB.load()
    library = DeckLibrary(cards, install.game_dir if install else None).load()

    store = history.History()
    if not store.available:
        print(f"Geçmiş veritabanı açılamadı: {store.path}", file=sys.stderr)
        return 1

    total_added = total_candidates = 0
    for log_dir in log_dirs:
        added, candidates = import_dir(log_dir, store, cards, library)
        total_added += added
        total_candidates += candidates
        print(f"{log_dir.name}  {added} yeni / {candidates} maç")

    totals = store.totals()
    rate = f"%{totals.winrate:.0f}" if totals.winrate is not None else "-"
    print(
        f"\n{total_added} maç eklendi ({total_candidates - total_added} zaten kayıtlıydı)."
        f"\nVeritabanı: {store.path}"
        f"\nToplam {totals.total} maç, {totals.wins}G {totals.losses}M, {rate}"
    )
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
