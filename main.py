"""deste: Hearthstone deck tracker (Linux / Wayland).

Kullanım:
    python main.py            # arayüzü başlat
    python main.py --full     # mevcut oturum logunu baştan okuyup başlat
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config, logdir
from core.watcher import Watcher
from ui import i18n


def main(argv: list[str]) -> int:
    settings = config.load()
    i18n.set_language(settings.get("language", "auto"))

    install = logdir.detect(settings.get("game_dir") or None)
    if install is None:
        print(
            i18n.t("error_no_install") + "\n" + i18n.t("error_no_install_hint"),
            file=sys.stderr,
        )
        return 1

    problems = logdir.check_log_config(install.log_config)
    problems += logdir.check_client_config(install.client_config)
    if problems:
        print(i18n.t("error_log_config") + ", ".join(problems), file=sys.stderr)
        print(i18n.t("error_log_config_hint"), file=sys.stderr)

    from PyQt6.QtWidgets import QApplication

    from data.cards import CardDB
    from data.decks import DeckLibrary
    from ui.window import TrackerWindow

    app = QApplication(sys.argv)
    app.setApplicationName("deste")
    app.setDesktopFileName("deste")

    cards = CardDB.load()
    library = DeckLibrary(cards, install.game_dir).load()

    watcher = Watcher(install, start_at_end="--full" not in argv)
    if "--full" in argv:
        for _ in range(500):
            if not watcher.poll():
                break

    window = TrackerWindow(watcher, library, cards, settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
