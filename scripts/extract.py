#!/usr/bin/env python3
"""Wyciąga z PBF województwa sieć dróg/ścieżek w okolicy Warszawy + granicę miasta.

Wynik: data/warszawa_ways.pkl  (lista dróg z tagami i geometrią, granica miasta)

Użycie:
    python3 scripts/extract.py data/mazowieckie-latest.osm.pbf data/warszawa_ways.pkl
"""
import pickle
import sys

import osmium
from shapely import wkb
from shapely.ops import unary_union

# bbox Warszawy z zapasem (lon_min, lat_min, lon_max, lat_max)
BBOX = (20.83, 52.08, 21.29, 52.38)

# tagi, które nas interesują przy klasyfikacji
KEEP_PREFIXES = (
    "highway", "bicycle", "foot", "cycleway", "footway", "sidewalk", "segregated",
    "oneway", "access", "crossing", "name", "bicycle_road", "cyclestreet", "area",
    "junction", "motor_vehicle", "vehicle", "service", "path", "surface", "layer",
    "bridge", "tunnel", "construction", "proposed", "ref", "lanes", "busway",
)

NODE_KEYS = ("highway", "crossing", "barrier", "bicycle", "crossing_ref",
             "crossing:markings", "railway", "noexit", "foot")


def in_bbox(lon, lat):
    return BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]


def main(pbf, out):
    ways = []
    node_tags = {}
    wkbf = osmium.geom.WKBFactory()
    boundary_parts = []

    fp = (osmium.FileProcessor(pbf)
          .with_locations()
          .with_areas(osmium.filter.TagFilter(("boundary", "administrative"))))

    n = 0
    for obj in fp:
        n += 1
        if n % 5_000_000 == 0:
            print(f"  ... {n:,} obiektów", file=sys.stderr)
        if obj.is_node():
            if len(obj.tags) and obj.location.valid() and in_bbox(obj.location.lon, obj.location.lat):
                t = {k: v for k, v in obj.tags if k in NODE_KEYS}
                if t:
                    node_tags[obj.id] = t
        elif obj.is_way():
            tags = obj.tags
            if "highway" not in tags:
                continue
            hw = tags["highway"]
            if hw in ("proposed", "abandoned", "razed", "platform", "bus_stop", "elevator", "corridor"):
                continue
            try:
                coords = [(nd.lon, nd.lat) for nd in obj.nodes]
            except osmium.InvalidLocationError:
                continue
            if not any(in_bbox(lon, lat) for lon, lat in coords):
                continue
            t = {k: v for k, v in tags if k.startswith(KEEP_PREFIXES)}
            ways.append({
                "id": obj.id,
                "tags": t,
                "nodes": [nd.ref for nd in obj.nodes],
                "coords": coords,
            })
        elif obj.is_area():
            t = obj.tags
            if t.get("admin_level") == "6" and t.get("name") in ("Warszawa", "m.st. Warszawa"):
                try:
                    boundary_parts.append(wkb.loads(wkbf.create_multipolygon(obj), hex=True))
                    print(f"  granica: {t.get('name')} (area {obj.id})", file=sys.stderr)
                except Exception as e:  # noqa
                    print("  nie udało się zbudować granicy:", e, file=sys.stderr)

    if not boundary_parts:
        sys.exit("Nie znaleziono granicy Warszawy (admin_level=6)")
    boundary = unary_union(boundary_parts)
    print(f"dróg: {len(ways):,}, otagowanych węzłów: {len(node_tags):,}", file=sys.stderr)
    with open(out, "wb") as f:
        pickle.dump({"ways": ways, "node_tags": node_tags, "boundary": boundary.wkb}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
