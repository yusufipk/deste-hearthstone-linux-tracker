# deste

[English](README.md) | Türkçe

Linux (KDE Wayland) için Hearthstone deck tracker.

Oyunun kendi log dosyalarını okur: ekran yakalama yok, görüntü tanıma yok,
bellek okuma yok. Yeni set çıktığında kod değil sadece kart verisi güncellenir.
Kişisel ihtiyaçtan doğdu, Arena Tracker'ın Qt5 + OpenCV mimarisi hem bakımsız
hem de her yamada kırılıyordu.

## Şu an ne yapıyor

- **Kendi destem:** kalan kartlar mana sırasına göre, adetleriyle. Çekilen kart
  listeden düşmez, solgunlaşır: "bunu oynadım" bilgisi görünür kalır.
- **Çekme yüzdesi:** her kartın bir sonraki çekişte gelme olasılığı.
- **Rakip:** oynadığı ve açığa çıkan kartlar, elindeki ve destesinde kalan kart
  sayısı.
- **Deste seçimi kendiliğinden:** deste kodu yapıştırmaya gerek yok, oyunun
  çevrimdışı önbelleğindeki desteler okunuyor ve maçtaki sınıfa göre eşleşen
  deste seçiliyor. Menüden elle de seçilebilir.
- **Kart görselleri:** satırın arka planında kartın sanatı, üzerine gelince
  kartın tam görseli (metni de görselin üstünde).
- **Ayarlanabilir saydamlık**, overlay (çerçevesiz, üstte) ve normal pencere
  modu, sistem tepsisi ikonu, masaüstü kısayolu.
- **Türkçe ve İngilizce arayüz**, menüden anında değişiyor. Varsayılan olarak
  sistemin diline bakılır.

## Nasıl çalışıyor

Oyun her oturumda `Logs/Hearthstone_YYYY_MM_DD_HH_MM_SS/` altına birkaç log
dosyası yazıyor. Bunlardan `Power.log` maçın tamamını içeriyor: varlıkların
yaratılması, bölge geçişleri (deste, el, oyun alanı, mezarlık), tag
değişimleri, tur sınırları ve maç sonucu.

Akış şöyle:

```
Power.log satırı
  -> core/parser_power.py   satırı Event'e çevirir (regex tablosu tek yerde)
  -> core/state.py          olayı oyun durumuna işler (varlık tablosu, bölgeler)
  -> data/decks.py          durumdaki sınıf ve çekilen kartlarla desteyi eşler
  -> ui/window.py           kalan liste, yüzdeler, rakip paneli
```

`core/logtail.py` dosyayı offset tutarak takip eder, oyun yeni bir oturum
dizini açtığında oraya geçer. `core/watcher.py` bunu Qt bilmeden çevirir, o
yüzden aynı motor terminalden (`tools/live.py`) veya kayıtlı loglar üstünden
(`tools/replay.py`) da çalışır.

Kart isimleri, maliyetleri ve nadirlikleri HearthstoneJSON'dan bir kere
indirilip `~/.cache/deste/` altına yazılır. Kart görselleri de aynı yere, ama
yalnızca ihtiyaç duyulduğunda ve arka planda. Ağ yoksa uygulama önbellekle
çalışmaya devam eder.

## Kurulum

Gereksinim: Python 3.11+, PyQt6. Geri kalan her şey stdlib.

```
./install.sh                # kısayol, simge, KWin kuralları
./install.sh --no-kwin      # sadece kısayol, pencere yöneticisine dokunma
./install.sh --no-hs-rule   # Hearthstone kuralı olmadan
./install.sh --uninstall    # hepsini geri al
```

`install.sh` masaüstü kısayolunu ve simgeyi kurar, `wmclass=deste` için
"her zaman üstte" KWin kuralı yazar ve KWin'e yapılandırmayı yeniden
okutur. Hepsi `--uninstall` ile geri alınır.

Tiling betiği (Krohnkite gibi) kullanıyorsan paneli o betiğin yüzen pencere
listesine eklemen gerekir, kurulum betiği başkasının ayarlarına dokunmuyor.

Oyunun logları yazması için iki dosya gerekiyor, ikisi de zaten kuruluysa
dokunulmaz:

- `<prefix>/users/<kullanıcı>/AppData/Local/Blizzard/Hearthstone/log.config`
  içinde `[Power] Verbose=1`, `[Zone]`, `[LoadingScreen]`, `[Arena]`
- `<oyun dizini>/client.config` içinde `[Log] FileSizeLimit.Int=-1`

Uygulama bunları kendi başına değiştirmez, eksikse uyarır.

## Kullanım

```
./run.sh                  # arayüz (masaüstü kısayolu da bunu çağırır)
python main.py --full     # mevcut oturum logunu baştan okuyup başlat

python -m tools.live      # terminalde canlı takip
python -m tools.replay <log_dizini> --deck   # kayıtlı oturumu baştan oynat
python -m tests.test_replay <log_dizini>     # tutarlılık testleri
```

Pencere kapatıldığında uygulama tepsiye iner, tepsi ikonuna tıklayınca geri
gelir. Saydamlık, mod değişimi, dil ve deste seçimi `⋮` menüsünde.

## Wayland notları

**Oyunun üstünde durmak.** KWin'de tam ekran pencereler "aktif katman"a çıkar
ve bu katman "her zaman üstte" katmanının da üstündedir. Yani oyun tam
ekrandayken hiçbir overlay üstünde duramaz, kural ne olursa olsun. Çözüm oyunun
tam ekrana geçmesini engellemek: `install.sh` Hearthstone için `fullscreen=false`
ve `noborder=true` kuralı yazar, oyun kenarlıksız pencere olarak ekranı
kaplamaya devam eder, görüntü aynıdır, overlay üstte kalabilir. Oyun umu/Proton
ile açıldığı için pencere sınıfı `steam_app_default`, bu sınıf başka oyunlarla
ortak olabileceğinden kural başlığa da bakar (`Hearthstone`).

**Konum.** Wayland'da uygulama kendi penceresinin ekranda nerede olduğunu
bilmez ve kendini taşıyamaz. Panel sürüklenirken `startSystemMove()` ile
taşımayı pencere yöneticisine bırakıyoruz; `move()` çağırmak pencereyi
kıpırdatmadığı gibi Qt'nin konum bilgisini de bozuyor, sonra menüler ve kart
önizlemesi ekranın dibine düşüyor. Aynı sebeple ayarlarda yalnızca boyut
saklanıyor, konum saklanmıyor. Menü ve önizleme konumları ekran kenarına göre
değil pencerenin kendi koordinatlarına göre hesaplanıyor, böylece bilinmeyen
kayma sadeleşiyor.

**Pencere boyutu.** Yerleşimin minimum boyutu pencereye dayatılmıyor
(`SetNoConstraint`), başlık metni kısaltılarak çiziliyor ve tur etiketi sabit
genişlikte. Yoksa maç sonucu yazısı geldiğinde panel kendiliğinden genişliyor,
kullanıcı her maçtan sonra boyutu düzeltmek zorunda kalıyor.

**İkon.** Tepsi ikonu bilerek `QIcon.fromTheme` ile kurulmuyor. Öyle kurulursa
Qt sisteme ikonun kendisini değil *adını* gönderiyor ve Plasma yeni kurulmuş
bir ikonu önbelleğinde bulamayınca tepside boş kare çıkıyor. `ui/icon.py` ikonu
her zaman dosyadan ve hazır PNG'lerle kuruyor.

## Mimari

```
core/     saf stdlib, UI ve ağ bilmez, headless test edilebilir
  logdir.py       kurulumu ve log dizinini bul, log.config doğrula
  logtail.py      offset tabanlı dosya takibi
  parser_power.py Power.log satırı -> olay
  state.py        olay -> oyun durumu (varlıklar, bölgeler, deste)
  watcher.py      canlı takip döngüsü (Qt'ye bağımlı değil)
  deckstring.py   deste kodu çöz/kodla
  config.py       kullanıcı ayarları
data/     ağ ve disk önbelleği
  cards.py        HearthstoneJSON kart verisi
  localdecks.py   oyunun çevrimdışı önbelleğinden desteler
  decks.py        deste kütüphanesi ve maça deste eşleştirme
  images.py       kart görselleri (tile ve tam render), arka planda indirir
ui/       PyQt6 arayüz
  window.py       panel, tepsi ikonu, saydamlık, mod yönetimi
  widgets.py      kart satırı (sanat şeridi) ve hover önizlemesi
  i18n.py         arayüz metinleri, Türkçe ve İngilizce
  theme.py        renkler ve stil
  icon.py         uygulama simgesi
tools/    replay ve terminal canlı takip
tests/    gerçek log korpusu üstünde tutarlılık testleri
```

### Tasarım kararları

**Power.log tek doğruluk kaynağı.** Zone.log daha okunaklı ama iki dosyayı
zaman damgasına göre birleştirmek gereksiz karmaşıklık. Power.log maç
sınırlarını, metadatayı ve tüm bölge geçişlerini zaten içeriyor. Zone.log
yalnızca testlerde bağımsız doğrulama kaynağı olarak kullanılıyor.

**Yalnızca `GameState.*` satırları işlenir.** `PowerTaskList.*` satırları aynı
içeriğin istemci kopyası, ikisi de işlenirse her olay iki kere sayılır.

**Olay değil durum sayılır.** Log satırları tekrar edebildiği için "her
DECK -> HAND satırında sayacı azalt" yaklaşımı yanlış sonuç verir. Her varlığın
bölgesi saklanır, sadece gerçek değişimler işlenir.

**Deste takibi deste seçiminden bağımsız.** Tracker sadece "destemden ne çıktı,
desteme ne karıştı" kaydını tutar. Kalan liste istenen an bir deste listesine
göre hesaplanır, böylece deste maç ortasında da seçilebilir.

**Üretilen kartlar destemden düşmez.** Discover, kopyalama veya rastgele
üretilen kartlar deste sayacına dokunmaz. Tersine, oyun içinde desteye
karıştırılan kartlar listeye eklenir.

**Log dosyaları asla silinmez.** Sadece okunur.

## Doğrulama

`tests/test_replay.py` uydurma veri kullanmaz, makinedeki gerçek oturum
loglarını okur. En kıymetli iki kontrol:

1. **Bağımsız kaynakla çapraz doğrulama:** Power.log'dan çıkarılan "çektiğim
   kartlar" kümesi, Zone.log'daki `FRIENDLY DECK -> FRIENDLY HAND` geçişleriyle
   varlık kimliği düzeyinde birebir eşleşmeli.
2. **Kalan liste oyunun sayacıyla tutmalı:** hesaplanan kalan deste listesinin
   boyutu, oyunun kendi DECK bölgesindeki kart sayısına eşit olmalı. Bir çekiş
   kaçarsa ya da karıştırılan kart sayılmazsa bu test anında kırılır.

6 oturum, 33 maç üstünde çalıştırıldı, hepsi geçiyor.

Pencere yönetimiyle ilgili davranışlar (menü ve önizleme konumu, tiling'e
girmemesi) sanal bir KWin oturumunda deneniyor:
`kwin_wayland --virtual --width 1800 --height 1125`. Böylece test ekranda
pencere açmıyor.

## Yol haritası

Sırada:

- **Maç geçmişi ve winrate** (sqlite, stdlib): maç başına mod, sınıflar,
  sonuç, tur sayısı; desteye ve sınıfa göre winrate ekranı.
- **Rakip arketip tahmini:** HSReplay imza kartlarıyla eşleştirip "Zee Shaman,
  4/8 imza kartı" gibi bir tahmin. Eşleşme zayıfsa panel gizlenir, tahmin
  uydurulmaz.
- **Rakip secret takibi:** oynanan secret'ın adayları oyun olaylarıyla elenir.
  Eleme kuralları `rules/secrets.json` içinde veri olarak durur, yeni set
  gelince kod değil o dosya güncellenir.

Sonraya bıraktıklarım:

- Arena draft asistanı. Ekran yakalama gerektiren tek özellik: kart sanatının
  algısal hash'i (pHash) ile tanıma, skorlar için hazır arena istatistikleri.
- Battlegrounds paneli
- Mulligan istatistikleri, deste bazlı detaylı analiz
- Tur/rope zamanlayıcısı, Twitch overlay, HSReplay yükleme

## Notlar

Kart verisi HearthstoneJSON, kart görselleri Blizzard'a ait. Bu depo Blizzard
ile ilişkili değil. Uygulama yalnızca oyunun kendi yazdığı log dosyalarını
okur, oyunun belleğine veya ağ trafiğine dokunmaz.
