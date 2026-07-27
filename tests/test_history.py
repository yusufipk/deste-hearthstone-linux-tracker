"""Maç geçmişi testleri.

İki parça var: veritabanı ve galibiyet matematiği elde kurulan kayıtlarla
sınanıyor (sonuçlar deterministik olsun diye), maçtan kayıt üretme yolu ise
makinedeki gerçek oturum loglarıyla. Log yoksa o bölüm atlanır.

Çalıştırma:
    python -m tests.test_history [log_dizini]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import history, logdir, logtail
from core.parser_power import parse_lines
from core.state import Tracker

SOURCE = "Hearthstone_2026_07_25_20_29_50"


class Failure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def sample(index: int, result: str, deck: str, opponent_class: str) -> history.MatchRecord:
    return history.MatchRecord(
        source=SOURCE,
        started_ts=f"20:{index:02d}:00.0000000",
        played_at=history.played_at(SOURCE, f"20:{index:02d}:00.0000000"),
        mode="RANKED",
        format_type="STANDARD",
        deck=deck,
        my_class="HUNTER",
        opponent_class=opponent_class,
        result=result,
        turns=8 + index,
        went_first=index % 2 == 0,
    )


# 4 maç Face Hunter (3G 1M), 2 maç Tripwire (1G 1M), biri beraberlik.
SAMPLES = [
    sample(31, "WON", "Face Hunter", "MAGE"),
    sample(32, "WON", "Face Hunter", "MAGE"),
    sample(33, "LOST", "Face Hunter", "PRIEST"),
    sample(34, "WON", "Face Hunter", "WARRIOR"),
    sample(35, "LOST", "Tripwire Hunter", "PRIEST"),
    sample(36, "WON", "Tripwire Hunter", "MAGE"),
    sample(37, "TIED", "Tripwire Hunter", "PRIEST"),
]


def load_games(log_dir: Path):
    games = []
    tracker = Tracker(on_game_end=games.append)
    tracker.feed(parse_lines(logtail.read_file_lines(log_dir / "Power.log")))
    tracker.close()
    return games


def run(log_dir: Path | None) -> int:
    failures: list[str] = []

    def record(name: str, fn) -> None:
        try:
            fn()
        except Failure as exc:
            failures.append(f"{name}: {exc}")
            print(f"  BAŞARISIZ  {name}: {exc}")
        else:
            print(f"  tamam      {name}")

    def check_played_at() -> None:
        check(
            history.played_at(SOURCE, "20:31:02.1234567") == "2026-07-25 20:31:02",
            "oturum tarihiyle saat birleşmiyor",
        )
        # Oturum gece yarısını geçtiyse saat geriye sarar, tarih bir gün ilerler.
        check(
            history.played_at(SOURCE, "00:14:00.0000000") == "2026-07-26 00:14:00",
            "gece yarısı sarması yanlış",
        )
        check(history.played_at("baska_dizin", "20:31:02.1") == "", "bozuk kaynak boş dönmeli")
        check(history.played_at(SOURCE, "") == "", "saatsiz kayıt boş dönmeli")
    record("log dizini adı ile saat doğru tarihe çevriliyor", check_played_at)

    with tempfile.TemporaryDirectory() as tmp:
        store = history.History(Path(tmp) / "history.db")
        check(store.available, "geçici veritabanı açılamadı")

        record(
            "kayıtlar yazılıyor",
            lambda: check(store.add_many(SAMPLES) == len(SAMPLES), "hepsi yazılmadı"),
        )
        record(
            "aynı maç ikinci kez yazılmıyor",
            lambda: check(
                store.add_many(SAMPLES) == 0 and store.totals().total == len(SAMPLES),
                f"tekrar yazımdan sonra {store.totals().total} kayıt var",
            ),
        )

        def check_totals() -> None:
            totals = store.totals()
            check(
                (totals.wins, totals.losses, totals.ties) == (4, 2, 1),
                f"toplam döküm yanlış: {totals}",
            )
            # Beraberlik oranın dışında: 4 galibiyet / 6 sonuçlanmış maç.
            check(
                abs(totals.winrate - 100 * 4 / 6) < 1e-9,
                f"galibiyet oranı yanlış: {totals.winrate}",
            )
        record("toplam döküm ve galibiyet oranı", check_totals)

        def check_by_deck() -> None:
            stats = {s.key: s for s in store.summary("deck")}
            check(set(stats) == {"Face Hunter", "Tripwire Hunter"}, f"desteler: {list(stats)}")
            face = stats["Face Hunter"]
            check((face.wins, face.losses, face.total) == (3, 1, 4), f"Face Hunter: {face}")
            check(abs(face.winrate - 75.0) < 1e-9, f"Face Hunter oranı: {face.winrate}")
            tripwire = stats["Tripwire Hunter"]
            check(
                (tripwire.wins, tripwire.losses, tripwire.ties) == (1, 1, 1),
                f"Tripwire Hunter: {tripwire}",
            )
            # Çok oynanan deste üstte olmalı, arayüz sıralamayı buradan alıyor.
            check(store.summary("deck")[0].key == "Face Hunter", "sıralama maç sayısına göre değil")
        record("desteye göre kırılım", check_by_deck)

        def check_by_class() -> None:
            stats = {s.key: s for s in store.summary("opponent_class")}
            check(
                (stats["MAGE"].wins, stats["MAGE"].losses) == (3, 0),
                f"Mage eşleşmesi: {stats['MAGE']}",
            )
            check(
                stats["PRIEST"].winrate == 0.0 and stats["PRIEST"].total == 3,
                f"Priest eşleşmesi: {stats['PRIEST']}",
            )
            check(
                sum(s.total for s in stats.values()) == len(SAMPLES),
                "sınıf kırılımının toplamı maç sayısını tutmuyor",
            )
        record("rakip sınıfına göre kırılım", check_by_class)

        def check_filter() -> None:
            check(store.modes() == ["RANKED"], f"modlar: {store.modes()}")
            check(store.totals("CASUAL").total == 0, "olmayan mod maç döndürdü")
            check(store.totals("RANKED").total == len(SAMPLES), "mod süzgeci maç eledi")
        record("mod süzgeci", check_filter)

        def check_order() -> None:
            listed = store.matches(3)
            check(len(listed) == 3, f"limit çalışmıyor: {len(listed)}")
            check(
                [r.started_ts for r in listed]
                == sorted((r.started_ts for r in SAMPLES), reverse=True)[:3],
                "en yeni maç üstte değil",
            )
        record("son maçlar yeniden eskiye sıralı", check_order)

        store.close()

    if log_dir is None:
        print("  atlandı    gerçek maçlardan kayıt üretme (log dizini yok)")
    else:
        def check_from_game() -> None:
            games = [g for g in load_games(log_dir) if g.result]
            check(bool(games), f"{log_dir} içinde sonucu belli maç yok")
            with tempfile.TemporaryDirectory() as tmp:
                store = history.History(Path(tmp) / "history.db")
                records = [history.from_game(g, log_dir.name) for g in games]
                check(
                    store.add_many(records) == len(records),
                    "aynı oturumdaki maçlar birbirini eziyor (başlangıç saatleri çakışıyor)",
                )
                for index, (game, item) in enumerate(zip(games, records), start=1):
                    check(item.turns == game.game_turn >= 1, f"maç {index}: tur sayısı {item.turns}")
                    check(item.result in ("WON", "LOST", "TIED"), f"maç {index}: sonuç {item.result}")
                    check(bool(item.mode), f"maç {index}: mod boş")
                    check(bool(item.played_at), f"maç {index}: tarih çözülemedi")
                check(
                    store.totals().total == len(records),
                    "veritabanındaki maç sayısı üretilen kayıt sayısını tutmuyor",
                )
                store.close()
        record("gerçek maçlardan kayıt üretiliyor", check_from_game)

    print()
    if failures:
        print(f"{len(failures)} test başarısız")
        return 1
    print("tüm testler geçti")
    return 0


def main(argv: list[str]) -> int:
    if argv:
        return run(Path(argv[0]).expanduser())
    install = logdir.detect()
    found = logdir.latest_log_dir(install.logs_dir) if install else None
    return run(found)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
