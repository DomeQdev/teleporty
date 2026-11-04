# Instrukcja weryfikacji kandydatów na teleporty rowerowe (Warszawa)

Repo: /home/user/teleporty. Twoja paczka: out/weryfikacja/czescN.json (N = twój numer).
Każdy hotspot ma:
- `img` – podgląd satelity Esri z19 (ok. 300×300 m) z narysowaną infrą z OSM, ścieżka względem out/weryfikacja/
  Kolory: zielony = DDR/CPR, niebieski = pas rowerowy, cyjan = kontrapas, żółty = przejazd rowerowy,
  biały cienki = chodnik/ścieżka piesza, różowy = przejście dla pieszych bez przejazdu, pomarańczowy = budowa.
  Czerwone kółko = koniec infry do oceny, magenta linia = luka do pobliskiej niepołączonej infry,
  pomarańczowa linia = niepołączony dalszy ciąg infry na wprost.
- `do_oceny` – końce infry do oceny, z automatycznymi powodami (`reasons`).
- `odrzucone_automatem` – końce już uznane za OK (nie oceniaj ich).

## Definicja (od zleceniodawcy – rowerzysty z Warszawy)
TELEPORT = infrastruktura rowerowa (DDR, CPR, pas, przejazd) kończy się tak, że żeby jechać dalej
trzeba nielegalnie/absurdalnie: wjechać na chodnik, na przejście dla pieszych bez przejazdu, w trawnik/krzaki,
albo infra się urywa, a obok jest INNA infra rowerowa, do której nie da się dojechać infrastrukturą.

To NIE są teleporty (werdykt `ok`):
- kontraruch / kontrapas na jednokierunkowej – zawsze OK,
- DDR/pas wpadający na jezdnię (nawet szybką), jeśli jest fizyczny zjazd na jezdnię (obniżony krawężnik,
  łagodne włączenie) – OK. W OSM taki zjazd bywa narysowany jako kilkumetrowy kawałek chodnika/przejścia do
  jezdni – patrz na zdjęcie, liczy się rzeczywistość,
- infra kończy się na drodze wewnętrznej / osiedlowej / parkingu, gdzie dalej jedzie się jezdnią,
- strefa zamieszkania / deptak z dopuszczonym ruchem rowerów.

Zleceniodawca uznał za teleporty m.in. (kalibracja):
- Świętojerska DDR / Bonifraterska pasy (52.2503, 21.0038) – DDR kończy się na chodniku, pas Bonifraterskiej
  zaczyna się 20 m dalej i nie da się do niego dojechać → „KURWA!!! Co tam się dzieje!!!”
- Rosoła / Nugat (52.1553, 21.0504) – DDR-y po obu stronach Nugat, między nimi tylko przejście dla pieszych
  bez przejazdu → „Czemu nie zrobili przejazdu rowerowego”
- Andersa / Plac Bankowy (52.2441, 21.0009) – DDR umiera na chodniku przy wielkim skrzyżowaniu → „Dramat.”
- Targowa / Kijowska / Zamoyskiego (52.2498, 21.0425) – DDR Targowej kończy się na chodniku przed
  ogromnym skrzyżowaniem, dalszy ciąg 150 m dalej, bez połączenia → „Japierdole.”

## Werdykty
- `teleport` – faktyczny teleport,
- `ok` – nie jest teleportem (wjazd na jezdnię, kontraruch, sensowne zakończenie),
- `blad_mapy` – na zdjęciu widać, że infra w rzeczywistości jest połączona/ciągnie się dalej, a tylko OSM jest
  niekompletny (np. czerwony asfalt idzie dalej, przejazd jest namalowany, a w OSM go nie ma),
- `niepewne` – nie da się rozstrzygnąć ze zdjęcia (zasłonięte drzewami, budowa, stare zdjęcie).

## Narzędzia
- `Read` na obrazku: out/weryfikacja/img/NNNN.jpg (obowiązkowo dla każdego hotspotu).
- Tagi OSM wokół punktu: `python3 scripts/inspect_point.py LAT LON 40`
- Szerszy kontekst / inne powiększenie (zapisuj do SWOJEGO katalogu tymczasowego, nie do out/):
  `python3 scripts/render.py data/warszawa_ways.pkl out/hotspoty.json <twoj_tmp> --at LAT,LON --zoom 18 --size 4`
  Jeśli obrazka w img/ jeszcze nie ma – wygeneruj go tak samo z `--zoom 19 --size 4`.
- Street View tylko w ostateczności (Playwright + chromium są zainstalowane, ale Google bywa niedostępny –
  nie trać na to dużo czasu).

## Wynik
Plik out/weryfikacja/wynikN.json – lista JSON, po jednym obiekcie na KAŻDY hotspot z paczki:
{"rank": 17, "werdykt": "teleport", "typ": "chodnik|przejscie_bez_przejazdu|krzaki|luka_do_innej_infry|urwany_pas|skrzyzowanie|inne",
 "nodes": [3380566688], "komentarz": "krótko po polsku: co tam jest i dlaczego"}
`typ` i `nodes` (węzły-końce które są teleportem) wypełniaj dla `teleport` i `niepewne`.
Zapisuj plik przyrostowo (co ok. 20 hotspotów nadpisuj całość), żeby nic nie przepadło.
Nie modyfikuj nic poza swoim wynikN.json i swoim katalogiem tymczasowym. Nie commituj.

## WAŻNE: obrazki muszą być faktycznie obejrzane
Jeśli Read na obrazku zwróci "[media removed: request limit]" albo pusty wynik – NIE zgaduj werdyktu z `reasons`.
Spróbuj ponownie (pojedynczo, po jednym obrazku na wywołanie). Jeśli dalej nie widać – werdykt `niepewne`,
komentarz "brak obrazka". Każdy wpis w wyniku ma pole "obrazek_widziany": true/false.
Oceniaj hotspot od razu po obejrzeniu jego obrazka (nie czytaj kilku obrazków naraz na zapas).
