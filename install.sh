#!/usr/bin/env bash
#
# deste kurulum betiği.
#
# Yaptıkları:
#   1. Masaüstü kısayolu (uygulama menüsü + masaüstü)
#   2. Simgeyi hicolor temasına kopyalar
#   3. KWin kuralları: deste her zaman üstte, Hearthstone tam ekrana geçmesin
#   4. KWin'e yapılandırmayı yeniden okutur
#
# Hepsi geri alınabilir:  ./install.sh --uninstall
# Sadece kısayol, KWin'e dokunma:  ./install.sh --no-kwin
# Hearthstone kuralı olmadan:      ./install.sh --no-hs-rule

set -euo pipefail

APP_ID="deste"
REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"
USER_DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
KWIN_RULES="${XDG_CONFIG_HOME:-$HOME/.config}/kwinrulesrc"
RULE_ID="deste-overlay"
HS_RULE_ID="deste-hearthstone"

DO_KWIN=1
DO_HS_RULE=1
DO_UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --no-kwin) DO_KWIN=0 ;;
        --no-hs-rule) DO_HS_RULE=0 ;;
        --uninstall) DO_UNINSTALL=1 ;;
        *) echo "bilinmeyen seçenek: $arg" >&2; exit 1 ;;
    esac
done

info() { printf '  %s\n' "$1"; }

reconfigure_kwin() {
    if command -v qdbus6 >/dev/null 2>&1; then
        qdbus6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    elif command -v qdbus >/dev/null 2>&1; then
        qdbus org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
    fi
}

# --- kaldırma -------------------------------------------------------------

if [ "$DO_UNINSTALL" = 1 ]; then
    echo "deste kaldırılıyor"
    rm -f "$DESKTOP_FILE" "$USER_DESKTOP/$APP_ID.desktop" "$ICON_DIR/$APP_ID.svg"
    info "kısayol ve simge silindi"

    if [ -f "$KWIN_RULES" ]; then
        current="$(kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null || echo "")"
        if [ -n "$current" ]; then
            new="$(printf '%s' "$current" | tr ',' '\n' | grep -vx "$RULE_ID" | grep -vx "$HS_RULE_ID" | paste -sd, -)"
            kwriteconfig6 --file kwinrulesrc --group General --key rules "$new"
            kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key Description --delete 2>/dev/null || true
            # Grubu tamamen sil
            python3 - "$KWIN_RULES" "$RULE_ID" "$HS_RULE_ID" <<'PY'
import sys, re
path, groups = sys.argv[1], sys.argv[2:]
try:
    text = open(path, encoding="utf-8").read()
except OSError:
    sys.exit(0)
for group in groups:
    pattern = re.compile(r"\n?\[" + re.escape(group) + r"\][^\[]*", re.S)
    text = pattern.sub("\n", text)
open(path, "w", encoding="utf-8").write(text)
PY
            info "KWin kuralı silindi"
        fi
    fi

    reconfigure_kwin
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo "tamam"
    exit 0
fi

# --- kurulum --------------------------------------------------------------

echo "deste kuruluyor: $REPO_DIR"

if ! python3 -c "import PyQt6" 2>/dev/null; then
    echo "UYARI: PyQt6 bulunamadı. Kurulum: sudo pacman -S python-pyqt6" >&2
fi

chmod +x "$REPO_DIR/run.sh"

mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
install -m644 "$REPO_DIR/assets/deste.svg" "$ICON_DIR/$APP_ID.svg"

# PNG boyutları: Plasma'nın tepsisi ve menüsü ikonu isimle çözerken hazır
# rasterları tercih ediyor, sadece SVG bırakınca boş kare çıkabiliyor.
if [ ! -f "$REPO_DIR/assets/icons/deste-48.png" ]; then
    (cd "$REPO_DIR" && python3 tools/make_icons.py >/dev/null 2>&1) || true
fi
for size in 16 22 24 32 48 64 96 128 256; do
    src="$REPO_DIR/assets/icons/deste-$size.png"
    [ -f "$src" ] || continue
    dest_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$dest_dir"
    install -m644 "$src" "$dest_dir/$APP_ID.png"
done
info "simge: SVG + PNG boyutları hicolor temasına kuruldu"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=deste
GenericName=Hearthstone deck tracker
Comment=Hearthstone destesini ve rakibin kartlarını takip eder
Exec=$REPO_DIR/run.sh
Icon=$APP_ID
Terminal=false
Categories=Game;Utility;
Keywords=hearthstone;deck;tracker;deste;
StartupNotify=false
StartupWMClass=$APP_ID
EOF
chmod +x "$DESKTOP_FILE"
info "kısayol: $DESKTOP_FILE"

if [ -d "$USER_DESKTOP" ]; then
    install -m755 "$DESKTOP_FILE" "$USER_DESKTOP/$APP_ID.desktop"
    # Plasma masaüstündeki kısayolun çalışması için güvenilir işaretlenmeli
    if command -v gio >/dev/null 2>&1; then
        gio set "$USER_DESKTOP/$APP_ID.desktop" metadata::trusted true 2>/dev/null || true
    fi
    info "masaüstü: $USER_DESKTOP/$APP_ID.desktop"
fi

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

# gtk-update-icon-cache burada bilerek çağrılmıyor: kullanıcı dizinindeki
# hicolor'da index.theme olmadığı için ürettiği önbellek Qt'nin ikonu
# yükleyememesine yol açıyor. Plasma'nın uygulama veritabanını tazelemek yeterli.
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
    info "Plasma uygulama veritabanı tazelendi"
fi

if [ "$DO_KWIN" = 1 ]; then
    # KWin kuralı: pencere her zaman üstte kalsın.
    # aboverule=2 -> Force (KWin rules.h: Unused=0, DontAffect=1, Force=2, ...)
    # wmclassmatch=1 -> tam eşleşme
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key Description "deste overlay"
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key wmclass "$APP_ID"
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key wmclassmatch 1
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key wmclasscomplete false
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key above true
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key aboverule 2

    # Not: boyut/konum bilerek zorlanmıyor. Force kuralı pencereyi sabitliyor
    # ama sürüklemeyi de kilitliyor. Konum ve boyut kullanıcıya bırakıldı.

    current="$(kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null || echo "")"
    if ! printf '%s' "$current" | tr ',' '\n' | grep -qx "$RULE_ID"; then
        if [ -z "$current" ]; then
            kwriteconfig6 --file kwinrulesrc --group General --key rules "$RULE_ID"
        else
            kwriteconfig6 --file kwinrulesrc --group General --key rules "$current,$RULE_ID"
        fi
    fi
    kwriteconfig6 --file kwinrulesrc --group General --key count \
        "$(kreadconfig6 --file kwinrulesrc --group General --key rules | tr ',' '\n' | grep -c . || echo 1)"
    info "KWin kuralı: her zaman üstte"

    # Hearthstone kuralı: tam ekrana geçmesin ve çerçevesiz olsun.
    #
    # Sebebi: KWin'de tam ekran pencereler "her zaman üstte" katmanının da
    # üstündeki aktif katmana çıkıyor, o yüzden overlay oyunun altında kalıyor.
    # Tam ekranı zorla kapatınca oyun kenarlıksız pencere olarak ekranı
    # kaplamaya devam ediyor ama overlay üstte kalabiliyor.
    #
    # umu/Proton ile açılan oyunların sınıfı steam_app_default olduğu için
    # başlığa da bakıyoruz, başka oyunlar etkilenmesin.
    if [ "$DO_HS_RULE" = 1 ]; then
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key Description "Hearthstone (deste)"
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key wmclass "steam_app_default"
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key wmclassmatch 1
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key wmclasscomplete false
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key title "Hearthstone"
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key titlematch 1
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key fullscreen false
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key fullscreenrule 2
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key noborder true
        kwriteconfig6 --file kwinrulesrc --group "$HS_RULE_ID" --key noborderrule 2

        current="$(kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null || echo "")"
        if ! printf '%s' "$current" | tr ',' '\n' | grep -qx "$HS_RULE_ID"; then
            kwriteconfig6 --file kwinrulesrc --group General --key rules "$current,$HS_RULE_ID"
        fi
        kwriteconfig6 --file kwinrulesrc --group General --key count \
            "$(kreadconfig6 --file kwinrulesrc --group General --key rules | tr ',' '\n' | grep -c . || echo 1)"
        info "KWin kuralı: Hearthstone tam ekrana geçmesin, çerçevesiz olsun"
    fi

    reconfigure_kwin
fi

echo
echo "tamam. Uygulama menüsünde ve masaüstünde 'deste' olarak görünüyor."
echo "Doğrudan çalıştırmak için: $REPO_DIR/run.sh"
