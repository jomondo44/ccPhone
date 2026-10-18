import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indie_admin.db import CHECKLIST_TEMPLATE, Store  # noqa: E402
from indie_admin.server import make_handler  # noqa: E402


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.store.conn.close()
        self.tmp.cleanup()

    def test_release_seeds_dated_checklist(self):
        r = self.store.create("releases", {"title": "Neon", "release_date": "2026-12-01"})
        tasks = self.store.list("checklist", {"release_id": r["id"]})
        self.assertEqual(len(tasks), len(CHECKLIST_TEMPLATE))
        self.assertEqual(tasks[0]["due_date"], "2026-10-06")  # 56 days before
        self.assertIn("2026-12-01", [t["due_date"] for t in tasks])

    def test_moving_release_date_moves_open_tasks(self):
        r = self.store.create("releases", {"title": "Neon", "release_date": "2026-12-01"})
        tasks = self.store.list("checklist", {"release_id": r["id"]})
        self.store.update("checklist", tasks[0]["id"], {"done": 1})
        self.store.update("releases", r["id"], {"release_date": "2026-12-08"})
        after = {t["id"]: t for t in self.store.list("checklist", {"release_id": r["id"]})}
        self.assertEqual(after[tasks[0]["id"]]["due_date"], "2026-10-06")  # done: unchanged
        self.assertEqual(after[tasks[1]["id"]]["due_date"], "2026-10-20")  # +7

    def test_undated_release_gets_dates_later(self):
        r = self.store.create("releases", {"title": "Someday"})
        self.store.update("releases", r["id"], {"release_date": "2026-12-01"})
        tasks = self.store.list("checklist", {"release_id": r["id"]})
        self.assertTrue(all(t["due_date"] for t in tasks))

    def test_required_fields(self):
        with self.assertRaises(ValueError):
            self.store.create("collaborators", {"name": "  "})
        with self.assertRaises(ValueError):
            self.store.create("splits", {"name": "Ann"})  # no song_id

    def test_dashboard_flags_bad_splits(self):
        s = self.store.create("songs", {"title": "Song A"})
        self.store.create("splits", {"song_id": s["id"], "name": "A", "writer_pct": 60, "signed": 1})
        self.store.create("splits", {"song_id": s["id"], "name": "B", "writer_pct": 30, "signed": 1})
        issues = self.store.dashboard()["split_issues"]
        self.assertEqual(issues[0]["writer_total"], 90)
        self.store.create("splits", {"song_id": s["id"], "name": "C", "writer_pct": 10, "signed": 1})
        self.assertEqual(self.store.dashboard()["split_issues"], [])

    def test_export_import_roundtrip(self):
        c = self.store.create("collaborators", {"name": "Dee", "pro": "BMI"})
        s = self.store.create("songs", {"title": "X"})
        self.store.create("splits", {"song_id": s["id"], "collaborator_id": c["id"],
                                     "name": "Dee", "writer_pct": 100})
        dump = json.loads(json.dumps(self.store.export_all()))
        other = Store(os.path.join(self.tmp.name, "o.db"))
        other.create("collaborators", {"name": "will be replaced"})
        other.import_all(dump)
        self.assertEqual([x["name"] for x in other.list("collaborators")], ["Dee"])
        self.assertEqual(other.list("splits")[0]["collaborator_id"], c["id"])
        other.conn.close()


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(os.path.join(cls.tmp.name, "h.db"))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.store.conn.close()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_pages_served(self):
        for path in ["/", "/static/app.js", "/static/app.css", "/api/dashboard"]:
            self.assertEqual(self.req("GET", path)[0], 200, path)

    def test_crud_and_split_sheet(self):
        code, body = self.req("POST", "/api/songs", {"title": "Night <Drive>"})
        self.assertEqual(code, 201)
        sid = json.loads(body)["id"]
        self.req("POST", "/api/splits", {"song_id": sid, "name": "Jo", "writer_pct": 100})
        code, page = self.req("GET", f"/splitsheet/{sid}")
        self.assertEqual(code, 200)
        self.assertIn("Night &lt;Drive&gt;", page)
        self.assertNotIn("do not total", page)
        code, body = self.req("PUT", f"/api/songs/{sid}", {"isrc": "USABC2600001"})
        self.assertEqual(json.loads(body)["isrc"], "USABC2600001")
        self.assertEqual(self.req("DELETE", f"/api/songs/{sid}")[0], 200)
        self.assertEqual(self.req("GET", f"/api/songs/{sid}")[0], 404)

    def test_errors(self):
        self.assertEqual(self.req("GET", "/api/nope")[0], 404)
        self.assertEqual(self.req("POST", "/api/releases", {})[0], 400)
        self.assertEqual(self.req("POST", "/api/releases", {"title": "x"},
                                  {"Origin": "http://evil.example"})[0], 403)

    def test_csv(self):
        self.req("POST", "/api/collaborators", {"name": "Csv Person"})
        code, body = self.req("GET", "/api/csv/collaborators")
        self.assertEqual(code, 200)
        self.assertIn("Csv Person", body)


if __name__ == "__main__":
    unittest.main()


class BmiTests(unittest.TestCase):
    def setUp(self):
        from indie_admin import bmi
        self.bmi = bmi
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "b.db"))

    def tearDown(self):
        self.store.conn.close()
        self.tmp.cleanup()

    def test_simple_catalog_preview_then_apply(self):
        self.store.create("songs", {"title": "Blocked Exit"})
        csv_text = ("Title,Registration Origin,BMI Work#\n"
                    "BETWEEN THE STARS,Registered,79855214\n"
                    "BLOCKED EXIT,Registered,79854791\n")
        res = self.bmi.import_catalog(self.store, csv_text)
        self.assertEqual((res["add"], res["update"]), (1, 1))
        self.assertEqual(len(self.store.list("songs")), 1)  # preview wrote nothing
        self.bmi.import_catalog(self.store, csv_text, apply=True)
        songs = {s["title"]: s for s in self.store.list("songs")}
        self.assertEqual(songs["Blocked Exit"]["bmi_work_no"], "79854791")
        self.assertEqual(songs["Between The Stars"]["bmi_status"], "Registered")
        again = self.bmi.import_catalog(self.store, csv_text)
        self.assertEqual(again["same"], 2)

    def test_writer_rows_and_200_percent(self):
        csv_text = ("﻿Work Title,Work #,ISWC,Writer Name,IPI Name #,Share %\n"
                    "SONG A,111,T-123,ROBERTS JAMES WALLACE MR,01351262970,100.00\n"
                    ",,,DOE JANE,0999,100.00\n")
        self.bmi.import_catalog(self.store, csv_text, apply=True)
        song = self.store.list("songs")[0]
        self.assertEqual(song["iswc"], "T-123")
        splits = self.store.list("splits", {"song_id": song["id"]})
        self.assertEqual([(s["name"], s["writer_pct"]) for s in splits],
                         [("James Wallace Roberts", 50), ("Jane Doe", 50)])

    def test_copy_sheet_doubles_shares_without_publisher(self):
        s = self.store.create("songs", {"title": "X"})
        self.store.create("splits", {"song_id": s["id"], "name": "James Roberts",
                                     "writer_pct": 100, "pro": "BMI",
                                     "ipi": "01351262970", "role": "Songwriter"})
        sheet = self.bmi.copy_sheet(self.store, s["id"])
        w = sheet["steps"][2]["writers"][0]
        self.assertEqual((w["share"], w["role"], w["last"]), (200, "Composer/Author", "Roberts"))
        self.assertEqual(sheet["problems"], [])

    def test_bad_csv(self):
        with self.assertRaises(ValueError):
            self.bmi.parse_catalog("a,b\n1,2\n")

    def test_old_database_is_migrated(self):
        import sqlite3
        path = os.path.join(self.tmp.name, "old.db")
        c = sqlite3.connect(path)
        c.execute("CREATE TABLE songs (id INTEGER PRIMARY KEY, release_id INTEGER, "
                  "title TEXT NOT NULL, isrc TEXT DEFAULT '', date_written TEXT DEFAULT '', "
                  "studio TEXT DEFAULT '', notes TEXT DEFAULT '')")
        c.execute("INSERT INTO songs (title) VALUES ('Old')")
        c.commit(); c.close()
        st = Store(path)
        self.assertEqual(st.list("songs")[0]["bmi_status"], "Not registered")
        st.conn.close()
