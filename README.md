# Teleporty rowerowe – Warszawa

Szukanie miejsc, w których infrastruktura rowerowa się kończy i nie ma sensownej kontynuacji:
DDR kończąca się w krzakach albo na chodniku, przejście dla pieszych bez przejazdu, urwany pas,
a przede wszystkim przypadki, w których **obok jest inna infrastruktura rowerowa, do której nie da się
po infrastrukturze dojechać**.

Dane: OSM, wycinek województwa mazowieckiego (`mazowieckie-latest.osm.pbf`), przycięty do granicy
m.st. Warszawy (relacja `admin_level=6`).

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
