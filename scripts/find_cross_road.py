#!/usr/bin/env python3
"""Druga runda: teleporty "przez ulicę", których pierwsza runda nie złapała.

K1  koniec infry przy jezdni (pierwsza runda uznała to automatem za OK), ale najbliższa niepołączona
    infra / dalszy ciąg leży PO DRUGIEJ STRONIE jezdni – czyli "połączenie" to przejechanie w poprzek
    ulicy bez przejazdu (Sokola, Zamoyskiego).
K2  końce, które weryfikacja pierwszej rundy uznała za OK, a kontynuacja jest po drugiej stronie jezdni
    (Al. Zieleniecka #855).
K3  "teoretyczne połączenie": infra w OSM przechodzi przez jezdnię, ale przejazd nie jest otagowany,
    albo jest otagowany jako zebra-tylko / unmarked – w terenie często jest tylko przejście dla pieszych
    albo nic.

Wynik: out/weryfikacja2/kandydaci.json + paczki paczkaNN.json (po ~40) + obrazki img/.

Użycie:
    python3 scripts/find_cross_road.py data/warszawa_ways.pkl out/hotspoty.json out/weryfikacja out/weryfikacja2
"""
import glob
import json
import math
import os
import pickle
import sys
from collections import defaultdict

from shapely import STRtree, wkb
from shapely.geometry import LineString, Point
from shapely.prepared import prep

sys.path.insert(0, os.path.dirname(__file__))
from find_candidates import KX, KY, LAT0, classify, xy  # noqa: E402
from prepare_review import auto_ok  # noqa: E402

CAR = ("road_busy", "road_quiet", "road_forbidden")
NO_CROSS_HW = {"service", "track", "living_street", "busway", "bus_guideway"}
K3_ROADS_ALWAYS = {"tertiary", "tertiary_link", "secondary", "secondary_link", "primary", "primary_link",
                   "trunk", "trunk_link", "motorway_link"}
K3_ROADS_IF_FLAGGED = {"unclassified", "residential", "road"}
BATCH = 40
PAIR_R = 90.0


def ll(x, y):
    return (round(x / KX + 21.0, 7), round(y / KY + LAT0, 7))


def main(pkl, hot_path, rdir, outdir):
    os.makedirs(os.path.join(outdir, "img"), exist_ok=True)
    d = pickle.load(open(pkl, "rb"))
    W, NT = d["ways"], d["node_tags"]
    boundary = prep(wkb.loads(d["boundary"]))
    cls = [classify(w["tags"]) for w in W]
    nxy, nways = {}, defaultdict(list)
    for i, w in enumerate(W):
        for n, (lo, la) in zip(w["nodes"], w["coords"]):
            nxy.setdefault(n, xy(lo, la))
            nways[n].append(i)

    car_geoms, car_way = [], []
    for i, w in enumerate(W):
        if cls[i][0] in CAR and w["tags"].get("highway") not in NO_CROSS_HW or \
                (cls[i][0] == "infra" and cls[i][1] in ("pas", "kontraruch")):
            ns = w["nodes"]
            for a, b in zip(ns, ns[1:]):
                if a != b:
                    car_geoms.append(LineString([nxy[a], nxy[b]]))
                    car_way.append(i)
    car_tree = STRtree(car_geoms)

    def crossed_roads(p, q, endpoint_node=None, nb=None):
        """Nazwy/klasy jezdni, które przecina odcinek p->q (pomijając sam punkt startowy)."""
        seg = LineString([p, q])
        out = {}
        P = Point(p)
        for j in car_tree.query(seg):
            g = car_geoms[j]
            if not g.intersects(seg):
                continue
            inter = g.intersection(seg)
            if inter.is_empty or P.distance(inter) < 1.0:
                continue
            t = W[car_way[j]]["tags"]
            out[t.get("name") or t.get("highway")] = t.get("highway")
        # koniec leży NA jezdni (wspólny węzeł): po drugiej stronie, jeśli nb i q po przeciwnych stronach
        if endpoint_node is not None and nb is not None:
            for i in nways[endpoint_node]:
                if not (cls[i][0] in CAR and W[i]["tags"].get("highway") not in NO_CROSS_HW):
                    continue
                ns = W[i]["nodes"]
                k = ns.index(endpoint_node)
                a = ns[k - 1] if k > 0 else ns[k]
                b = ns[k + 1] if k < len(ns) - 1 else ns[k]
                (ax, ay), (bx, by) = nxy[a], nxy[b]
                if (ax, ay) == (bx, by):
                    continue

                def side(pt):
                    return (bx - ax) * (pt[1] - ay) - (by - ay) * (pt[0] - ax)
                s1, s2 = side(nxy[nb]), side(q)
                if s1 * s2 < 0 and abs(s2) / math.hypot(bx - ax, by - ay) > 3:
                    t = W[i]["tags"]
                    out[t.get("name") or t.get("highway")] = t.get("highway")
        return out

    def infra_nb(n):
        for i in nways[n]:
            if cls[i][0] == "infra":
                ns = W[i]["nodes"]
                k = ns.index(n)
                return ns[k - 1] if k > 0 else ns[k + 1] if len(ns) > 1 else None
        return None

    H = json.load(open(hot_path))
    verdicts = {}
    for p in sorted(glob.glob(os.path.join(rdir, "wynik*.json"))):
        for v in json.load(open(p)):
            verdicts[int(v["rank"])] = v

    cands = []
    # wszystkie końce infry (do szukania par twarzą w twarz przez ulicę)
    all_eps = [(h, e) for h in H for e in h["endpoints"]]
    ep_grid = defaultdict(list)
    for h, e in all_eps:
        x, y = nxy[e["node"]]
        ep_grid[(int(x // PAIR_R), int(y // PAIR_R))].append((h, e))

    def pair_target(e):
        """Najbliższy inny koniec infry w PAIR_R m, niepołączony po infrze (inny hotspot albo luka)."""
        x, y = nxy[e["node"]]
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for h2, e2 in ep_grid[(int(x // PAIR_R) + dx, int(y // PAIR_R) + dy)]:
                    if e2["node"] == e["node"] or set(e2["infra"].split("+")) <= {"pas", "kontraruch"}:
                        continue
                    x2, y2 = nxy[e2["node"]]
                    dd = math.hypot(x2 - x, y2 - y)
                    if 5 < dd <= PAIR_R and (best is None or dd < best[0]):
                        best = (dd, e2)
        return best

    # ---------------- K1 / K2
    for h in H:
        v = verdicts.get(h["rank"])
        if v and v["werdykt"] != "ok":
            continue  # już jest teleportem / niepewne / błąd mapy
        for e in h["endpoints"]:
            ao = auto_ok(e)
            reviewed_ok = v is not None and not ao
            if ao in ("kontraruch", "budowa", "blad_mapy", "pas na jezdni"):
                continue
            if not ao and not reviewed_ok:
                continue
            if set(e["infra"].split("+")) <= {"pas", "kontraruch"}:
                continue
            n = e["node"]
            if reviewed_ok and e["end_type"] == "chodnik_rower_dopuszczony":
                cands.append({
                    "kat": "K4", "lat": e["lat"], "lon": e["lon"], "node": n, "rank1": h["rank"],
                    "names": h["names"], "opis": f"{e['infra']} przechodzi w chodnik z dopuszczonym ruchem rowerów",
                    "reasons": e["reasons"], "cel": None, "werdykt_rundy1": v["komentarz"]})
                continue
            tgts = []
            if e.get("gap") and e["gap"]["gap_m"] >= 2.5:
                tgts.append(("luka", e["gap"]["gap_lon"], e["gap"]["gap_lat"], e["gap"]["gap_m"]))
            if e.get("fwd"):
                tgts.append(("dalszy_ciag", e["fwd"]["fwd_lon"], e["fwd"]["fwd_lat"], e["fwd"]["fwd_m"]))
            pt = pair_target(e)
            if pt:
                tgts.append(("drugi_koniec", pt[1]["lon"], pt[1]["lat"], pt[0]))
            tgt = roads = None
            for t_ in tgts:
                r_ = crossed_roads(nxy[n], xy(t_[1], t_[2]), n, infra_nb(n))
                if r_:
                    tgt, roads = t_, r_
                    break
            if not tgt:
                continue
            cands.append({
                "kat": "K2" if reviewed_ok else "K1", "lat": e["lat"], "lon": e["lon"], "node": n,
                "rank1": h["rank"], "names": h["names"],
                "opis": f"{e['infra']} kończy się ({e['end_type']}); {tgt[0]} {tgt[3]:.0f} m dalej, "
                        f"po drugiej stronie: {', '.join(f'{k} ({v_})' for k, v_ in roads.items())}",
                "reasons": e["reasons"], "cel": [tgt[2], tgt[1]],
                "werdykt_rundy1": v["komentarz"] if reviewed_ok else "automat: wjazd na jezdnię",
            })

    # ---------------- K3 – infra przechodzi przez jezdnię bez przejazdu w tagach
    seen = set()
    for n, ws in nways.items():
        roads = [i for i in ws if cls[i][0] in CAR and W[i]["tags"].get("highway") not in NO_CROSS_HW]
        inf = [i for i in ws if cls[i][0] == "infra" and cls[i][1] not in ("pas", "kontraruch")]
        if not roads or not inf:
            continue
        deg = 0
        for i in inf:
            ns = W[i]["nodes"]
            for k, x in enumerate(ns):
                if x == n:
                    deg += (k > 0) + (k < len(ns) - 1)
        if deg < 2:
            continue  # koniec infry – to obsługuje pierwsza runda / K1
        lo, la = W[inf[0]]["coords"][W[inf[0]]["nodes"].index(n)]
        if not boundary.contains(Point(lo, la)):
            continue
        wt = [W[i]["tags"] for i in inf]
        nt = NT.get(n, {})
        marked_way = any(t.get("cycleway") == "crossing" or t.get("footway") == "crossing"
                         or t.get("path") == "crossing" for t in wt)
        marks = {t.get("crossing:markings", "") for t in wt} | {nt.get("crossing:markings", "")}
        crs = {t.get("crossing", "") for t in wt} | {nt.get("crossing", "")}
        if not marked_way and nt.get("highway") not in ("crossing", "traffic_signals"):
            flag = "brak tagów przejazdu"
        elif crs & {"unmarked", "no"} or "no" in marks:
            flag = "otagowane jako nieoznakowane (unmarked/no)"
        elif "zebra" in "".join(marks) and not any("dots" in m or "dashes" in m for m in marks):
            flag = "otagowane jako sama zebra (bez kostki przejazdu)"
        else:
            continue
        hws = {W[i]["tags"]["highway"] for i in roads}
        if not (hws & K3_ROADS_ALWAYS or (hws & K3_ROADS_IF_FLAGGED and flag != "brak tagów przejazdu")):
            continue
        key = (round(lo, 4), round(la, 4))
        if key in seen:
            continue
        seen.add(key)
        rn = sorted({W[i]["tags"].get("name") or W[i]["tags"]["highway"] for i in roads})
        cands.append({
            "kat": "K3", "lat": la, "lon": lo, "node": n, "rank1": None, "names": rn,
            "opis": f"infra ({'+'.join(sorted({cls[i][1] for i in inf}))}) przecina {', '.join(rn)} "
                    f"({', '.join(sorted(hws))}) – {flag}",
            "reasons": [flag], "cel": None, "werdykt_rundy1": None,
        })

    # grupowanie bliskich (25 m) żeby jedno skrzyżowanie = jeden kandydat
    cands.sort(key=lambda c: (c["kat"], c["lat"]))
    groups = []
    for c in cands:
        x, y = xy(c["lon"], c["lat"])
        for g in groups:
            gx, gy = xy(g["lon"], g["lat"])
            if math.hypot(x - gx, y - gy) < 25:
                g["punkty"].append(c)
                break
        else:
            groups.append({"lat": c["lat"], "lon": c["lon"], "punkty": [c]})
    for k, g in enumerate(groups, 1):
        g["id"] = k
        g["kat"] = "+".join(sorted({c["kat"] for c in g["punkty"]}))
        g["names"] = sorted({n for c in g["punkty"] for n in c["names"]})[:4]
        g["img"] = f"img/{k:04d}.jpg"
    from collections import Counter
    print("kandydatów:", len(cands), dict(Counter(c["kat"] for c in cands)),
          "grup:", len(groups), dict(Counter(g["kat"] for g in groups)), file=sys.stderr)
    json.dump(groups, open(os.path.join(outdir, "kandydaci.json"), "w"), ensure_ascii=False, indent=1)
    # paczki, posortowane geograficznie, żeby jeden agent miał zwarty kawałek miasta
    groups_sorted = sorted(groups, key=lambda g: (round(g["lon"] * 20), g["lat"]))
    nb = 0
    for s in range(0, len(groups_sorted), BATCH):
        nb += 1
        json.dump({"paczka": nb, "kandydaci": groups_sorted[s:s + BATCH]},
                  open(os.path.join(outdir, f"paczka{nb:02d}.json"), "w"), ensure_ascii=False, indent=1)
    print("paczek:", nb, file=sys.stderr)

    if "--no-img" in sys.argv:
        return
    from render import Renderer
    R = Renderer(pkl)
    for g in groups:
        p = os.path.join(outdir, g["img"])
        if os.path.exists(p):
            continue
        eps = []
        for c in g["punkty"]:
            e = {"lat": c["lat"], "lon": c["lon"]}
            if c["cel"]:
                e["gap"] = {"gap_m": 10, "gap_lat": c["cel"][0], "gap_lon": c["cel"][1]}
            eps.append(e)
        R.render(g["lat"], g["lon"], p, 19, 4, f"[{g['id']}] {g['kat']} " + " / ".join(g["names"][:3]), eps)


if __name__ == "__main__":
    main(*sys.argv[1:5])
