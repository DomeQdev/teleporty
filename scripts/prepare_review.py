#!/usr/bin/env python3
"""Odsiewa kandydatów regułami i przygotowuje paczki do ręcznej/AI weryfikacji.

Reguły automatycznego odrzucenia (końce uznane za OK bez oglądania):
  * wpadnięcie na jezdnię – dowolnej klasy, także szybką (jezdnia_spokojna, jezdnia_ruchliwa),
  * kontraruch / kontrapas (infra = tylko 'kontraruch'),
  * pas rowerowy kończący się na węźle-przejściu na jezdni (pas i tak jest na jezdni),
  * budowa (dalej highway=construction), błąd mapy (niepołączone < 2,5 m).
Hotspot idzie do weryfikacji, jeśli ma choć jeden koniec, który nie został odrzucony.

Wynik: out/weryfikacja/czesc{1,2,3}.json + podglądy out/weryfikacja/img/NNNN.jpg

Użycie:
    python3 scripts/prepare_review.py data/warszawa_ways.pkl out/hotspoty.json out/weryfikacja [--parts 3]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from render import Renderer  # noqa: E402

AUTO_OK = {"jezdnia_spokojna", "jezdnia_ruchliwa", "budowa", "blad_mapy"}


def auto_ok(e):
    infra = set(e["infra"].split("+"))
    if infra <= {"kontraruch"}:
        return "kontraruch"
    if e["end_type"] in AUTO_OK:
        return "jezdnia" if e["end_type"].startswith("jezdnia") else e["end_type"]
    if e["end_type"].startswith("jezdnia") and infra <= {"pas", "kontraruch"}:
        return "pas na jezdni"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("hotspots")
    ap.add_argument("outdir")
    ap.add_argument("--parts", type=int, default=3)
    ap.add_argument("--no-img", action="store_true")
    a = ap.parse_args()

    H = json.load(open(a.hotspots))
    review, dropped = [], 0
    for h in H:
        keep = []
        for e in h["endpoints"]:
            r = auto_ok(e)
            e["auto_ok"] = r
            if not r:
                keep.append(e)
        if keep:
            review.append({
                "rank": h["rank"], "score": h["score"], "lat": h["lat"], "lon": h["lon"],
                "names": h["names"], "img": f"img/{h['rank']:04d}.jpg",
                "links": h["links"],
                "do_oceny": [{k: e[k] for k in ("node", "lat", "lon", "infra", "end_type", "reasons", "gap", "fwd")}
                             for e in keep],
                "odrzucone_automatem": [{"node": e["node"], "infra": e["infra"], "end_type": e["end_type"],
                                         "powod": e["auto_ok"]} for e in h["endpoints"] if e["auto_ok"]],
            })
        else:
            dropped += 1
    print(f"hotspotów: {len(H)}, odrzuconych regułami: {dropped}, do weryfikacji: {len(review)}", file=sys.stderr)

    # podział na części wg długości geograficznej (zachód -> wschód), równe liczności
    review.sort(key=lambda r: r["lon"])
    os.makedirs(os.path.join(a.outdir, "img"), exist_ok=True)
    n = len(review)
    for p in range(a.parts):
        chunk = review[p * n // a.parts:(p + 1) * n // a.parts]
        chunk.sort(key=lambda r: r["rank"])
        lo0, lo1 = min(r["lon"] for r in chunk), max(r["lon"] for r in chunk)
        path = os.path.join(a.outdir, f"czesc{p + 1}.json")
        json.dump({"czesc": p + 1, "lon_od": lo0, "lon_do": lo1, "hotspoty": chunk},
                  open(path, "w"), ensure_ascii=False, indent=1)
        print(f"  {path}: {len(chunk)} hotspotów, lon {lo0:.4f}–{lo1:.4f}", file=sys.stderr)

    if a.no_img:
        return
    R = Renderer(a.pkl)
    for i, r in enumerate(review):
        p = os.path.join(a.outdir, r["img"])
        if os.path.exists(p):
            continue
        title = f"#{r['rank']} [{r['score']}] " + " / ".join(r["names"][:3])
        R.render(r["lat"], r["lon"], p, 19, 4, title, r["do_oceny"])
        if i % 50 == 0:
            print(f"  img {i}/{len(review)}", file=sys.stderr)


if __name__ == "__main__":
    main()
