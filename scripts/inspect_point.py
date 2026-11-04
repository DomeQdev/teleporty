#!/usr/bin/env python3
"""Wypisuje drogi z OSM w promieniu R metrów od punktu: klasa wg find_candidates + tagi.

Użycie:
    python3 scripts/inspect_point.py 52.1553 21.0504 [40]
"""
import math
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(__file__))
from find_candidates import classify  # noqa: E402

lat, lon = float(sys.argv[1]), float(sys.argv[2])
R = float(sys.argv[3]) if len(sys.argv) > 3 else 40.0
pkl = os.path.join(os.path.dirname(__file__), "..", "data", "warszawa_ways.pkl")
d = pickle.load(open(pkl, "rb"))
kx = 111320 * math.cos(math.radians(lat))
ky = 110540
rows = []
for w in d["ways"]:
    best = min(math.hypot((lo - lon) * kx, (la - lat) * ky) for lo, la in w["coords"])
    if best <= R:
        c = classify(w["tags"])
        if c[0] == "ignore":
            continue
        rows.append((best, w["id"], c, {k: v for k, v in w["tags"].items() if k not in ("surface",)}))
for best, wid, c, t in sorted(rows):
    print(f"{best:5.1f} m  way {wid}  [{c[0]}/{c[1]}]  {t}")
