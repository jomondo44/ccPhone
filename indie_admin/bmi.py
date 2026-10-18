"""BMI helpers: import the "CSV Full Catalog" export, and build the copy sheet
that mirrors BMI's 5-step New Work form. BMI has no public API, so nothing
here talks to BMI; the user downloads and pastes."""

import csv
import datetime as dt
import io
import re


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


# Header keywords -> our field. First matching rule wins per column.
HEADER_RULES = [
    ("work_no", lambda h: "work" in h and any(k in h for k in ("#", "no", "num", "id"))
     and "title" not in h),
    ("iswc", lambda h: "iswc" in h),
    ("title", lambda h: "title" in h and "alt" not in h),
    ("ipi", lambda h: "ipi" in h or "cae" in h or "ip name" in h),
    ("share", lambda h: "share" in h or h.endswith("%") or "percent" in h),
    ("role", lambda h: "role" in h or "capacity" in h or "designation" in h),
    ("affiliation", lambda h: "affiliation" in h or h in ("pro", "society")),
    ("writer", lambda h: ("writer" in h or "name" in h or "interested party" in h)
     and "title" not in h),
    ("origin", lambda h: "origin" in h or "status" in h),
]


def map_headers(headers):
    mapping = {}
    for i, raw in enumerate(headers):
        h = str(raw or "").strip().lower()
        for field, test in HEADER_RULES:
            if field not in mapping and test(h):
                mapping[field] = i
                break
    return mapping


def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def parse_catalog(text):
    """Parse BMI's catalog CSV into works:
    [{title, work_no, iswc, writers:[{name, ipi, share, role}]}].
    Handles one row per work or one row per writer (rows grouped by work #)."""
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    # The header is the first row that names a title column.
    start = next((i for i, r in enumerate(rows[:15])
                  if "title" in map_headers(r)), None)
    if start is None:
        raise ValueError("Couldn't find a 'Title' column. Is this BMI's "
                         "'CSV Full Catalog' download?")
    cols = map_headers(rows[start])
    get = lambda r, k: (r[cols[k]].strip() if k in cols and cols[k] < len(r) else "")

    works, order = {}, []
    last_key = None
    for r in rows[start + 1:]:
        title, no = get(r, "title"), get(r, "work_no")
        # Writer-only continuation rows leave title / work # blank.
        key = no or (_norm(title) if title else last_key)
        if not key:
            continue
        last_key = key
        w = works.get(key)
        if w is None:
            w = works[key] = {"title": title, "work_no": no, "iswc": "",
                              "writers": []}
            order.append(key)
        w["title"] = w["title"] or title
        w["iswc"] = w["iswc"] or get(r, "iswc")
        name = get(r, "writer")
        if name and _norm(name) != _norm(title):
            w["writers"].append({"name": name, "ipi": get(r, "ipi"),
                                 "share": _num(get(r, "share")),
                                 "role": get(r, "role"),
                                 "pro": get(r, "affiliation")})
    return [works[k] for k in order], sorted(cols)


def import_catalog(store, text, apply=False):
    """Match BMI works to songs (by BMI work # then title). With apply=False
    nothing is written and the plan is returned for preview."""
    works, cols = parse_catalog(text)
    songs = store.list("songs")
    by_no = {s["bmi_work_no"]: s for s in songs if s.get("bmi_work_no")}
    by_title = {_norm(s["title"]): s for s in songs}
    today = dt.date.today().isoformat()
    plan = []
    for w in works:
        song = by_no.get(w["work_no"]) or by_title.get(_norm(w["title"]))
        if song and song.get("bmi_status") == "Registered" \
                and song.get("bmi_work_no") == w["work_no"]:
            action = "up to date"
        else:
            action = "update" if song else "add"
        plan.append({"title": w["title"], "work_no": w["work_no"],
                     "writers": len(w["writers"]), "action": action,
                     "song_id": song["id"] if song else None})
        if not apply or action == "up to date":
            continue
        fields = {"bmi_status": "Registered", "bmi_work_no": w["work_no"]}
        if w["iswc"]:
            fields["iswc"] = w["iswc"]
        if song:
            if not song.get("bmi_date"):
                fields["bmi_date"] = today
            store.update("songs", song["id"], fields)
            sid = song["id"]
        else:
            fields.update(title=w["title"].title(), bmi_date="")
            sid = store.create("songs", fields)["id"]
        if w["writers"] and not store.list("splits", {"song_id": sid}):
            _add_writers(store, sid, w["writers"])
    return {"columns": cols, "works": len(works), "plan": plan,
            "add": sum(p["action"] == "add" for p in plan),
            "update": sum(p["action"] == "update" for p in plan),
            "same": sum(p["action"] == "up to date" for p in plan)}


def _add_writers(store, song_id, writers):
    total = sum(w["share"] or 0 for w in writers)
    # BMI counts writer shares out of 200% when there's no publisher.
    factor = 0.5 if total > 100.5 else 1
    for w in writers:
        store.create("splits", {
            "song_id": song_id, "name": _display_name(w["name"]),
            "role": "Songwriter", "ipi": w["ipi"], "pro": w["pro"] or "BMI",
            "writer_pct": round((w["share"] or 0) * factor, 2)})


def _display_name(name):
    """BMI lists 'ROBERTS JAMES WALLACE MR' (last name first)."""
    parts = [p for p in name.replace(",", " ").split() if p.upper() not in
             ("MR", "MRS", "MS", "DR", "JR", "SR")]
    if len(parts) >= 2 and name.isupper():
        parts = parts[1:] + parts[:1]
    return " ".join(p.capitalize() for p in parts) or name


ROLE_MAP = {
    "Songwriter": "Composer/Author", "Co-writer": "Composer/Author",
    "Artist": "Composer/Author", "Featured artist": "Composer/Author",
    "Producer": "Composer", "Musician": "Composer",
}


def copy_sheet(store, song_id):
    """Everything BMI's New Work form asks, in its order, plus problems."""
    song = store.get("songs", song_id)
    if not song:
        return None
    rel = store.get("releases", song["release_id"]) if song["release_id"] else None
    splits = store.list("splits", {"song_id": song_id})
    has_pub = any((s["publisher"] or "").strip() and (s["pub_pct"] or 0) > 0
                  for s in splits)
    problems = []
    writer_total = sum(s["writer_pct"] or 0 for s in splits)
    if not splits:
        problems.append("No writers on the split sheet yet.")
    elif abs(writer_total - 100) > 0.01:
        problems.append(f"Writer shares total {writer_total:g}%, not 100%.")
    writers = []
    for s in splits:
        last, first = _split_name(s["name"])
        share = (s["writer_pct"] or 0) * (1 if has_pub else 2)
        if not s["ipi"]:
            problems.append(f"{s['name']}: no IPI # (BMI can still register, "
                            "but royalties match more reliably with it).")
        if not s["pro"] or s["pro"] in ("None", ""):
            problems.append(f"{s['name']}: no PRO affiliation set.")
        writers.append({
            "name": s["name"], "last": last, "first": first,
            "role": ROLE_MAP.get(s["role"], "Composer/Author"),
            "ipi": s["ipi"], "pro": s["pro"] or "", "share": round(share, 2),
            "publisher": s["publisher"] if has_pub else "",
            "pub_share": s["pub_pct"] if has_pub else 0})
    steps = [
        {"step": "1 of 5 · Work info", "fields": [
            ["Type of work", song["genre_type"] or "All Other Genres"],
            ["Work Title", song["title"]],
            ["Duration", song["duration"] or "(optional)"],
            ["Work Content", song["work_content"] or "Music and Lyrics"],
            ["Language", song["language"] or "English"],
            ["Alternate titles", song["alt_titles"] or "(none)"]]},
        {"step": "2 of 5 · Other works", "fields": [
            ["Public domain arrangement / translation?", "No"],
            ["Contains samples or medleys?", "Yes" if song["has_samples"] else "No"]]},
        {"step": "3 of 5 · Writers" + (" & publishers" if has_pub else ""),
         "note": ("No publisher: BMI wants writer shares to total 200%."
                  if not has_pub else "With publishers, writer shares total 100%."),
         "writers": writers},
        {"step": "4 of 5 · Artists & recordings", "fields": [
            ["Any artists?", "Yes" if rel and rel["artist"] else "No"],
            ["Artist", rel["artist"] if rel else ""],
            ["Any recordings?", "Yes" if song["isrc"] or rel else "No"],
            ["Recording / ISRC", song["isrc"] or "(none yet)"],
            ["Created for Film, TV, Theater or Music Library?", "No"]]},
        {"step": "5 of 5 · Review & submit", "fields": [
            ["After submitting", "Tap 'Mark submitted' below. When it shows up "
             "in your BMI Works Catalog, re-import the CSV to mark it registered."]]},
    ]
    return {"song": song, "steps": steps, "problems": problems,
            "has_publisher": has_pub}


def _split_name(name):
    parts = (name or "").split()
    if len(parts) < 2:
        return name or "", ""
    return parts[-1], " ".join(parts[:-1])
