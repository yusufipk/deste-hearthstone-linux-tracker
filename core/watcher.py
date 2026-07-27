"""Canlı log takibi.

Oyun açıkken en yeni oturum dizinini bulur, Power.log'a eklenen satırları
okuyup durum makinesini besler. Kendi zamanlayıcısı yoktur: poll() çağrısını
arayüz (QTimer) ya da terminal döngüsü yapar. Böylece Qt'ye bağımlı değil.
"""

from __future__ import annotations

from pathlib import Path

from . import logdir, logtail
from .parser_power import parse_lines
from .state import Game, Tracker

# Yeni oturum dizini kontrolü her poll'da yapılmasın, dosya sistemi taraması.
LOG_DIR_CHECK_INTERVAL = 20


class Watcher:
    def __init__(
        self,
        install: logdir.Installation,
        on_game_end=None,
        on_update=None,
        start_at_end: bool = True,
    ):
        self.install = install
        self.on_update = on_update
        self.tracker = Tracker(on_game_end=on_game_end)
        self.log_dir: Path | None = None
        self.log_set: logtail.LogSet | None = None
        # Uygulama oyunun ortasında açılırsa geçmiş maçları tekrar işlememek
        # için dosyanın sonundan başlıyoruz. Devam eden maçın başı kaçar, bu
        # yüzden bir sonraki maçtan itibaren takip tam olur.
        self.start_at_end = start_at_end
        self._checks = 0

    @property
    def game(self) -> Game | None:
        return self.tracker.game

    def poll(self) -> bool:
        """Yeni satır varsa işler. Durum değiştiyse True döner."""
        if self._checks % LOG_DIR_CHECK_INTERVAL == 0:
            self._refresh_log_dir()
        self._checks += 1

        if self.log_set is None:
            return False
        lines = self.log_set.read_new_lines("Power")
        if not lines:
            return False
        self.tracker.feed(parse_lines(lines))
        if self.on_update is not None:
            self.on_update(self.tracker.game)
        return True

    def _refresh_log_dir(self) -> None:
        latest = logdir.latest_log_dir(self.install.logs_dir)
        if latest is None or latest == self.log_dir:
            return
        # Yeni oturum: oyun yeniden açılmış.
        self.log_dir = latest
        self.log_set = logtail.LogSet(
            latest, components=("Power",), start_at_end=self.start_at_end
        )
        # İlk dizinden sonrakiler baştan okunmalı, oyun yeni açıldığı için
        # dosya zaten boştur ve maçın başını kaçırmak istemeyiz.
        self.start_at_end = False
