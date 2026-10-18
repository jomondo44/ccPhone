"""SQLite storage for Indie Musician Admin Lite (stdlib only)."""

import datetime as dt
import json
import os
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS collaborators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    pro TEXT DEFAULT '',
    ipi TEXT DEFAULT '',
    publisher TEXT DEFAULT '',
    socials TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created TEXT DEFAULT (date('now'))
);
CREATE TABLE IF NOT EXISTS contact_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collaborator_id INTEGER NOT NULL REFERENCES collaborators(id) ON DELETE CASCADE,
    date TEXT DEFAULT (date('now')),
    method TEXT DEFAULT '',
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT DEFAULT '',
    kind TEXT DEFAULT 'Single',
    release_date TEXT DEFAULT '',
    status TEXT DEFAULT 'Planning',
    distributor TEXT DEFAULT '',
    upc TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS checklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    due_date TEXT DEFAULT '',
    done INTEGER DEFAULT 0,
    sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id INTEGER REFERENCES releases(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    isrc TEXT DEFAULT '',
    date_written TEXT DEFAULT '',
    studio TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    collaborator_id INTEGER REFERENCES collaborators(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    role TEXT DEFAULT '',
    writer_pct REAL DEFAULT 0,
    publisher TEXT DEFAULT '',
    pub_pct REAL DEFAULT 0,
    master_pct REAL DEFAULT 0,
    pro TEXT DEFAULT '',
    ipi TEXT DEFAULT '',
    signed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS promos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id INTEGER REFERENCES releases(id) ON DELETE SET NULL,
    outlet TEXT NOT NULL,
    kind TEXT DEFAULT 'Playlist',
    contact TEXT DEFAULT '',
    email TEXT DEFAULT '',
    status TEXT DEFAULT 'To pitch',
    pitched_on TEXT DEFAULT '',
    follow_up TEXT DEFAULT '',
    cost REAL DEFAULT 0,
    result_link TEXT DEFAULT '',
    notes TEXT DEFAULT ''
);
"""

# Columns added after the first release; added to older databases on startup.
MIGRATIONS = {
    "songs": [
        ("duration", "TEXT DEFAULT ''"),
        ("work_content", "TEXT DEFAULT 'Music and Lyrics'"),
        ("language", "TEXT DEFAULT 'English'"),
        ("alt_titles", "TEXT DEFAULT ''"),
        ("genre_type", "TEXT DEFAULT 'All Other Genres'"),
        ("has_samples", "INTEGER DEFAULT 0"),
        ("iswc", "TEXT DEFAULT ''"),
        ("bmi_status", "TEXT DEFAULT 'Not registered'"),
        ("bmi_work_no", "TEXT DEFAULT ''"),
        ("bmi_date", "TEXT DEFAULT ''"),
        ("mlc_status", "TEXT DEFAULT 'Not registered'"),
        ("sx_status", "TEXT DEFAULT 'Not registered'"),
    ],
}

# Whitelisted writable columns per table. Anything else in a request is ignored.
TABLES = {
    "collaborators": ["name", "role", "email", "phone", "pro", "ipi",
                      "publisher", "socials", "notes"],
    "contact_log": ["collaborator_id", "date", "method", "note"],
    "releases": ["title", "artist", "kind", "release_date", "status",
                 "distributor", "upc", "notes"],
    "checklist": ["release_id", "task", "due_date", "done", "sort"],
    "songs": ["release_id", "title", "isrc", "date_written", "studio", "notes",
              "duration", "work_content", "language", "alt_titles", "genre_type",
              "has_samples", "iswc", "bmi_status", "bmi_work_no", "bmi_date",
              "mlc_status", "sx_status"],
    "splits": ["song_id", "collaborator_id", "name", "role", "writer_pct",
               "publisher", "pub_pct", "master_pct", "pro", "ipi", "signed"],
    "promos": ["release_id", "outlet", "kind", "contact", "email", "status",
               "pitched_on", "follow_up", "cost", "result_link", "notes"],
}

REQUIRED = {
    "collaborators": ["name"],
    "contact_log": ["collaborator_id"],
    "releases": ["title"],
    "checklist": ["release_id", "task"],
    "songs": ["title"],
    "splits": ["song_id", "name"],
    "promos": ["outlet"],
}

# Columns a list request may filter on (?release_id=3 etc.).
FILTERS = {"release_id", "song_id", "collaborator_id"}

ORDER = {
    "collaborators": "name COLLATE NOCASE",
    "contact_log": "date DESC, id DESC",
    "releases": "CASE WHEN release_date='' THEN 1 ELSE 0 END, release_date DESC",
    "checklist": "sort, due_date, id",
    "songs": "title COLLATE NOCASE",
    "splits": "id",
    "promos": "CASE status WHEN 'To pitch' THEN 0 WHEN 'Pitched' THEN 1 "
              "WHEN 'Followed up' THEN 2 ELSE 3 END, follow_up, id",
}

# Default release checklist: (days relative to release date, task).
CHECKLIST_TEMPLATE = [
    (-56, "Final mix approved"),
    (-49, "Master delivered (WAV 24-bit + MP3)"),
    (-49, "Split sheet signed by all writers"),
    (-42, "Artwork final (3000x3000 JPG)"),
    (-42, "Register songs with PRO"),
    (-35, "Upload to distributor"),
    (-35, "ISRC / UPC codes confirmed"),
    (-30, "Register with The MLC / mechanical admin"),
    (-28, "Spotify for Artists editorial pitch"),
    (-28, "Press release / one-sheet written"),
    (-21, "Pre-save link live"),
    (-21, "Pitch playlists, blogs, radio"),
    (-14, "Teaser content scheduled"),
    (-7, "Lyrics submitted (Musixmatch / Genius)"),
    (-3, "Notify mailing list and collaborators"),
    (0, "Release day posts + stories"),
    (3, "Thank-you and follow-ups to press"),
    (7, "Review streams & promo results"),
    (14, "Register with SoundExchange (if not done)"),
]


def default_db_path():
    base = os.environ.get("INDIE_ADMIN_HOME") or os.path.join(
        os.path.expanduser("~"), ".indie_admin")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "data.db")


def _shift(date_str, days):
    try:
        d = dt.date.fromisoformat(date_str)
    except (TypeError, ValueError):
        return ""
    return (d + dt.timedelta(days=days)).isoformat()


class Store:
    def __init__(self, path=None):
        self.path = path or default_db_path()
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in
                    self.conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols:
                if name not in have:
                    self.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        self.conn.commit()

    # ---- generic CRUD -------------------------------------------------
    def _clean(self, table, data, partial=False):
        cols = TABLES[table]
        out = {k: data[k] for k in cols if k in data}
        for k, v in out.items():
            if v == "" and k.endswith("_id"):
                out[k] = None
            elif isinstance(v, bool):
                out[k] = int(v)
        for req in REQUIRED[table]:
            if (not partial or req in out) and not str(
                    out.get(req) if out.get(req) is not None else "").strip():
                raise ValueError(f"'{req}' is required")
        return out

    def list(self, table, filters=None):
        if table not in TABLES:
            raise KeyError(table)
        sql = f"SELECT * FROM {table}"
        args = []
        where = []
        for k, v in (filters or {}).items():
            if k in FILTERS and k in TABLES[table]:
                where.append(f"{k} = ?")
                args.append(v)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {ORDER[table]}"
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args)]

    def get(self, table, row_id):
        if table not in TABLES:
            raise KeyError(table)
        with self.lock:
            r = self.conn.execute(f"SELECT * FROM {table} WHERE id = ?",
                                  (row_id,)).fetchone()
        return dict(r) if r else None

    def create(self, table, data):
        if table not in TABLES:
            raise KeyError(table)
        row = self._clean(table, data)
        cols = ", ".join(row) or "id"
        marks = ", ".join("?" for _ in row) or "NULL"
        with self.lock:
            cur = self.conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({marks})",
                list(row.values()))
            new_id = cur.lastrowid
            if table == "releases" and data.get("use_template", True):
                self._seed_checklist(new_id, row.get("release_date", ""))
            self.conn.commit()
        return self.get(table, new_id)

    def update(self, table, row_id, data):
        if table not in TABLES:
            raise KeyError(table)
        row = self._clean(table, data, partial=True)
        if row:
            sets = ", ".join(f"{k} = ?" for k in row)
            with self.lock:
                old = self.conn.execute(
                    f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
                self.conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?",
                                  [*row.values(), row_id])
                if (table == "releases" and old and "release_date" in row
                        and row["release_date"] != old["release_date"]):
                    self._reschedule(row_id, old["release_date"],
                                     row["release_date"])
                self.conn.commit()
        return self.get(table, row_id)

    def delete(self, table, row_id):
        if table not in TABLES:
            raise KeyError(table)
        with self.lock:
            self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
            self.conn.commit()

    # ---- release checklist helpers -------------------------------------
    def _seed_checklist(self, release_id, release_date):
        self.conn.executemany(
            "INSERT INTO checklist (release_id, task, due_date, sort) "
            "VALUES (?, ?, ?, ?)",
            [(release_id, task, _shift(release_date, days), i)
             for i, (days, task) in enumerate(CHECKLIST_TEMPLATE)])

    def _reschedule(self, release_id, old_date, new_date):
        """Move open checklist due dates when the release date changes."""
        try:
            delta = (dt.date.fromisoformat(new_date)
                     - dt.date.fromisoformat(old_date)).days
        except (TypeError, ValueError):
            # No previous date: fill blanks from the template offsets.
            offsets = {t: d for d, t in CHECKLIST_TEMPLATE}
            for r in self.conn.execute(
                    "SELECT id, task FROM checklist WHERE release_id = ? "
                    "AND due_date = ''", (release_id,)).fetchall():
                if r["task"] in offsets:
                    self.conn.execute(
                        "UPDATE checklist SET due_date = ? WHERE id = ?",
                        (_shift(new_date, offsets[r["task"]]), r["id"]))
            return
        for r in self.conn.execute(
                "SELECT id, due_date FROM checklist WHERE release_id = ? "
                "AND done = 0 AND due_date != ''", (release_id,)).fetchall():
            self.conn.execute("UPDATE checklist SET due_date = ? WHERE id = ?",
                              (_shift(r["due_date"], delta), r["id"]))

    # ---- summaries -----------------------------------------------------
    def dashboard(self, today=None):
        today = today or dt.date.today().isoformat()
        week = _shift(today, 7)
        q = self.conn.execute
        with self.lock:
            releases = [dict(r) for r in q(
                "SELECT r.*, "
                " (SELECT COUNT(*) FROM checklist c WHERE c.release_id=r.id) AS total,"
                " (SELECT COUNT(*) FROM checklist c WHERE c.release_id=r.id AND done=1) AS done "
                "FROM releases r WHERE r.status != 'Released' "
                "OR r.release_date >= ? ORDER BY "
                "CASE WHEN release_date='' THEN 1 ELSE 0 END, release_date",
                (_shift(today, -14),))]
            tasks = [dict(r) for r in q(
                "SELECT c.*, r.title AS release_title FROM checklist c "
                "JOIN releases r ON r.id = c.release_id "
                "WHERE c.done = 0 AND c.due_date != '' AND c.due_date <= ? "
                "ORDER BY c.due_date LIMIT 30", (week,))]
            follow_ups = [dict(r) for r in q(
                "SELECT p.*, r.title AS release_title FROM promos p "
                "LEFT JOIN releases r ON r.id = p.release_id "
                "WHERE p.follow_up != '' AND p.follow_up <= ? AND p.status IN "
                "('To pitch','Pitched','Followed up') ORDER BY p.follow_up",
                (week,))]
            splits = [dict(r) for r in q(
                "SELECT s.id, s.title, COUNT(sp.id) AS n, "
                " COALESCE(SUM(sp.writer_pct),0) AS writer_total, "
                " COALESCE(SUM(sp.signed),0) AS signed "
                "FROM songs s LEFT JOIN splits sp ON sp.song_id = s.id "
                "GROUP BY s.id HAVING COUNT(sp.id) = 0 "
                "OR ABS(COALESCE(SUM(sp.writer_pct),0) - 100) > 0.01 "
                "OR COALESCE(SUM(sp.signed),0) < COUNT(sp.id) ORDER BY s.title")]
            bmi = [dict(r) for r in q(
                "SELECT id, title, bmi_status FROM songs "
                "WHERE bmi_status != 'Registered' ORDER BY "
                "CASE bmi_status WHEN 'Submitted' THEN 1 ELSE 0 END, title")]
        return {"today": today, "releases": releases, "tasks": tasks,
                "bmi_todo": bmi,
                "follow_ups": follow_ups, "split_issues": splits}

    # ---- backup --------------------------------------------------------
    def export_all(self):
        data = {"app": "indie-admin-lite", "version": 1,
                "exported": dt.datetime.now().isoformat(timespec="seconds")}
        with self.lock:
            for t in TABLES:
                data[t] = [dict(r) for r in
                           self.conn.execute(f"SELECT * FROM {t} ORDER BY id")]
        return data

    def import_all(self, data):
        if not isinstance(data, dict) or data.get("app") != "indie-admin-lite":
            raise ValueError("Not an Indie Admin Lite backup file")
        # Parents before children so foreign keys resolve.
        order = ["collaborators", "releases", "songs", "contact_log",
                 "checklist", "splits", "promos"]
        with self.lock:
            try:
                self.conn.execute("PRAGMA foreign_keys = OFF")
                for t in reversed(order):
                    self.conn.execute(f"DELETE FROM {t}")
                for t in order:
                    for row in data.get(t, []):
                        cols = ["id"] + [c for c in TABLES[t] if c in row]
                        self.conn.execute(
                            f"INSERT INTO {t} ({', '.join(cols)}) VALUES "
                            f"({', '.join('?' for _ in cols)})",
                            [row.get(c) for c in cols])
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self.conn.execute("PRAGMA foreign_keys = ON")


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)
