# Runda 2: teleporty "przez ulicę"

Repo: /home/user/teleporty. Twoja paczka: out/weryfikacja2/paczkaNN.json (NN = twój numer).
Każdy kandydat (`kandydaci[]`) ma:
- `img` – podgląd satelity Esri z19 (~190×190 m) z narysowaną infrą z OSM, ścieżka względem out/weryfikacja2/
  Kolory: zielony = DDR/CPR, niebieski = pas rowerowy, cyjan = kontrapas, żółty = przejazd rowerowy (wg OSM!),
  biały cienki = chodnik, różowy = przejście dla pieszych bez przejazdu (wg OSM), pomarańczowy = budowa.
  Czerwone kółko = punkt do oceny, magenta linia = do czego ten koniec "powinien" się łączyć.
- `kat` i `punkty[].opis` – dlaczego to jest kandydat:
  - **K1** – infra kończy się przy jezdni, a jej kontynuacja / inna niepołączona infra jest PO DRUGIEJ STRONIE
    ulicy. Pierwsza runda uznała to automatem za OK („wjazd na jezdnię”), a to błąd.
  - **K2** – jak K1, ale pierwsza runda oceniła to ręcznie jako OK (`werdykt_rundy1`) – oceń jeszcze raz wg nowych zasad.
  - **K3** – „teoretyczne połączenie”: w OSM DDR przechodzi przez jezdnię, ale przejazd nie jest otagowany albo jest
    otagowany jako sama zebra / nieoznakowany. Sprawdź na zdjęciu, czy w terenie jest PRZEJAZD ROWEROWY
    (czerwony asfalt, kwadratowa „kostka” po boku zebry, P-11) czy tylko zebra albo nic.
  - **K4** – DDR/CPR przechodzi w chodnik z dopuszczonym ruchem rowerów.

## Zasady (od zleceniodawcy)
Teleport = infra rowerowa urywa się tak, że dalej trzeba nielegalnie / absurdalnie przejechać chodnikiem, zebrą,
trawnikiem albo **w poprzek jezdni bez przejazdu, żeby trafić na DDR po drugiej stronie**.

- **TELEPORT:** DDR kończy się przy jezdni, a dalszy ciąg (albo inna DDR, na którą „ma się” wjechać) jest po
  drugiej stronie ulicy i nie ma między nimi przejazdu rowerowego – choćby OSM rysował tam „połączenie”.
  Przykłady zleceniodawcy: Sokola (DDR po wschodniej stronie wpada na jezdnię, ciąg dalszy DDR po zachodniej,
  bez przejazdu), Al. Zieleniecka przy Targowej (CPR po jednej stronie kończy się na wjeździe na pętlę,
  CPR po drugiej stronie na chodniku – między nimi Zieleniecka i torowisko bez przejazdu),
  Rosoła/Nugat (DDR po obu stronach ulicy, tylko zebra).
- **TELEPORT (K3):** w OSM jest „połączenie” przez jezdnię, ale w terenie widać tylko zebrę albo nic.
- **TELEPORT (K4):** DDR kończy się na chodniku z dopuszczonym ruchem rowerów przy ruchliwej ulicy, bez
  dalszej infry – typ `chodnik_rower_dopuszczony` (zleceniodawca sam zdecyduje, czy to liczy).
- **OK:** jest przejazd rowerowy w terenie; DDR kończy się na jezdni i naturalna kontynuacja to jazda tą jezdnią
  (DDR „wpuszcza” na jezdnię w kierunku jazdy, nie ma po drugiej stronie DDR, na którą trzeba przejechać);
  kontraruchy; „druga strona” to inna, niezwiązana trasa (np. DDR prostopadła, do której nikt nie chciałby się dostać tędy).
- **blad_mapy:** w terenie jest przejazd / infra jest połączona, tylko OSM jest źle otagowany (np. K3, gdzie
  widać czerwony przejazd z kostką, a w OSM brak tagów) – to przydatne do poprawy OSM.
- **niepewne:** nie da się rozstrzygnąć (drzewa, budowa, rozmyte, stare zdjęcie).

## Narzędzia
- `Read` na obrazku out/weryfikacja2/img/NNNN.jpg – obowiązkowo dla każdego kandydata, po jednym na raz,
  ocena zaraz po obejrzeniu. Jeśli Read zwróci „[media removed: request limit]” albo nic – NIE zgaduj,
  spróbuj ponownie, a jak dalej nie widać: `niepewne`, komentarz „brak obrazka”.
- Tagi OSM: `python3 scripts/inspect_point.py LAT LON 40`
- Inny kadr (zapisuj do SWOJEGO katalogu tymczasowego):
  `python3 scripts/render.py data/warszawa_ways.pkl out/hotspoty.json <tmp> --at LAT,LON --zoom 20 --size 3`
  (z20 przydaje się do sprawdzenia, czy przejazd ma kostkę rowerową). Brakujący obrazek: tak samo z `--zoom 19 --size 4`.

## Wynik
out/weryfikacja2/wynikNN.json – lista JSON, jeden obiekt na KAŻDEGO kandydata z paczki:
{"id": 288, "werdykt": "teleport|ok|blad_mapy|niepewne",
 "typ": "przez_ulice|przejscie_bez_przejazdu|zebra_zamiast_przejazdu|chodnik|chodnik_rower_dopuszczony|krzaki|inne",
 "obrazek_widziany": true, "komentarz": "krótko po polsku: co tam jest i dlaczego"}
Zapisuj przyrostowo (co ~10 kandydatów nadpisz całość). Nie zmieniaj nic poza swoim wynikNN.json i katalogiem tmp. Nie commituj.
Na koniec zwróć: liczby werdyktów, ile obrazków faktycznie widziałeś, top 5 najgorszych (id + miejsce + 1 zdanie).
