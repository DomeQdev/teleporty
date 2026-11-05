# Teleporty rowerowe – Warszawa

Szukanie miejsc, w których infrastruktura rowerowa się kończy i nie ma sensownej kontynuacji:
DDR kończąca się w krzakach albo na chodniku, przejście dla pieszych bez przejazdu, urwany pas,
a przede wszystkim przypadki, w których **obok jest inna infrastruktura rowerowa, do której nie da się
po infrastrukturze dojechać**.

Dane: OSM, wycinek województwa mazowieckiego (`mazowieckie-latest.osm.pbf`), przycięty do granicy
m.st. Warszawy (relacja `admin_level=6`).

## Wynik: zweryfikowane teleporty (stan OSM 2026-11-03)

**335 faktycznych teleportów** (+132 niepewne, +87 błędów mapy) z dwóch rund weryfikacji.

| runda | co | teleport | niepewne | błąd mapy |
|---|---|---|---|---|
| 1 | końce infry (chodnik, krzaki, przejście bez przejazdu, luka) | 191 | 72 | 20 |
| 2 | teleporty przez ulicę (K1–K4, `scripts/find_cross_road.py`) | 144 | 60 | 67 |

Runda 2 – typy: zebra zamiast przejazdu 48, przez ulicę 41, chodnik 38, przejście bez przejazdu 10,
chodnik z dopuszczonym ruchem rowerów 6, krzaki 1.

* `out/teleporty_mapa.html` – mapa z teleportami / niepewnymi / błędami mapy z obu rund, komentarz do każdego
* `out/teleporty.csv` – teleporty i niepewne (kolumna `runda`), linki do OSM i Street View
* `out/bledy_mapy.csv` – w terenie jest przejazd/połączenie, w OSM brak albo złe tagi (do poprawy w OSM)
* `out/teleporty.geojson`, `out/teleporty.json`

### Jak weryfikowano
1. Reguły (`scripts/prepare_review.py`) – za OK uznane bez oglądania: wpadnięcie na jezdnię (dowolną,
   także szybką), kontraruchy/kontrapasy, pas kończący się na przejściu na jezdni, budowa, niepołączenie < 2,5 m.
   Z 1521 hotspotów zostało 492.
2. Każde z 492 miejsc obejrzane na podglądzie Esri z19 z narysowaną infrą (`out/weryfikacja/img/`,
   niecommitowane) przez agentów AI wg `out/weryfikacja/INSTRUKCJA.md`; Warszawa podzielona na 3 pasy
   zachód→wschód (`czesc1..3.json`), części 1 i 2 przeliczone w mniejszych paczkach (`redo/`), bo
   pierwszy przebieg nie widział obrazków. Werdykty: `out/weryfikacja/wynik*.json`.
3. Runda 2 (`scripts/find_cross_road.py`, instrukcja `out/weryfikacja2/INSTRUKCJA.md`) – to, czego pierwsza
   runda nie łapała:
   * **K1** koniec infry przy jezdni (pierwsza runda uznawała to automatem za OK), a kontynuacja / inna
     niepołączona infra / drugi koniec infry (do 90 m) leży po drugiej stronie jezdni (np. Sokola),
   * **K2** to samo, ale oceniane w 1. rundzie jako OK (np. Al. Zieleniecka przy Targowej),
   * **K3** „teoretyczne połączenie” – DDR przechodzi w OSM przez jezdnię, ale przejazd nie jest otagowany
     albo jest otagowany jako sama zebra / nieoznakowany (w terenie często tylko zebra),
   * **K4** DDR przechodzi w chodnik z dopuszczonym ruchem rowerów.
   688 grup, każda obejrzana na z19 (przejazdy dodatkowo na z20) – 18 paczek po ≤40.
4. `scripts/merge_review.py` scala werdykty, `scripts/build_map.py out/teleporty.json` buduje mapę.

Werdykty `niepewne` to głównie budowy i miejsca zasłonięte drzewami – warto je obejrzeć w Street View.

### Ręczna weryfikacja w przeglądarce

```bash
python scripts/serve_review.py     # http://127.0.0.1:8765, bez instalowania zależności
```

Przeglądanie wszystkich 554 miejsc z `out/teleporty.json`: lista z filtrami, mapa z infrą, link do Street View
przy każdym miejscu i każdym punkcie (nowa karta). Oceny zapisują się od razu do `out/oceny.json`,
w CSV można je pobrać przyciskiem na stronie.

Klawisze: `t` teleport, `n` nie, `m` nie wiem, `s` Street View, `j`/`k` następny/poprzedni, `u` cofnij, `c` komentarz.

`--host 0.0.0.0` udostępnia serwer w sieci lokalnej (np. na telefon), ale każdy w tej sieci może wtedy zmieniać oceny.

## Uruchomienie

```bash
pip install -r requirements.txt
./run.sh            # pobiera PBF, liczy wszystko, renderuje podglądy top 50 (TOP=200 ./run.sh)
```

Wyniki w `out/`:

| plik | co |
|---|---|
| `mapa.html` | **mapa do przeglądania kandydatów**: podkład Esri satelita / OSM / CyclOSM, infrastruktura z OSM, lista z filtrem, ocena każdego miejsca (TELEPORT / ? / nie, zapis w przeglądarce, eksport do CSV), linki do Street View |
| `hotspoty.csv` | hotspoty (skupiska końców infry w promieniu 40 m) posortowane wg punktacji, z linkami do OSM / Street View / kafla Esri |
| `hotspoty.json` | to samo, plus szczegóły każdego końca infry |
| `kandydaci.geojson` | wszystkie końce infry jako punkty (np. do QGIS-a / uMap) |
| `podglady/NNNN.jpg` | satelita Esri z19 z narysowaną infrastrukturą dla top N (niecommitowane, `render.py`) |

Klawisze w `mapa.html`: `j`/`k` następny/poprzedni, `t` TELEPORT, `n` nie, `m` ?, `s` Street View.

## Jak to działa (`scripts/find_candidates.py`)

1. **Klasyfikacja dróg**:
   infra = `highway=cycleway` (DDR, przejazdy `cycleway=crossing`), `footway/path + bicycle=designated` (CPR),
   jezdnie z `cycleway*=lane/track/…` lub `bicycle:lanes=…designated` (pas);
   chodnik = `footway/path/pedestrian/steps` bez dopuszczenia rowerów;
   przejście bez przejazdu = `footway=crossing` bez `bicycle=designated/yes`;
   jezdnie: spokojne (residential/service/…), ruchliwe (tertiary+), z zakazem (`bicycle=no`, autostrady).
2. **Graf infry** → węzły o stopniu 1 to końce infrastruktury (w Warszawie ~1 900).
3. Dla każdego końca:
   * **co jest dalej** – nic (ślepy koniec / krzaki), chodnik, schody, przejście bez przejazdu,
     jezdnia ruchliwa / spokojna / z zakazem, budowa; niepołączenie < 2,5 m od innej drogi = prawdopodobny błąd mapy;
   * **luka („TELEPORT”)** – inna infra w promieniu 50 m, do której po grafie infry jest > 4× dalej
     niż w linii prostej albo w ogóle się nie da (Dijkstra do 900 m); pas przerwany tylko na skrzyżowaniu
     tej samej jezdni nie jest liczony;
   * **dalszy ciąg na wprost** – niepołączona infra w stożku ±50° do 200 m w kierunku jazdy;
   * **wielkość skrzyżowania** – liczba ruchliwych ulic i przejść bez przejazdu w promieniu 45 m
     (DDR umierająca na wielkim skrzyżowaniu, typ „Dramat.”);
   * wysepki infry krótsze niż 60 m.
4. Punktacja sumuje powyższe, końce w promieniu 40 m są łączone w hotspot.

Punktacja to tylko kolejność przeglądania – każdy przypadek trzeba obejrzeć (satelita, w razie
wątpliwości Street View). Spokojne zjazdy na osiedlówki (`jezdnia_spokojna`) są na liście,
ale z niską punktacją.

## Kalibracja na znanych teleportach (stan danych 2026-11-03)

| miejsce | ocena eksperta | ranking |
|---|---|---|
| Świętojerska DDR / Bonifraterska pasy | „KURWA !!!!!!!!!!!!! Kurwaaaaaa !!!!!!!!!!!!!! Co tam się dzieje !!!!!!!!!!!!!!!” | #17 |
| Rosoła / Nugat | „Czemu ci pierdoleni debile nie zrobiły przejazdu rowerowego” | #18 |
| DDR na Andersa / Plac Bankowy | „Dramat.” | #129 |
| Targowa / Kijowska / Zamoyskiego / Zieleniecka | „Japierdole.” | #136 |

Typy z luką do innej infry lądują wysoko; DDR kończąca się na dużym skrzyżowaniu bez infry w
zasięgu 50 m (Andersa, Targowa) jest wyżej niż zwykłe końce, ale niżej niż ewidentne luki – warto
przejrzeć co najmniej top ~250.

## Skrypty

* `scripts/extract.py` – PBF → `data/warszawa_ways.pkl` (drogi w bbox Warszawy + granica miasta)
* `scripts/find_candidates.py` – analiza, eksport do `out/`
* `scripts/build_map.py` – `out/mapa.html`
* `scripts/render.py` – podglądy satelitarne (`--top N` albo `--at lat,lon`), kafle Esri cache'owane w `data/tiles/`
