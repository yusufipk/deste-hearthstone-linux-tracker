"""Log dosyalarını offset tabanlı takip eder.

Oyun her açılışta yeni bir oturum dizini yaratıp dosyaları sıfırdan yazar.
Dosya küçüldüyse ya da inode değiştiyse baştan okunur. Yarım kalan son satır
tamamlanana kadar tamponda bekletilir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TailedFile:
    path: Path
    offset: int = 0
    inode: int | None = None
    buffer: str = ""
    # Uygulama oyun açıkken başlatıldıysa geçmiş satırları tekrar işlememek için
    # dosyanın sonuna atlayabiliyoruz.
    start_at_end: bool = False
    _started: bool = field(default=False, repr=False)

    def read_new_lines(self) -> list[str]:
        try:
            stat = self.path.stat()
        except OSError:
            return []

        if self.inode is None:
            self.inode = stat.st_ino
            if self.start_at_end and not self._started:
                self.offset = stat.st_size
        elif stat.st_ino != self.inode or stat.st_size < self.offset:
            # Yeni oturum ya da dosya kırpıldı.
            self.inode = stat.st_ino
            self.offset = 0
            self.buffer = ""
        self._started = True

        if stat.st_size == self.offset:
            return []

        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
                self.offset = handle.tell()
        except OSError:
            return []

        if not chunk:
            return []

        data = self.buffer + chunk
        lines = data.split("\n")
        self.buffer = lines.pop()
        return lines


class LogSet:
    """Bir oturum dizinindeki ilgili log dosyalarını birlikte takip eder."""

    def __init__(self, log_dir: Path, components=("Power",), start_at_end: bool = False):
        self.log_dir = log_dir
        self.files = {
            name: TailedFile(log_dir / f"{name}.log", start_at_end=start_at_end)
            for name in components
        }

    def read_new_lines(self, component: str = "Power") -> list[str]:
        tailed = self.files.get(component)
        return tailed.read_new_lines() if tailed else []

    def read_all_components(self) -> dict[str, list[str]]:
        return {name: tailed.read_new_lines() for name, tailed in self.files.items()}


def read_file_lines(path: Path):
    """Tam dosyayı satır satır okur. Replay ve testler için."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            yield line.rstrip("\n")


def file_size(path: Path) -> int:
    try:
        return os.stat(path).st_size
    except OSError:
        return 0
