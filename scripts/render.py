#!/usr/bin/env python3
"""Renderuje podgląd satelitarny (Esri World Imagery) z narysowaną infrastrukturą z OSM.

Kolory:  zielony = DDR/CPR, niebieski = pas rowerowy, żółty = przejazd rowerowy,
         biały cienki = chodnik/ścieżka piesza, różowy = przejście bez przejazdu,
         czerwone kółko = koniec infry (kandydat), magenta linia = "teleport" (luka do innej infry),
         pomarańczowa linia = niepołączony dalszy ciąg na wprost.

Użycie:
    python3 scripts/render.py data/warszawa_ways.pkl out/hotspoty.json out/podglady --top 100
    python3 scripts/render.py data/warszawa_ways.pkl out/hotspoty.json out/podglady --at 52.2497,21.0005
"""
import argparse
import io
import json
import math
import os
import pickle
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from find_candidates import classify  # noqa: E402

TILE_URL = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?blankTile=false"
UA = {"User-Agent": "teleporty-rowerowe/0.1 (analiza infrastruktury rowerowej)"}
CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "tiles")


def ll2px(lon, lat, z):
    n = 256 * 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile(z, x, y, sess):
    p = os.path.join(CACHE, str(z), str(x), f"{y}.jpg")
    if os.path.exists(p):
        return Image.open(p).convert("RGB")
    for attempt in range(4):
        try:
            r = sess.get(TILE_URL.format(z=z, x=x, y=y), headers=UA, timeout=30)
            if r.status_code == 200 and r.content:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(r.content)
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except requests.RequestException:
            pass
        time.sleep(2 ** attempt)
    return Image.new("RGB", (256, 256), (40, 40, 40))


STYLE = {
    ("infra", "DDR"): ((0, 230, 0), 4),
    ("infra", "DDR/CPR"): ((0, 230, 0), 4),
    ("infra", "CPR"): ((140, 255, 80), 4),
    ("infra", "pas"): ((30, 140, 255), 5),
    ("infra", "przejazd"): ((255, 230, 0), 4),
    ("crossing_ped", None): ((255, 80, 200), 2),
    ("ped", None): ((235, 235, 235), 1),
    ("ped_bike", None): ((200, 200, 120), 2),
    ("construction", None): ((255, 140, 0), 2),
}


class Renderer:
    def __init__(self, pkl):
        d = pickle.load(open(pkl, "rb"))
        self.ways = d["ways"]
        self.cls = [classify(w["tags"]) for w in self.ways]
        # prosta siatka do szybkiego wyboru dróg w kadrze
        self.grid = {}
        for i, w in enumerate(self.ways):
            if self.cls[i][0] in ("ignore",):
                continue
            keys = {(int(lon * 200), int(lat * 300)) for lon, lat in w["coords"]}
            for k in keys:
                self.grid.setdefault(k, []).append(i)
        self.sess = requests.Session()

    def render(self, lat, lon, path, z=19, size=3, title="", endpoints=()):
        cx, cy = ll2px(lon, lat, z)
        tx0 = int(cx // 256) - size // 2
        ty0 = int(cy // 256) - size // 2
        img = Image.new("RGB", (256 * size, 256 * size))
        for dx in range(size):
            for dy in range(size):
                img.paste(tile(z, tx0 + dx, ty0 + dy, self.sess), (dx * 256, dy * 256))
        ox, oy = tx0 * 256, ty0 * 256
        dr = ImageDraw.Draw(img, "RGBA")

        def P(lo, la):
            x, y = ll2px(lo, la, z)
            return (x - ox, y - oy)

        sel = set()
        for gx in range(int(lon * 200) - 2, int(lon * 200) + 3):
            for gy in range(int(lat * 300) - 2, int(lat * 300) + 3):
                sel.update(self.grid.get((gx, gy), []))
        order = sorted(sel, key=lambda i: {"ped": 0, "ped_bike": 1, "crossing_ped": 2, "construction": 2}.get(self.cls[i][0], 5))
        for i in order:
            c = self.cls[i]
            st = STYLE.get(c) or STYLE.get((c[0], None))
            if not st:
                continue
            pts = [P(lo, la) for lo, la in self.ways[i]["coords"]]
            if len(pts) > 1:
                dr.line(pts, fill=st[0] + (230,), width=st[1])

        for e in endpoints:
            x, y = P(e["lon"], e["lat"])
            if e.get("gap") and e["gap"]["gap_m"] >= 2.5:
                gx, gy = P(e["gap"]["gap_lon"], e["gap"]["gap_lat"])
                dr.line([(x, y), (gx, gy)], fill=(255, 0, 255, 255), width=3)
            if e.get("fwd"):
                fx, fy = P(e["fwd"]["fwd_lon"], e["fwd"]["fwd_lat"])
                dr.line([(x, y), (fx, fy)], fill=(255, 150, 0, 220), width=2)
            r = 9
            dr.ellipse([x - r, y - r, x + r, y + r], outline=(255, 0, 0, 255), width=3)
        if title:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 15)
            except OSError:
                font = ImageFont.load_default()
            dr.rectangle([0, 0, img.width, 22], fill=(0, 0, 0, 170))
            dr.text((5, 3), title, fill=(255, 255, 255), font=font)
        img.save(path, quality=88)
        return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("hotspots")
    ap.add_argument("outdir")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--at", help="lat,lon – pojedynczy podgląd")
    ap.add_argument("--zoom", type=int, default=19)
    ap.add_argument("--size", type=int, default=3, help="kafelków na bok")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    R = Renderer(a.pkl)
    H = json.load(open(a.hotspots))
    if a.at:
        lat, lon = map(float, a.at.split(","))
        eps = [e for h in H for e in h["endpoints"]
               if abs(e["lat"] - lat) < 0.003 and abs(e["lon"] - lon) < 0.005]
        p = R.render(lat, lon, os.path.join(a.outdir, f"at_{lat:.5f}_{lon:.5f}.jpg"), a.zoom, a.size,
                     f"{lat:.5f},{lon:.5f}", eps)
        print(p)
        return
    for h in H[: a.top]:
        eps = [e for h2 in H for e in h2["endpoints"]
               if abs(e["lat"] - h["lat"]) < 0.002 and abs(e["lon"] - h["lon"]) < 0.003]
        title = f"#{h['rank']} [{h['score']}] " + " / ".join(h["names"][:3])
        p = R.render(h["lat"], h["lon"], os.path.join(a.outdir, f"{h['rank']:04d}.jpg"), a.zoom, a.size, title, eps)
        print(p, file=sys.stderr)


if __name__ == "__main__":
    main()
