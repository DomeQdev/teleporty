#!/usr/bin/env python3
"""Szuka kandydatów na teleporty rowerowe w Warszawie.

Teleport = miejsce, gdzie infrastruktura rowerowa (DDR, CPR, pas, przejazd) się kończy
i nie ma legalnej/sensownej kontynuacji: ślepy koniec "w krzakach", wjazd na chodnik,
przejście dla pieszych bez przejazdu, urwany pas, albo – najgorsze – obok jest inna
infrastruktura rowerowa, do której nie da się dojechać infrastrukturą rowerową.

Algorytm:
  1. klasyfikacja każdej drogi z OSM (infra / chodnik / przejście / jezdnia cicha / ruchliwa / zakaz),
  2. graf infrastruktury rowerowej -> węzły o stopniu 1 = końce infrastruktury,
  3. dla każdego końca: co go dotyka (nic? chodnik? przejście bez przejazdu? jezdnia jakiej klasy?)
     + czy w promieniu GAP_R metrów jest INNA infra rowerowa, do której po infrastrukturze
     jest daleko albo w ogóle się nie da (Dijkstra po grafie infry),
  4. punktacja, grupowanie końców w "hotspoty" (skrzyżowania), eksport.

Użycie:
    python3 scripts/find_candidates.py data/warszawa_ways.pkl out/
"""
import csv
import heapq
import json
import math
import os
import pickle
import sys
from collections import defaultdict

from shapely import STRtree, wkb
from shapely.geometry import LineString, Point
from shapely.prepared import prep

LAT0 = 52.23
KX = 111320 * math.cos(math.radians(LAT0))
KY = 110540

GAP_R = 50.0          # promień szukania "innej, niepołączonej" infry [m]
DIJKSTRA_CUTOFF = 900  # [m]
CLUSTER_R = 40.0      # grupowanie końców w hotspoty [m]
MAP_ERROR_GAP = 2.5   # odstęp poniżej którego to raczej błąd mapy (niepołączone węzły) [m]
FORWARD_R = 200.0     # jak daleko "na wprost" szukamy dalszego ciągu infry [m]
FORWARD_HALF_ANGLE = 50  # stożek na wprost, +/- stopni
JUNCTION_R = 45.0     # promień liczenia "wielkości skrzyżowania" [m]


def xy(lon, lat):
    return ((lon - 21.0) * KX, (lat - LAT0) * KY)


# ---------------------------------------------------------------- klasyfikacja

LANE_VALUES = {"lane", "opposite_lane", "track", "opposite_track", "shared_busway",
               "share_busway", "opposite_share_busway"}
BIKE_OK = {"yes", "designated", "permissive"}
PED_HW = {"footway", "pedestrian", "path", "steps", "bridleway", "corridor", "track_ped"}
QUIET_ROADS = {"residential", "living_street", "service", "unclassified", "road", "track",
               "busway", "bus_guideway"}
BUSY_ROADS = {"tertiary", "tertiary_link", "secondary", "secondary_link",
              "primary", "primary_link"}
FAST_ROADS = {"trunk", "trunk_link", "motorway", "motorway_link"}

ROAD_RANK = {"motorway": 7, "motorway_link": 6, "trunk": 6, "trunk_link": 5, "primary": 5,
             "primary_link": 4, "secondary": 4, "secondary_link": 3, "tertiary": 3,
             "tertiary_link": 2, "unclassified": 1, "residential": 1, "living_street": 0,
             "service": 0}


def has_lane(t):
    for k in ("cycleway", "cycleway:both", "cycleway:left", "cycleway:right"):
        if t.get(k) in LANE_VALUES:
            return True
    for k in ("bicycle:lanes", "bicycle:lanes:forward", "bicycle:lanes:backward"):
        if "designated" in t.get(k, ""):
            return True
    if t.get("bicycle_road") == "yes" or t.get("cyclestreet") == "yes":
        return True
    return False


def classify(t):
    """Zwraca (klasa, podtyp). Klasy: infra, ped, ped_bike, crossing_ped, road_quiet,
    road_busy, road_forbidden, construction, ignore."""
    hw = t.get("highway", "")
    bic = t.get("bicycle", "")
    if hw == "construction":
        c = t.get("construction", "")
        return ("construction", c)
    if hw == "cycleway":
        if t.get("cycleway") == "crossing":
            return ("infra", "przejazd")
        return ("infra", "DDR")
    if hw in PED_HW or hw in ("footway",):
        if bic == "designated":
            if t.get("footway") == "crossing" or t.get("path") == "crossing":
                return ("infra", "przejazd")
            return ("infra", "CPR" if t.get("segregated") == "no" else "DDR/CPR")
        is_crossing = t.get("footway") == "crossing" or t.get("path") == "crossing"
        if is_crossing:
            if bic in BIKE_OK:
                return ("ped_bike", "przejscie_rower_dopuszczony")
            return ("crossing_ped", "przejscie")
        if hw == "steps":
            return ("ped", "schody")
        if bic in BIKE_OK:
            return ("ped_bike", hw)
        if bic in ("no", "dismount"):
            return ("ped", hw + "_zakaz")
        return ("ped", t.get("footway") or hw)
    if hw in QUIET_ROADS or hw in BUSY_ROADS or hw in FAST_ROADS:
        if has_lane(t):
            return ("infra", "pas")
        if hw == "track" and bic not in BIKE_OK:
            return ("road_quiet", hw)
        if bic in ("no",) or hw in ("motorway", "motorway_link"):
            return ("road_forbidden", hw)
        if t.get("access") in ("no", "private") and bic not in BIKE_OK:
            return ("road_forbidden" if hw not in QUIET_ROADS else "road_quiet", hw)
        if hw in FAST_ROADS:
            return ("road_busy", hw)
        if hw in BUSY_ROADS:
            return ("road_busy", hw)
        return ("road_quiet", hw)
    return ("ignore", hw)


def layer_of(t):
    try:
        return int(t.get("layer", "1" if t.get("bridge") not in (None, "no") else
                          "-1" if t.get("tunnel") not in (None, "no") else "0"))
    except ValueError:
        return 0


# ---------------------------------------------------------------- główna logika

def main(pkl, outdir):
    os.makedirs(outdir, exist_ok=True)
    d = pickle.load(open(pkl, "rb"))
    ways = d["ways"]
    node_tags = d["node_tags"]
    boundary = wkb.loads(d["boundary"])
    pboundary = prep(boundary)

    node_xy = {}
    node_ll = {}
    node_ways = defaultdict(list)       # node -> [way idx]
    infra_adj = defaultdict(list)       # node -> [(node, len)]
    road_adj = defaultdict(list)        # jezdnie + infra – do sprawdzania "pas przerwany na skrzyżowaniu"
    node_layers = defaultdict(set)

    cls = []
    for i, w in enumerate(ways):
        c = classify(w["tags"])
        cls.append(c)
        lay = layer_of(w["tags"])
        for nid, (lon, lat) in zip(w["nodes"], w["coords"]):
            if nid not in node_xy:
                node_xy[nid] = xy(lon, lat)
                node_ll[nid] = (lon, lat)
            node_ways[nid].append(i)
            node_layers[nid].add(lay)
        if c[0] in ("infra", "road_quiet", "road_busy"):
            ns = w["nodes"]
            for a, b in zip(ns, ns[1:]):
                if a == b:
                    continue
                (x1, y1), (x2, y2) = node_xy[a], node_xy[b]
                L = math.hypot(x2 - x1, y2 - y1)
                if c[0] == "infra":
                    infra_adj[a].append((b, L))
                    infra_adj[b].append((a, L))
                if c[0] != "infra" or c[1] == "pas":
                    road_adj[a].append((b, L))
                    road_adj[b].append((a, L))

    print(f"dróg: {len(ways):,}  węzłów infry: {len(infra_adj):,}", file=sys.stderr)

    # segmenty infry do wyszukiwania przestrzennego
    seg_geoms, seg_nodes, seg_way = [], [], []
    for i, w in enumerate(ways):
        if cls[i][0] != "infra":
            continue
        ns = w["nodes"]
        for a, b in zip(ns, ns[1:]):
            if a != b:
                seg_geoms.append(LineString([node_xy[a], node_xy[b]]))
                seg_nodes.append((a, b))
                seg_way.append(i)
    tree = STRtree(seg_geoms)

    # wszystkie segmenty (dowolnych dróg) – do wykrywania "prawie połączonych" końców
    all_geoms, all_way = [], []
    for i, w in enumerate(ways):
        if cls[i][0] == "ignore":
            continue
        ns = w["nodes"]
        for a, b in zip(ns, ns[1:]):
            if a != b:
                all_geoms.append(LineString([node_xy[a], node_xy[b]]))
                all_way.append(i)
    all_tree = STRtree(all_geoms)

    # obiekty do liczenia "wielkości skrzyżowania"
    busy_geoms, busy_names = [], []
    pedx_geoms = []
    for i, w in enumerate(ways):
        if len(w["coords"]) < 2:
            continue
        if cls[i][0] in ("road_busy", "road_forbidden") or (cls[i][1] == "pas" and
                                                            w["tags"].get("highway") in BUSY_ROADS | FAST_ROADS):
            busy_geoms.append(LineString([xy(*c) for c in w["coords"]]))
            busy_names.append(w["tags"].get("name") or w["tags"].get("ref") or f"way{w['id']}")
        elif cls[i][0] == "crossing_ped":
            pedx_geoms.append(LineString([xy(*c) for c in w["coords"]]))
    busy_tree = STRtree(busy_geoms)
    pedx_tree = STRtree(pedx_geoms)

    def dijkstra(src, adj=None, cutoff=DIJKSTRA_CUTOFF):
        adj = adj if adj is not None else infra_adj
        dist = {src: 0.0}
        pq = [(0.0, src)]
        while pq:
            dd, u = heapq.heappop(pq)
            if dd > dist.get(u, 1e18) or dd > cutoff:
                continue
            for v, L in adj[u]:
                nd = dd + L
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        return dist

    # unikalne krawędzie infry na węźle (żeby węzeł w środku zamkniętej pętli nie był końcem)
    def infra_degree(n):
        return len({v for v, _ in infra_adj[n]})

    endpoints = []
    for n in infra_adj:
        if infra_degree(n) != 1:
            continue
        lon, lat = node_ll[n]
        if not pboundary.contains(Point(lon, lat)):
            continue
        endpoints.append(n)
    print(f"końców infry w granicach Warszawy: {len(endpoints):,}", file=sys.stderr)

    cands = []
    for n in endpoints:
        P = Point(node_xy[n])
        my_ways = node_ways[n]
        infra_types = sorted({cls[i][1] for i in my_ways if cls[i][0] == "infra"})
        infra_ids = sorted({ways[i]["id"] for i in my_ways if cls[i][0] == "infra"})
        others = [i for i in my_ways if cls[i][0] != "infra"]
        oc = defaultdict(list)
        for i in others:
            oc[cls[i][0]].append(i)
        ntag = node_tags.get(n, {})

        reasons = []
        score = 0.0
        is_lane = infra_types == ["pas"]

        # --- co jest na końcu
        if not others:
            # nic nie dotyka. Sprawdź czy coś przechodzi tuż obok (błąd mapy)
            near_any = None
            for j in all_tree.query(P.buffer(MAP_ERROR_GAP)):
                if all_way[j] in my_ways:
                    continue
                dd = all_geoms[j].distance(P)
                if dd <= MAP_ERROR_GAP and (near_any is None or dd < near_any[0]):
                    near_any = (dd, all_way[j])
            if near_any:
                reasons.append(f"niepołączone z {cls[near_any[1]][1]} w odl. {near_any[0]:.1f} m (pewnie błąd mapy)")
                end_type = "blad_mapy"
                score += 0.5
            else:
                reasons.append("ślepy koniec – nic dalej (krzaki?)")
                end_type = "slepy"
                score += 3.0
        elif oc.get("road_forbidden"):
            end_type = "zakaz"
            reasons.append("kończy się na drodze z zakazem dla rowerów")
            score += 4.0
        elif oc.get("road_busy"):
            hws = sorted({cls[i][1] for i in oc["road_busy"]}, key=lambda h: -ROAD_RANK.get(h, 0))
            end_type = "jezdnia_ruchliwa"
            rank = ROAD_RANK.get(hws[0], 3)
            if is_lane:
                # pas na drodze, droga leci dalej bez pasa
                reasons.append(f"pas rowerowy urywa się na {hws[0]}")
                score += 1.5 + 0.3 * (rank - 3)
            else:
                reasons.append(f"DDR wpada na jezdnię {hws[0]}")
                score += 1.5 + 0.4 * (rank - 3)
        elif oc.get("crossing_ped"):
            end_type = "przejscie_bez_przejazdu"
            reasons.append("kończy się na przejściu dla pieszych bez przejazdu rowerowego")
            score += 4.0
        elif oc.get("road_quiet"):
            end_type = "jezdnia_spokojna"
            hws = sorted({cls[i][1] for i in oc["road_quiet"]})
            reasons.append(f"wjazd na spokojną jezdnię ({', '.join(hws)})")
            score += 0.3 if not is_lane else 0.6
        elif oc.get("ped"):
            end_type = "chodnik"
            sub = sorted({cls[i][1] for i in oc["ped"]})
            reasons.append(f"kończy się na chodniku/ścieżce pieszej ({', '.join(sub)})")
            score += 3.0
            if "schody" in sub:
                reasons.append("SCHODY")
                score += 1.0
        elif oc.get("ped_bike"):
            end_type = "chodnik_rower_dopuszczony"
            reasons.append("przechodzi w chodnik/ciąg z dopuszczonym ruchem rowerów (bicycle=yes)")
            score += 1.2
        elif oc.get("construction"):
            end_type = "budowa"
            reasons.append("dalej budowa (highway=construction)")
            score += 0.2
        else:
            end_type = "inne"
            reasons.append("inne: " + ", ".join(sorted({cls[i][1] for i in others})))
            score += 1.0

        # dodatkowo, jeżeli na węźle jest przejście bez przejazdu jako tag węzła
        if ntag.get("highway") == "crossing" and ntag.get("bicycle") not in BIKE_OK and end_type.startswith("jezdnia"):
            reasons.append("węzeł to przejście dla pieszych (highway=crossing) bez przejazdu")
            score += 1.5
            end_type += "+przejscie"
        if "barrier" in ntag:
            reasons.append(f"bariera: {ntag['barrier']}")

        # --- czy obok jest inna infra, do której nie da się dojechać po infrze
        dist = dijkstra(n)
        my_layers = node_layers[n]
        road_dist = None
        gap = None  # (euclid, network or None, way idx, point xy)
        # kierunek jazdy = od przedostatniego węzła do końca
        nb = infra_adj[n][0][0]
        hx, hy = node_xy[n][0] - node_xy[nb][0], node_xy[n][1] - node_xy[nb][1]
        hlen = math.hypot(hx, hy) or 1.0
        hx, hy = hx / hlen, hy / hlen
        fwd = None  # najbliższa niepołączona infra na wprost (euclid, net, way idx, xy)
        fwd_any = False
        for j in tree.query(P.buffer(FORWARD_R)):
            a, b = seg_nodes[j]
            if a == n or b == n:
                continue
            g = seg_geoms[j]
            e = g.distance(P)
            if e > FORWARD_R:
                continue
            if not (node_layers[a] & my_layers or node_layers[b] & my_layers):
                continue
            proj = g.interpolate(g.project(P))
            ax, ay = node_xy[a]
            bx, by = node_xy[b]
            net = min(dist.get(a, 1e9) + math.hypot(proj.x - ax, proj.y - ay),
                      dist.get(b, 1e9) + math.hypot(proj.x - bx, proj.y - by))
            vx, vy = proj.x - node_xy[n][0], proj.y - node_xy[n][1]
            ahead = e > 1 and (vx * hx + vy * hy) / e >= math.cos(math.radians(FORWARD_HALF_ANGLE))
            if ahead and net <= max(3 * e, e + 150):
                fwd_any = True          # na wprost jest infra, do której da się dojechać
            if net <= max(4 * e, e + 120):
                continue
            # pas przerwany na skrzyżowaniu: pas -> pas tej samej jezdni, po jezdni blisko
            if is_lane and cls[seg_way[j]][1] == "pas":
                if road_dist is None:
                    road_dist = dijkstra(n, road_adj, 300)
                rnet = min(road_dist.get(a, 1e9) + math.hypot(proj.x - ax, proj.y - ay),
                           road_dist.get(b, 1e9) + math.hypot(proj.x - bx, proj.y - by))
                if rnet <= e * 1.3 + 25:
                    if ahead:
                        fwd_any = True
                    continue
            if ahead and (fwd is None or e < fwd[0]):
                fwd = (e, net if net < 1e8 else None, seg_way[j], (proj.x, proj.y))
            if e > GAP_R:
                continue
            if gap is None or e < gap[0]:
                gap = (e, net if net < 1e8 else None, seg_way[j], (proj.x, proj.y))

        gap_info = None
        if gap:
            e, net, wi, (px, py) = gap
            lon_g = px / KX + 21.0
            lat_g = py / KY + LAT0
            what = cls[wi][1]
            nm = ways[wi]["tags"].get("name", "")
            if e < MAP_ERROR_GAP:
                reasons.append(f"inna infra ({what}) {e:.1f} m obok, niepołączona – pewnie błąd mapy")
                score += 0.5
            else:
                if net is None:
                    reasons.append(f"TELEPORT: {what}{' ' + nm if nm else ''} {e:.0f} m dalej, "
                                   f"po infrze nie da się dojechać (>{DIJKSTRA_CUTOFF} m)")
                    score += 3.0 + 2.0 * (1 - e / GAP_R)
                else:
                    reasons.append(f"TELEPORT: {what}{' ' + nm if nm else ''} {e:.0f} m dalej, "
                                   f"po infrze {net:.0f} m")
                    score += 2.0 + 1.5 * (1 - e / GAP_R) + min(1.0, net / 600)
                if end_type == "blad_mapy":
                    pass
            gap_info = {"gap_m": round(e, 1), "net_m": None if net is None else round(net),
                        "gap_way": ways[wi]["id"], "gap_lon": round(lon_g, 7), "gap_lat": round(lat_g, 7)}

        # dalszy ciąg na wprost
        fwd_info = None
        if not gap and end_type not in ("blad_mapy", "budowa"):
            if fwd is not None and not fwd_any:
                e, net, wi, (px, py) = fwd
                what = cls[wi][1]
                reasons.append(f"dalszy ciąg ({what}) na wprost {e:.0f} m dalej, niepołączony"
                               + (f" (po infrze {net:.0f} m)" if net else ""))
                score += 1.0 + 1.0 * (1 - e / FORWARD_R)
                fwd_info = {"fwd_m": round(e), "fwd_lon": round(px / KX + 21.0, 7),
                            "fwd_lat": round(py / KY + LAT0, 7)}
            elif fwd is None and not fwd_any and end_type not in ("jezdnia_spokojna",):
                reasons.append(f"na wprost brak jakiejkolwiek infry w promieniu {FORWARD_R:.0f} m")
                score += 0.5

        # wielkość skrzyżowania – DDR umierająca na dużym skrzyżowaniu to "Dramat."
        busy_near = {busy_names[j] for j in busy_tree.query(P.buffer(JUNCTION_R))
                     if busy_geoms[j].distance(P) <= JUNCTION_R}
        pedx_near = sum(1 for j in pedx_tree.query(P.buffer(JUNCTION_R))
                        if pedx_geoms[j].distance(P) <= JUNCTION_R)
        if end_type not in ("jezdnia_spokojna", "blad_mapy", "budowa", "chodnik_rower_dopuszczony") \
                and (len(busy_near) >= 2 or pedx_near >= 2):
            bonus = min(2.5, 0.8 * max(0, len(busy_near) - 1) + 0.3 * min(pedx_near, 5))
            reasons.append(f"duże skrzyżowanie: {len(busy_near)} ruchliwe ulice, "
                           f"{pedx_near} przejść bez przejazdu w {JUNCTION_R:.0f} m")
            score += bonus

        # krótka izolowana wysepka infry (cały komponent < 60 m) – kurioza
        comp_len = sum(L for u in dist for v, L in infra_adj[u]) / 2
        reach_all = all(dd < DIJKSTRA_CUTOFF for dd in dist.values()) and len(dist) < 200
        if reach_all and comp_len < 60:
            reasons.append(f"wysepka infry, łącznie {comp_len:.0f} m")
            score += 1.0

        lon, lat = node_ll[n]
        road_names = sorted({ways[i]["tags"].get("name") for i in others if ways[i]["tags"].get("name")})
        cands.append({
            "node": n, "lon": lon, "lat": lat, "score": round(score, 2),
            "end_type": end_type, "infra": "+".join(infra_types), "infra_ways": infra_ids,
            "reasons": reasons, "touching_names": road_names, "gap": gap_info, "fwd": fwd_info,
        })

    # ------------------------------------------------------------ hotspoty
    cands.sort(key=lambda c: -c["score"])
    # union-find po odległości
    parent = list(range(len(cands)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid = defaultdict(list)
    for i, c in enumerate(cands):
        x, y = xy(c["lon"], c["lat"])
        gx, gy = int(x // CLUSTER_R), int(y // CLUSTER_R)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid[(gx + dx, gy + dy)]:
                    x2, y2 = xy(cands[j]["lon"], cands[j]["lat"])
                    if math.hypot(x - x2, y - y2) <= CLUSTER_R:
                        parent[find(i)] = find(j)
        grid[(gx, gy)].append(i)

    groups = defaultdict(list)
    for i in range(len(cands)):
        groups[find(i)].append(cands[i])

    # nazwy ulic w okolicy hotspotu
    named = [(i, w) for i, w in enumerate(ways) if w["tags"].get("name") and cls[i][0] in
             ("road_busy", "road_quiet", "road_forbidden", "infra")
             and w["tags"].get("highway") not in ("cycleway", "footway", "path", "service")]
    name_geoms = [LineString([xy(*c) for c in w["coords"]]) if len(w["coords"]) > 1 else Point(xy(*w["coords"][0]))
                  for _, w in named]
    name_tree = STRtree(name_geoms)

    hotspots = []
    for g in groups.values():
        g.sort(key=lambda c: -c["score"])
        sc = g[0]["score"] + 0.35 * sum(c["score"] for c in g[1:4])
        lon = sum(c["lon"] for c in g) / len(g)
        lat = sum(c["lat"] for c in g) / len(g)
        P = Point(xy(lon, lat))
        nm = {}
        for j in name_tree.query(P.buffer(45)):
            if name_geoms[j].distance(P) <= 45:
                w = named[j][1]
                n_ = w["tags"]["name"]
                nm[n_] = max(nm.get(n_, -1), ROAD_RANK.get(w["tags"].get("highway"), 0))
        names = [k for k, _ in sorted(nm.items(), key=lambda kv: -kv[1])][:4]
        has_teleport = any(c["gap"] and c["gap"]["gap_m"] >= MAP_ERROR_GAP for c in g)
        hotspots.append({
            "score": round(sc, 2), "lon": round(lon, 7), "lat": round(lat, 7),
            "names": names, "n_endpoints": len(g), "teleport": has_teleport,
            "types": sorted({c["end_type"] for c in g}),
            "endpoints": g,
        })
    hotspots.sort(key=lambda h: -h["score"])
    for k, h in enumerate(hotspots, 1):
        h["rank"] = k

    # ------------------------------------------------------------ eksport
    def links(lon, lat, node=None):
        z = 19
        n_ = 2 ** z
        tx = int((lon + 180) / 360 * n_)
        ty = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n_)
        return {
            "osm": f"https://www.openstreetmap.org/node/{node}" if node else
                   f"https://www.openstreetmap.org/#map=19/{lat:.6f}/{lon:.6f}",
            "osm_map": f"https://www.openstreetmap.org/#map=19/{lat:.6f}/{lon:.6f}&layers=Y",
            "esri_tile": f"https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{ty}/{tx}?blankTile=false",
            "streetview": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}",
            "gmaps_sat": f"https://www.google.com/maps/@{lat:.6f},{lon:.6f},20z/data=!3m1!1e3",
        }

    feats = []
    for h in hotspots:
        for c in h["endpoints"]:
            feats.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [c["lon"], c["lat"]]},
                "properties": {"hotspot": h["rank"], "hotspot_score": h["score"],
                               **{k: v for k, v in c.items() if k not in ("lon", "lat")},
                               "links": links(c["lon"], c["lat"], c["node"])},
            })
    with open(os.path.join(outdir, "kandydaci.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)

    with open(os.path.join(outdir, "hotspoty.json"), "w") as f:
        json.dump([{**{k: v for k, v in h.items() if k != "endpoints"},
                    "links": links(h["lon"], h["lat"]),
                    "endpoints": [{**c, "links": links(c["lon"], c["lat"], c["node"])} for c in h["endpoints"]]}
                   for h in hotspots], f, ensure_ascii=False, indent=1)

    with open(os.path.join(outdir, "hotspoty.csv"), "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["rank", "score", "teleport", "miejsce", "n_koncow", "typy", "powody",
                     "lat", "lon", "osm", "streetview", "esri_z19"])
        for h in hotspots:
            L = links(h["lon"], h["lat"])
            wr.writerow([h["rank"], h["score"], "TAK" if h["teleport"] else "", " / ".join(h["names"]),
                         h["n_endpoints"], ",".join(h["types"]),
                         " | ".join(r for c in h["endpoints"][:4] for r in c["reasons"]),
                         h["lat"], h["lon"], L["osm_map"], L["streetview"], L["esri_tile"]])

    from collections import Counter
    print(f"kandydatów (końców): {len(cands):,}, hotspotów: {len(hotspots):,}", file=sys.stderr)
    print("typy końców:", dict(Counter(c["end_type"] for c in cands)), file=sys.stderr)
    print(f"z teleportem (inna infra obok): {sum(1 for c in cands if c['gap'] and c['gap']['gap_m'] >= MAP_ERROR_GAP):,}",
          file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
