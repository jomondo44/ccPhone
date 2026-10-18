"""Tiny offline web server: JSON API + single-page UI. Stdlib only."""

import argparse
import csv
import html
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

from . import bmi
from .db import TABLES, Store, dumps

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MAX_BODY = 20 * 1024 * 1024


def split_sheet_html(store, song_id):
    song = store.get("songs", song_id)
    if not song:
        return None
    rel = store.get("releases", song["release_id"]) if song["release_id"] else None
    rows = store.list("splits", {"song_id": song_id})
    e = lambda v: html.escape(str(v if v is not None else ""))
    tw = sum(r["writer_pct"] or 0 for r in rows)
    tp = sum(r["pub_pct"] or 0 for r in rows)
    tm = sum(r["master_pct"] or 0 for r in rows)
    body = "".join(
        f"<tr><td>{e(r['name'])}</td><td>{e(r['role'])}</td>"
        f"<td>{e(r['pro'])}</td><td>{e(r['ipi'])}</td>"
        f"<td class=n>{r['writer_pct'] or 0:g}%</td><td>{e(r['publisher'])}</td>"
        f"<td class=n>{r['pub_pct'] or 0:g}%</td>"
        f"<td class=n>{r['master_pct'] or 0:g}%</td>"
        f"<td class=sig></td><td class=date></td></tr>" for r in rows)
    return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Split Sheet - {e(song['title'])}</title><style>
body{{font:14px/1.4 system-ui,sans-serif;margin:24px;color:#111;background:#fff}}
h1{{margin:0 0 4px}} table{{width:100%;border-collapse:collapse;margin:16px 0}}
th,td{{border:1px solid #999;padding:6px;text-align:left;vertical-align:top}}
th{{background:#eee}} .n{{text-align:right}} .sig{{min-width:120px}}
.date{{min-width:70px}} .meta td{{border:none;padding:2px 12px 2px 0}}
.warn{{color:#b00020;font-weight:600}} .wrap{{overflow-x:auto}}
@media print{{button{{display:none}} body{{margin:10mm}}}}
</style></head><body>
<button onclick="print()">Print / Save as PDF</button>
<h1>Split Sheet</h1>
<table class=meta>
<tr><td><b>Song title</b></td><td>{e(song['title'])}</td></tr>
<tr><td><b>Release</b></td><td>{e(rel['title'] if rel else '')}</td></tr>
<tr><td><b>Artist</b></td><td>{e(rel['artist'] if rel else '')}</td></tr>
<tr><td><b>ISRC</b></td><td>{e(song['isrc'])}</td></tr>
<tr><td><b>Date written</b></td><td>{e(song['date_written'])}</td></tr>
<tr><td><b>Studio / location</b></td><td>{e(song['studio'])}</td></tr>
</table>
<div class=wrap><table><thead><tr><th>Name</th><th>Role</th><th>PRO</th>
<th>IPI/CAE</th><th>Writer %</th><th>Publisher</th><th>Pub %</th>
<th>Master %</th><th>Signature</th><th>Date</th></tr></thead>
<tbody>{body}</tbody><tfoot><tr><th colspan=4>Total</th>
<th class=n>{tw:g}%</th><th></th><th class=n>{tp:g}%</th>
<th class=n>{tm:g}%</th><th colspan=2></th></tr></tfoot></table></div>
{'' if abs(tw - 100) < 0.01 else '<p class=warn>Writer shares do not total 100%.</p>'}
<p>Notes: {e(song['notes'])}</p>
<p>All parties agree that the above percentages represent their ownership
share of the composition named above.</p>
</body></html>"""


def csv_export(store, table):
    rows = store.list(table)
    buf = io.StringIO()
    cols = ["id"] + TABLES[table]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "IndieAdminLite/1.0"

        def log_message(self, fmt, *args):
            if os.environ.get("INDIE_ADMIN_VERBOSE"):
                super().log_message(fmt, *args)

        # -- response helpers --
        def _send(self, code, body, ctype="application/json; charset=utf-8",
                  extra=None):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, dumps(obj))

        def _error(self, code, msg):
            self._json({"error": msg}, code)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("Request too large")
            raw = self.rfile.read(n) if n else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data

        def _route(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split("/") if p]
            return parts, dict(parse_qsl(u.query))

        def _same_origin(self):
            # Block cross-site writes from other pages open in the browser.
            origin = self.headers.get("Origin")
            if not origin:
                return True
            return urlparse(origin).netloc == self.headers.get("Host")

        def _dispatch(self, method):
            try:
                if method != "GET" and not self._same_origin():
                    return self._error(403, "Cross-origin request blocked")
                parts, query = self._route()
                if method == "GET":
                    return self._get(parts, query)
                if parts[:1] != ["api"]:
                    return self._error(404, "Not found")
                return self._api_write(method, parts[1:])
            except (ValueError, json.JSONDecodeError, sqlite3.IntegrityError) as ex:
                self._error(400, str(ex))
            except KeyError as ex:
                self._error(404, f"Unknown resource {ex}")
            except Exception as ex:  # keep the server alive on bugs
                self._error(500, f"{type(ex).__name__}: {ex}")

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        # -- routes --
        def _get(self, parts, query):
            if not parts or parts == ["index.html"]:
                return self._static("index.html")
            if parts[0] == "static" and len(parts) == 2:
                return self._static(parts[1])
            if parts[0] == "splitsheet" and len(parts) == 2:
                page = split_sheet_html(store, int(parts[1]))
                if page is None:
                    return self._error(404, "Song not found")
                return self._send(200, page, "text/html; charset=utf-8")
            if parts[0] != "api":
                return self._error(404, "Not found")
            parts = parts[1:]
            if len(parts) == 3 and parts[:2] == ["bmi", "sheet"]:
                sheet = bmi.copy_sheet(store, int(parts[2]))
                return self._json(sheet) if sheet else self._error(404, "Song not found")
            if parts == ["dashboard"]:
                return self._json(store.dashboard())
            if parts == ["export"]:
                return self._send(
                    200, json.dumps(store.export_all(), indent=1,
                                    ensure_ascii=False),
                    extra={"Content-Disposition":
                           'attachment; filename="indie-admin-backup.json"'})
            if len(parts) == 2 and parts[0] == "csv" and parts[1] in TABLES:
                return self._send(
                    200, csv_export(store, parts[1]), "text/csv; charset=utf-8",
                    {"Content-Disposition":
                     f'attachment; filename="{parts[1]}.csv"'})
            if len(parts) == 1:
                return self._json(store.list(parts[0], query))
            if len(parts) == 2:
                row = store.get(parts[0], int(parts[1]))
                return self._json(row) if row else self._error(404, "Not found")
            return self._error(404, "Not found")

        def _api_write(self, method, parts):
            if method == "POST" and parts == ["bmi", "import"]:
                body = self._body()
                return self._json(bmi.import_catalog(
                    store, str(body.get("csv", "")), bool(body.get("apply"))))
            if method == "POST" and parts == ["import"]:
                store.import_all(self._body())
                return self._json({"ok": True})
            if method == "POST" and len(parts) == 1:
                return self._json(store.create(parts[0], self._body()), 201)
            if len(parts) == 2:
                table, row_id = parts[0], int(parts[1])
                if method == "PUT":
                    row = store.update(table, row_id, self._body())
                    return self._json(row) if row else self._error(404, "Not found")
                if method == "DELETE":
                    store.delete(table, row_id)
                    return self._json({"ok": True})
            return self._error(404, "Not found")

        def _static(self, name):
            path = os.path.join(STATIC, os.path.basename(name))
            if not os.path.isfile(path):
                return self._error(404, "Not found")
            ctype = {"html": "text/html", "js": "text/javascript",
                     "css": "text/css", "json": "application/json",
                     "svg": "image/svg+xml", "png": "image/png"}.get(
                         name.rsplit(".", 1)[-1], "application/octet-stream")
            with open(path, "rb") as f:
                self._send(200, f.read(), ctype + "; charset=utf-8"
                           if ctype.startswith("text") else ctype)

    return Handler


def open_browser(url):
    # Termux: termux-open-url hands the link to Android's default browser.
    if shutil.which("termux-open-url"):
        subprocess.Popen(["termux-open-url", url], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Indie Musician Admin Lite")
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default 127.0.0.1, phone only)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", help="path to the SQLite data file")
    ap.add_argument("--no-browser", action="store_true",
                    help="don't open the browser automatically")
    args = ap.parse_args(argv)

    store = Store(args.db)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    print(f"Indie Musician Admin Lite running at {url}")
    print(f"Data file: {store.path}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.6, open_browser, (url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
