#!/usr/bin/env python3
"""Scala werdykty weryfikacji (out/weryfikacja/wynik*.json) z hotspotami.

Wynik:
  out/teleporty.json     – hotspoty z werdyktem teleport / niepewne / blad_mapy (struktura jak hotspoty.json)
  out/teleporty.csv      – faktyczne teleporty (+ niepewne na końcu)
  out/bledy_mapy.csv     – miejsca, gdzie infra istnieje w terenie, a w OSM nie (do poprawy w OSM)
  out/teleporty.geojson  – punkty z werdyktem

Użycie:
    python3 scripts/merge_review.py out/hotspoty.json out/weryfikacja out
"""
import csv
import glob
import json
import os
import sys
from collections import Counter


def main(hot_path, rdir, outdir):
    H = {h["rank"]: h for h in json.load(open(hot_path))}
    expected = set()
    for p in glob.glob(os.path.join(rdir, "czesc*.json")):
        expected |= {h["rank"] for h in json.load(open(p))["hotspoty"]}
    verdicts = {}
    for p in sorted(glob.glob(os.path.join(rdir, "wynik*.json"))):
        for v in json.load(open(p)):
            verdicts[int(v["rank"])] = v
    missing = sorted(expected - set(verdicts))
    print(f"do weryfikacji: {len(expected)}, ocenionych: {len(verdicts)}, brak oceny: {len(missing)} {missing[:20]}",
          file=sys.stderr)
    print("werdykty:", dict(Counter(v["werdykt"] for v in verdicts.values())), file=sys.stderr)

    order = {"teleport": 0, "niepewne": 1, "blad_mapy": 2}
    keep = []
    for r, v in verdicts.items():
        if v["werdykt"] not in order or r not in H:
            continue
        h = dict(H[r])
        h.update({"werdykt": v["werdykt"], "typ": v.get("typ", ""), "komentarz": v.get("komentarz", ""),
                  "teleport_nodes": v.get("nodes", [])})
        keep.append(h)
    keep.sort(key=lambda h: (order[h["werdykt"]], -h["score"]))
    json.dump(keep, open(os.path.join(outdir, "teleporty.json"), "w"), ensure_ascii=False, indent=1)

    def write_csv(path, rows):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["werdykt", "typ", "miejsce", "komentarz", "score", "rank", "lat", "lon",
                        "osm", "streetview", "nodes"])
            for h in rows:
                L = h["links"]
                w.writerow([h["werdykt"], h["typ"], " / ".join(h["names"]), h["komentarz"], h["score"], h["rank"],
                            h["lat"], h["lon"], L["osm_map"], L["streetview"],
                            " ".join(map(str, h["teleport_nodes"]))])

    write_csv(os.path.join(outdir, "teleporty.csv"), [h for h in keep if h["werdykt"] in ("teleport", "niepewne")])
    write_csv(os.path.join(outdir, "bledy_mapy.csv"), [h for h in keep if h["werdykt"] == "blad_mapy"])
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [h["lon"], h["lat"]]},
              "properties": {k: h[k] for k in ("rank", "score", "werdykt", "typ", "komentarz", "names",
                                               "teleport_nodes")}} for h in keep]
    json.dump({"type": "FeatureCollection", "features": feats},
              open(os.path.join(outdir, "teleporty.geojson"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main(*sys.argv[1:4])
