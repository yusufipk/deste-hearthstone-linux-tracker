"""Gerçek log korpusu üstünde tutarlılık testleri.

Bu testler uydurma veri kullanmaz, makinedeki gerçek Hearthstone oturum
loglarını okur. En kıymetli kontrol, Power.log'dan kurulan durumun bağımsız
bir kaynakla (Zone.log) çapraz doğrulanmasıdır.

Çalıştırma:
    python -m tests.test_replay [log_dizini]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import logdir, logtail
from core.parser_power import parse_lines
from core.state import DECK, Game, Tracker

ZONE_LINE_RE = re.compile(
    r"^\w \s*(?P<ts>\d+:\d+:\d+\.\d+) ZoneChangeList\.ProcessChanges\(\) - .*"
    r"\[entityName=(?P<name>.*?) id=(?P<id>\d+) zone=\w+ zonePos=-?\d+ "
    r"cardId=(?P<card>\w*) player=\d+\] zone from (?P<src>[A-Z ]+) -> (?P<dst>[A-Z ]+)$"
)


class Failure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def load_games(log_dir: Path) -> list[Game]:
    games: list[Game] = []
    tracker = Tracker(on_game_end=games.append)
    tracker.feed(parse_lines(logtail.read_file_lines(log_dir / "Power.log")))
    tracker.close()
    return games


def zone_draws_by_window(log_dir: Path, windows: list[tuple[str, str]]) -> list[set[int]]:
    """Zone.log'dan her maç penceresi için FRIENDLY DECK -> FRIENDLY HAND
    geçişi yapan varlık kimliklerini toplar."""
    results: list[set[int]] = [set() for _ in windows]
    zone_log = log_dir / "Zone.log"
    if not zone_log.exists():
        return results
    for line in logtail.read_file_lines(zone_log):
        match = ZONE_LINE_RE.match(line)
        if not match:
            continue
        if match.group("src") != "FRIENDLY DECK" or match.group("dst") != "FRIENDLY HAND":
            continue
        ts = match.group("ts")
        for index, (start, end) in enumerate(windows):
            if start <= ts and (not end or ts <= end):
                results[index].add(int(match.group("id")))
                break
    return results


def initial_deck_sizes(game: Game) -> dict[int, int]:
    sizes: dict[int, int] = {}
    for entity in game.entities.values():
        if entity.from_opening and entity.initial_zone == DECK and entity.controller is not None:
            sizes[entity.controller] = sizes.get(entity.controller, 0) + 1
    return sizes


def run(log_dir: Path) -> int:
    games = load_games(log_dir)
    failures: list[str] = []

    def record(name: str, fn) -> None:
        try:
            fn()
        except Failure as exc:
            failures.append(f"{name}: {exc}")
            print(f"  BAŞARISIZ  {name}: {exc}")
        else:
            print(f"  tamam      {name}")

    power_log = log_dir / "Power.log"
    expected_games = sum(
        1
        for line in logtail.read_file_lines(power_log)
        if line.endswith("GameState.DebugPrintPower() - CREATE_GAME")
    )

    print(f"Log dizini: {log_dir}")
    print(f"Beklenen maç sayısı (CREATE_GAME): {expected_games}")
    print(f"Ayrıştırılan maç sayısı: {len(games)}\n")

    record(
        "maç sayısı CREATE_GAME ile eşleşiyor",
        lambda: check(len(games) == expected_games, f"{len(games)} != {expected_games}"),
    )

    record(
        "her maçın yerel oyuncusu belirlendi",
        lambda: check(
            all(g.local_player_id is not None for g in games),
            f"{sum(1 for g in games if g.local_player_id is None)} maçta belirlenemedi",
        ),
    )

    # Oturumun son maçı log yazılırken hâlâ devam ediyor olabilir, onu muaf
    # tutuyoruz. Öncekilerin hepsinin sonucu bilinmek zorunda.
    finished_games = games[:-1] if games else []
    record(
        "biten maçların sonucu var",
        lambda: check(
            all(g.result in ("WON", "LOST", "TIED") for g in finished_games),
            f"{[i for i, g in enumerate(finished_games, 1) if not g.result]} numaralı maçlarda sonuç yok",
        ),
    )

    record(
        "her maçta iki kahraman da tespit edildi",
        lambda: check(
            all(
                g.hero_card_id(g.local_player_id) and g.hero_card_id(g.opponent_player_id)
                for g in games
            ),
            "bazı maçlarda kahraman kartı boş",
        ),
    )

    def check_initial_decks() -> None:
        # Hearthstone'da geçerli deste boyutu 30, Renathal benzeri etkilerle 40.
        for index, game in enumerate(games, start=1):
            sizes = initial_deck_sizes(game)
            for player_id, size in sizes.items():
                check(
                    size in (30, 40),
                    f"maç {index}, oyuncu {player_id} başlangıç destesi {size} kart",
                )
    record("başlangıç desteleri 30 ya da 40 kart", check_initial_decks)

    # Bağımsız kaynakla çapraz doğrulama.
    windows = [(g.started_ts, g.ended_ts) for g in games]
    zone_draws = zone_draws_by_window(log_dir, windows)

    def check_draws() -> None:
        # Kimlik kümesi karşılaştırılıyor, sayı değil: Zone.log aynı geçişi
        # birden fazla satırda yazabiliyor, ayrıca mulligan sonrası aynı kart
        # tekrar çekilebiliyor.
        for index, (game, drawn_ids) in enumerate(zip(games, zone_draws), start=1):
            tracked = {e.entity_id for e in game.my_events if e.kind == "drawn"}
            missing = drawn_ids - tracked
            extra = tracked - drawn_ids
            check(
                not missing and not extra,
                f"maç {index}: Zone.log'da olup bizde olmayan {sorted(missing)}, "
                f"bizde olup Zone.log'da olmayan {sorted(extra)}",
            )
    record("çekilen kartlar Zone.log ile birebir eşleşiyor", check_draws)

    def check_deck_counts() -> None:
        for index, game in enumerate(games, start=1):
            check(
                0 <= game.my_deck_count <= 60,
                f"maç {index}: deste sayacı mantıksız ({game.my_deck_count})",
            )
            check(
                0 <= game.opponent_deck_count <= 60,
                f"maç {index}: rakip deste sayacı mantıksız ({game.opponent_deck_count})",
            )
    record("deste sayaçları mantıklı aralıkta", check_deck_counts)

    # Deste takibi: kart verisi ve deste kütüphanesi varsa en kıymetli
    # tutarlılık kontrolü. Kalan liste, oyunun kendi deste sayacıyla birebir
    # tutmalı. Tutmuyorsa ya çekiş kaçırılmış ya da desteye karışan kart
    # sayılmamıştır.
    library = None
    try:
        from data.cards import CardDB
        from data.decks import DeckLibrary

        install = logdir.detect()
        cards_db = CardDB.load(auto_update=False)
        library = DeckLibrary(cards_db, install.game_dir if install else None).load()
    except Exception as exc:  # kart verisi yoksa bu bölümü atla
        print(f"  atlandı    deste takibi kontrolleri ({exc})")

    if library is not None and library.decks:
        def check_deck_tracking() -> None:
            checked = 0
            for index, game in enumerate(games, start=1):
                deck = library.match(game)
                if deck is None:
                    continue
                checked += 1
                remaining = sum(game.remaining_deck(deck.cards).values())
                check(
                    remaining == game.my_deck_count,
                    f"maç {index} ({deck.name}): kalan liste {remaining}, "
                    f"oyunun deste sayacı {game.my_deck_count}",
                )
                check(
                    game.deck_list_mismatch(deck.cards) == 0,
                    f"maç {index} ({deck.name}): listede olmayan "
                    f"{game.deck_list_mismatch(deck.cards)} kart destemden çıktı",
                )
            check(checked > 0, "hiçbir maça deste eşleşmedi")

        record("kalan deste listesi oyunun sayacıyla tutuyor", check_deck_tracking)

    print()
    if failures:
        print(f"{len(failures)} test başarısız")
        return 1
    print("tüm testler geçti")
    return 0


def main(argv: list[str]) -> int:
    if argv:
        log_dir = Path(argv[0]).expanduser()
    else:
        install = logdir.detect()
        if install is None:
            print("Hearthstone kurulumu bulunamadı.", file=sys.stderr)
            return 1
        found = logdir.latest_log_dir(install.logs_dir)
        if found is None:
            print("Log dizini yok.", file=sys.stderr)
            return 1
        log_dir = found
    return run(log_dir)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
