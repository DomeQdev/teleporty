#!/usr/bin/env bash
# Pełny pipeline: pobranie PBF -> ekstrakcja -> kandydaci -> mapa -> podglądy top 50
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data out
PBF=data/mazowieckie-latest.osm.pbf
if [ ! -f "$PBF" ]; then
  # geofabrik bywa niedostępny zza proxy – mirror openstreetmap.fr ma ten sam wycinek
  curl -fSL -o "$PBF" https://download.geofabrik.de/europe/poland/mazowieckie-latest.osm.pbf \
    || curl -fSL -o "$PBF" https://download.openstreetmap.fr/extracts/europe/poland/mazowieckie-latest.osm.pbf
fi
python3 scripts/extract.py "$PBF" data/warszawa_ways.pkl
python3 scripts/find_candidates.py data/warszawa_ways.pkl out
python3 scripts/build_map.py data/warszawa_ways.pkl out/hotspoty.json out/mapa.html
python3 scripts/render.py data/warszawa_ways.pkl out/hotspoty.json out/podglady --top "${TOP:-50}"
