#!/usr/bin/env python3
"""Serwer WWW do ręcznej weryfikacji teleportów (bez zależności, sama biblioteka standardowa).

Czyta out/teleporty.json, oceny zapisuje na bieżąco do out/oceny.json.
Warstwa infry jest wyciągana z out/teleporty_mapa.html (data/*.pkl nie ma w repo).

Użycie:
    python scripts/serve_review.py                # http://127.0.0.1:8765
    python scripts/serve_review.py --port 9000
    python scripts/serve_review.py --host 0.0.0.0 # dostęp z sieci lokalnej, BEZ logowania
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = Path(__file__).resolve().parent / "serve_review.html"
OCENY_DOZWOLONE = {"tak", "nie", "moze", None}
MAX_KOMENTARZ = 2000
MAX_BODY = 64 * 1024


def streetview_url(lat, lon):
    return f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}"


def load_teleporty(path):
    """Tylko pola potrzebne w przeglądarce (pełny plik ma prawie 1 MB linków i punktacji)."""
    out = []
    for h in json.load(open(path, encoding="utf-8")):
        out.append({
            "rank": h["rank"],
            "lat": h["lat"],
            "lon": h["lon"],
            "names": h["names"],
            "werdykt": h["werdykt"],
            "typ": h.get("typ") or "",
            "komentarz": h.get("komentarz") or "",
            "runda": h.get("runda", 1),
            "teleport_nodes": h.get("teleport_nodes") or [],
            "endpoints": [{
                "node": e["node"],
                "lat": e["lat"],
                "lon": e["lon"],
                "infra": e["infra"],
                "end_type": e["end_type"],
                "reasons": e["reasons"],
                "gap": [e["gap"]["gap_lat"], e["gap"]["gap_lon"]]
                       if e.get("gap") and e["gap"].get("gap_lat") is not None else None,
            } for e in h["endpoints"]],
        })
    return out


def load_infra(path):
    """Zwraca JSON z warstwą infry jako bajty; brak mapy nie blokuje weryfikacji."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"UWAGA: brak {path} – mapa bez warstwy infry", file=sys.stderr)
        return b"[]"
    m = re.search(r"const INFRA=(.*?);\r?\nconst H=", text, re.S)
    if not m:
        print(f"UWAGA: nie znaleziono INFRA w {path} – mapa bez warstwy infry", file=sys.stderr)
        return b"[]"
    return m.group(1).encode("utf-8")


class OcenyStore:
    """Oceny w pliku JSON; zapis atomowy, pamięć zmieniana dopiero po udanym zapisie."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        # Uszkodzony plik ma przerwać start: inaczej następny zapis nadpisałby czyjąś pracę.
        self.data = json.load(open(path, encoding="utf-8")) if path.exists() else {}

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def set(self, rank, ocena, komentarz):
        key = str(rank)
        with self.lock:
            new = dict(self.data)
            if ocena is None and not komentarz:
                new.pop(key, None)
                entry = None
            else:
                entry = {"ocena": ocena, "komentarz": komentarz,
                         "czas": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                new[key] = entry
            self._write(new)
            self.data = new
            return entry

    def _write(self, data):
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".oceny-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            # Na Windows antywirus lub edytor potrafi chwilowo trzymać plik docelowy.
            for attempt in range(5):
                try:
                    os.replace(tmp, self.path)
                    return
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def export_csv(teleporty, oceny):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["rank", "ocena", "moj_komentarz", "czas", "werdykt_ai", "typ", "runda", "miejsce",
                "komentarz_ai", "lat", "lon", "streetview"])
    for h in teleporty:
        o = oceny.get(str(h["rank"]))
        if not o:
            continue
        w.writerow([h["rank"], o["ocena"] or "", o["komentarz"], o["czas"], h["werdykt"], h["typ"], h["runda"],
                    " / ".join(h["names"]), h["komentarz"], h["lat"], h["lon"], streetview_url(h["lat"], h["lon"])])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM, żeby Excel nie psuł polskich znaków


def make_handler(teleporty, infra, store):
    ranks = {h["rank"] for h in teleporty}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Teleporty/1"

        def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/teleporty":
                self._json(200, {"teleporty": teleporty, "oceny": store.snapshot()})
            elif path == "/api/infra":
                self._send(200, infra)
            elif path == "/api/oceny.csv":
                self._send(200, export_csv(teleporty, store.snapshot()), "text/csv; charset=utf-8",
                           {"Content-Disposition": 'attachment; filename="oceny.csv"'})
            else:
                self._json(404, {"error": "nie ma takiego adresu"})

        def do_PUT(self):
            m = re.fullmatch(r"/api/oceny/(\d+)", self.path)
            if not m:
                return self._json(404, {"error": "nie ma takiego adresu"})
            rank = int(m.group(1))
            if rank not in ranks:
                return self._json(404, {"error": f"nie ma teleportu #{rank}"})
            # Inna strona otwarta w przeglądarce nie wyśle application/json bez preflightu CORS,
            # a tego serwer nie obsługuje – dzięki temu nie może nadpisać ocen.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "wymagany application/json"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._json(411, {"error": "brak Content-Length"})
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"error": "nieprawidłowy rozmiar danych"})
            try:
                body = json.loads(self.rfile.read(length))
                ocena = body.get("ocena")
                komentarz = body.get("komentarz") or ""
            except (ValueError, AttributeError):
                return self._json(400, {"error": "nieprawidłowy JSON"})
            if not isinstance(ocena, (str, type(None))) or ocena not in OCENY_DOZWOLONE:
                return self._json(400, {"error": "ocena musi być tak, nie, moze albo null"})
            if not isinstance(komentarz, str) or len(komentarz) > MAX_KOMENTARZ:
                return self._json(400, {"error": f"komentarz: tekst do {MAX_KOMENTARZ} znaków"})
            try:
                entry = store.set(rank, ocena, komentarz.strip())
            except OSError as e:
                return self._json(500, {"error": f"nie udało się zapisać pliku: {e}"})
            self._json(200, {"rank": rank, "entry": entry})

        def log_request(self, code="-", size="-"):
            if not str(code).startswith("2"):
                super().log_request(code, size)

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Serwer do ręcznej weryfikacji teleportów")
    ap.add_argument("--host", default="127.0.0.1", help="adres (domyślnie tylko ten komputer)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dane", type=Path, default=ROOT / "out" / "teleporty.json")
    ap.add_argument("--mapa", type=Path, default=ROOT / "out" / "teleporty_mapa.html",
                    help="plik HTML, z którego brana jest warstwa infry")
    ap.add_argument("--oceny", type=Path, default=ROOT / "out" / "oceny.json")
    args = ap.parse_args()

    teleporty = load_teleporty(args.dane)
    infra = load_infra(args.mapa)
    store = OcenyStore(args.oceny)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(teleporty, infra, store))
    print(f"{len(teleporty)} teleportów, {len(store.data)} już ocenionych, oceny w {args.oceny}", flush=True)
    print(f"Otwórz http://{args.host}:{args.port}/  (Ctrl+C kończy)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
