# Indie Musician Admin Lite

Simple, offline admin for independent artists who are too small for full
management software but drowning in splits, collaborators, promo and release
to-dos.

- **Split sheets**: writers, roles, PRO, IPI, writer / publishing / master
  shares. Flags sheets that don't total 100% or aren't signed. One tap to split
  evenly, print / save as PDF, or share as text.
- **Collaborator log**: producers, co-writers, engineers, designers, with
  tap-to-call / text / email, PRO and IPI details, notes, a dated contact log,
  and the songs they're on.
- **Release checklist**: every new release gets a 19-step checklist (master,
  artwork, split sheet, PRO / MLC registration, distributor upload, editorial
  pitch, pre-save, lyrics, release day, SoundExchange...) dated backwards from
  the release date. Move the release date and open tasks move with it.
- **Promo tracker**: playlists, blogs, radio, podcasts, press. Status
  pipeline (To pitch, Pitched, Followed up, Accepted, Published, Declined),
  auto follow-up reminders one week after pitching, cost and win-rate totals.
- **BMI registration helper**: BMI has no public API, so the app works
  alongside its website. *Pull*: on BMI Online Services, open Works Catalog,
  tap **CSV Full Catalog**, and import that file on the Splits tab. Songs are
  matched by BMI work # or title, previewed, then marked registered. *Push*:
  each song's **BMI copy sheet** lists every field of BMI's 5-step New Work
  form in order with copy buttons (writer shares doubled to BMI's 200% rule
  when there's no publisher) and flags missing IPI numbers or bad totals
  first. MLC and SoundExchange status are tracked too.
- **Home dashboard**: what's due this week, overdue tasks, promo follow-ups
  and split sheets that need fixing.
- **Your data stays on your phone** in one SQLite file. JSON backup / restore
  and CSV export built in.

Pure Python standard library, no `pip install` needed.

## Run on Android with Termux

1. Install **Termux** from F-Droid (the Play Store build is outdated).
2. In Termux:

   ```bash
   pkg install -y python git
   git clone https://github.com/jomondo44/ccPhone.git
   cd ccPhone
   python musician_admin.py
   ```

   Your browser opens at `http://127.0.0.1:8765/`. Keep Termux running in the
   background while you use the app. Tip: in Chrome, use the menu and
   **Add to Home screen** to get an app icon for that address.

3. Optional, one-time: `bash termux/install.sh` adds a `musician-admin`
   command and a home-screen shortcut for the **Termux:Widget** add-on.

Options:

```text
python musician_admin.py --port 9000       # different port
python musician_admin.py --no-browser      # don't auto-open the browser
python musician_admin.py --db ~/band.db    # separate data file (e.g. per project)
```

Data lives in `~/.indie_admin/data.db` (override with `INDIE_ADMIN_HOME`).
Use **Home, Download backup** regularly, especially before changing phones.

It also runs the same way on Windows, macOS and Linux with Python 3.8+.

## APK (no Termux needed)

The `Build APK` GitHub Actions workflow packages the same app with Buildozer
(python-for-android `webview` bootstrap) on every push. Download the APK from
the workflow run's **Artifacts** section, copy it to your phone and install it
(allow "install unknown apps" for your browser or file manager).

To build it yourself on Linux: `pip install buildozer cython && buildozer android debug`.

APK limitation: Android's built-in WebView doesn't handle file downloads or the
file picker, so **Download backup**, **Restore backup**, CSV export and the
printable split sheet's PDF save work best in the Termux version. Everything
else works the same.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Project layout

```text
musician_admin.py        launcher (Termux / desktop)
main.py                  APK entry point
indie_admin/db.py        SQLite schema, CRUD, checklist template, dashboard, backup
indie_admin/server.py    local HTTP server, JSON API, printable split sheet, CSV
indie_admin/static/      phone UI (HTML / CSS / vanilla JS)
termux/install.sh        command + home-screen shortcut
buildozer.spec           APK build config
```
