"""Backups: snapshot, test, copy, prune, record.

Every run:
  1. snapshots the database through SQLite's online backup API (never the
     live file) and zips it with every document and profile picture, plus a
     manifest (row counts, the files expected);
  2. restore-tests the zip when Settings → Backups asks for it: opens it,
     runs PRAGMA integrity_check on the database inside and checks every
     document the database names is in the archive;
  3. copies it to each destination switched on in Settings → Backups —
     OneDrive, a SharePoint site folder, a mounted network share;
  4. prunes by daily / weekly / monthly retention, locally and at each
     destination (the updater's pre-update copies, odin-preupdate-*, are
     kept apart: the newest keep_pre_update of them);
  5. records the run in backup_runs (shown on the Backups settings page).

The zip is written as .partial-<name> and renamed once complete, so a run
killed mid-write (a container recreated) never leaves a truncated archive for
retention to keep; the next run removes the leftover. A local copy is always
written: a backup that only exists when a cloud integration happens to be
configured is not a backup. Restore procedure:
docs/RUNBOOK.md, "Restore a backup".

Runs from the scheduler (scheduler.py, at the time set in Settings), from
"Back up now", or by hand: python backup.py
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

import db as _db
import graph

NAME_PREFIX, NAME_SUFFIX = "odin-backup-", ".zip"
# The updater's backup before each update (backup.py --local): a name of its
# own, so a later backup the same day never prunes the pre-migration copy; the
# newest keep_pre_update of them are kept apart from the daily/weekly/monthly set.
PRE_UPDATE_PREFIX, PRE_UPDATE_TRIGGER = "odin-preupdate-", "before update"
PARTIAL = ".partial-"   # an archive still being written: renamed to its real name once complete


def _backup_dir():
    """DATA_DIR/backups, owner only: an archive holds the whole database."""
    path = os.path.join(_db.DATA_DIR, "backups")
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)   # a folder made before this rule, too
    return path


def _stamp(name):
    """The UTC time in a backup's file name, or None for anything else."""
    if not (name.startswith(NAME_PREFIX) and name.endswith(NAME_SUFFIX)):
        return None
    try:
        return datetime.strptime(name[len(NAME_PREFIX):-len(NAME_SUFFIX)], "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def retention_keep(names, daily, weekly, monthly):
    """Which backup files to keep: the newest of each of the last `daily`
    days, `weekly` ISO weeks and `monthly` months (grandfather-father-son),
    and always the newest of all. Files that aren't backups are never touched
    (they are returned as kept)."""
    dated = sorted(((_stamp(n), n) for n in names if _stamp(n)), reverse=True)
    keep = {n for n in names if not _stamp(n)}
    if dated:
        keep.add(dated[0][1])
    for count, key in ((daily, lambda d: d.date()), (weekly, lambda d: d.isocalendar()[:2]), (monthly, lambda d: (d.year, d.month))):
        seen = []
        for stamp, name in dated:
            k = key(stamp)
            if k not in seen:
                if len(seen) >= count:
                    break
                seen.append(k)
                keep.add(name)
    return keep


def _snapshot(tmp):
    snapshot = os.path.join(tmp, "odin.db")
    source, target = sqlite3.connect(_db.DB_PATH), sqlite3.connect(snapshot)
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()
    return snapshot


def _manifest(snapshot):
    con = sqlite3.connect(snapshot)
    try:
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("projects", "users", "documents", "tasks", "status_notes", "audit_logs")}
    finally:
        con.close()
    return {"created_at": datetime.utcnow().isoformat(), "counts": counts, "documents": _document_paths(snapshot)}


def _document_paths(db_file):
    """Where each document the database names must sit inside the archive."""
    con = sqlite3.connect(db_file)
    try:
        return [f"uploads/{pid}/{name}" for pid, name in con.execute("SELECT project_id, stored_name FROM documents WHERE stored_name IS NOT NULL")]
    finally:
        con.close()


def restore_test(zip_path):
    """(ok, detail): does this archive restore? Integrity-check the database
    inside and list any document it names that is not in the archive (a
    warning: the backup is still good)."""
    try:
        with zipfile.ZipFile(zip_path) as zf, tempfile.TemporaryDirectory() as tmp:
            bad = zf.testzip()
            if bad:
                return False, f"corrupt entry {bad}"
            zf.extract("odin.db", tmp)
            restored = os.path.join(tmp, "odin.db")
            con = sqlite3.connect(restored)
            try:
                integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
                projects = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            finally:
                con.close()
            stored = _document_paths(restored)
            names = set(zf.namelist())
            missing = [s for s in stored if s not in names]
            if integrity != "ok":
                return False, f"database integrity check: {integrity[:120]}"
            if missing:   # a warning, not a failure: the copy restores; one lost file must not stop pruning or the updater
                return True, f"database intact, {projects} projects; WARNING: {len(missing)} of {len(stored)} documents have no file on the server: {', '.join(missing[:3])}{' ...' if len(missing) > 3 else ''}"
            return True, f"database intact, {projects} projects, all {len(stored)} documents present"
    except Exception as exc:  # noqa: BLE001 — any failure to open is a failed restore
        return False, f"could not open the archive: {exc}"


def _prune_local(keep_args, keep_pre_update):
    names = os.listdir(_backup_dir())
    keep = retention_keep(names, *keep_args)
    pre = sorted((n for n in names if n.startswith(PRE_UPDATE_PREFIX) and n.endswith(NAME_SUFFIX)), reverse=True)
    keep -= set(pre[keep_pre_update:])   # the stamp sorts by name: the newest first
    for name in names:
        if name not in keep:
            os.remove(os.path.join(_backup_dir(), name))


def _copy_share(zip_path, folder, keep_args, prune=True):
    if not folder or not os.path.isabs(folder):
        return False, "no share folder set"
    if not os.path.isdir(folder):
        return False, f"{folder} is not mounted"
    final = os.path.join(folder, os.path.basename(zip_path))
    partial = os.path.join(folder, ".partial-" + os.path.basename(zip_path))
    try:   # copy under a temporary name: a full share must not leave a half archive passing for that day's copy
        shutil.copy2(zip_path, partial)
        os.replace(partial, final)
    except OSError as exc:
        try:
            os.remove(partial)
        except OSError:
            pass
        return False, str(exc)
    names = os.listdir(folder)
    for name in (set(names) - retention_keep(names, *keep_args)) if prune else ():
        os.remove(os.path.join(folder, name))
    return True, None


def _copy_graph(zip_path, folder, drive, keep_args, prune=True):
    ok, error = graph.upload_file(zip_path, f"{folder}/{os.path.basename(zip_path)}", drive=drive)
    if not ok or not prune:
        return ok, error
    items, error = graph.list_folder(folder, drive=drive)
    keep = retention_keep([n for n, _ in items], *keep_args)
    for name, item_id in items:
        if name not in keep:
            graph.delete_item(item_id, drive=drive)
    return True, None


def run_backup(trigger="manual", actor=None, local_only=False):
    """Make, test, copy and prune one backup; record it. Returns (ok, message).
    Works without an app context (the scheduler and cron call it). One run at
    a time across processes (a double-click on Back up now, the scheduler and
    the updater); `local_only` skips the off-server copies (the updater's
    pre-update backup, which may run where no share is mounted)."""
    import fcntl
    with open(os.path.join(_backup_dir(), ".lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False, "another backup is running; try again in a minute"
        return _run_backup(trigger, actor, local_only)


def _destination(name, copy):
    """One off-server copy; a failure (even an exception) is that destination's, never the run's."""
    try:
        return (name, *copy())
    except Exception as exc:  # noqa: BLE001
        return name, False, str(exc)


def _room(con):
    """Refuse (RuntimeError) when the backup disk has less free than the policy
    backup_min_free_mb (0: twice the last archive, 1,024 MB before the first),
    and tell the admins once a day: a backup must not fill the database's disk."""
    from policies import policy
    need = policy("backup_min_free_mb", con)
    if not need:
        last = con.execute("SELECT size_bytes FROM backup_runs WHERE size_bytes IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        need = max(1, 2 * last[0] // 2**20) if last else 1024
    free = shutil.disk_usage(_backup_dir()).free // 2**20
    if free < need:
        why = f"only {free:,} MB free on the backup disk, and a backup needs {need:,} MB (Settings > Backups > Disk space)"
        from scheduler import _tell_admins_once_a_day
        _tell_admins_once_a_day("backup_no_room", "Odin skipped a backup: the disk is too full",
                                f"The backup was not made: {why}. Free space on the server or keep fewer copies (Settings > Backups > Copies kept); "
                                "see docs/RUNBOOK.md, \"Disk full\".", "/settings/backups")
        raise RuntimeError(why)


def _run_backup(trigger, actor, local_only):
    from policies import policy
    con = sqlite3.connect(_db.DB_PATH)
    con.row_factory = sqlite3.Row
    p = {k: policy(k, con) for k in ("keep_daily", "keep_weekly", "keep_monthly", "keep_pre_update", "restore_test", "dest_onedrive",
                                       "dest_sharepoint", "sharepoint_site", "sharepoint_folder", "dest_share", "share_path")}
    keep_args = (p["keep_daily"], p["keep_weekly"], p["keep_monthly"])
    started = datetime.utcnow()
    prefix = PRE_UPDATE_PREFIX if trigger == PRE_UPDATE_TRIGGER else NAME_PREFIX
    zip_name = f"{prefix}{started.strftime('%Y%m%d-%H%M%S')}{NAME_SUFFIX}"
    zip_path = os.path.join(_backup_dir(), zip_name)
    partial = os.path.join(_backup_dir(), PARTIAL + zip_name)
    results, ok, restore_ok, restore_detail = [], True, None, None
    written = False   # the zip is complete: only an unfinished one is removed on failure
    try:
        for name in os.listdir(_backup_dir()):   # left by a run that was killed (a container recreated mid-backup)
            if name.startswith(PARTIAL):
                os.remove(os.path.join(_backup_dir(), name))
        _room(con)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = _snapshot(tmp)
            manifest = _manifest(snapshot)
            # created 0600 (never world-readable, whatever the umask): it carries guest tokens and every document;
            # written under a temporary name, so a run killed mid-write never leaves a truncated archive passing for that day's copy
            with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as out, \
                    zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(snapshot, arcname="odin.db")
                zf.writestr("manifest.json", json.dumps(manifest, indent=1))
                from services.retention import ARCHIVE_DIR_NAME
                for folder, label in ((_db.UPLOAD_DIR, "uploads"), (_db.AVATAR_DIR, "avatars"),
                                      (os.path.join(_db.DATA_DIR, ARCHIVE_DIR_NAME), ARCHIVE_DIR_NAME),
                                      (os.path.join(_db.DATA_DIR, "brand"), "brand")):   # document template logos
                    for root, _dirs, files in os.walk(folder):
                        for fname in files:
                            full = os.path.join(root, fname)
                            zf.write(full, arcname=os.path.join(label, os.path.relpath(full, folder)))
            os.replace(partial, zip_path)
            written = True
        if p["restore_test"]:
            restore_ok, restore_detail = restore_test(zip_path)
            ok = restore_ok
        destinations = [("local", True, None)]
        prune = restore_ok is not False   # a failed restore test must never push out older good copies, here or off the server
        def sharepoint():
            drive, error = graph.sharepoint_drive(p["sharepoint_site"]) if p["sharepoint_site"] else (None, "no SharePoint site set")
            return _copy_graph(zip_path, p["sharepoint_folder"] or "Odin-Backups", drive, keep_args, prune) if drive else (False, error)
        if p["dest_onedrive"] and not local_only:
            destinations.append(_destination("OneDrive", lambda: _copy_graph(zip_path, "Odin-Backups", "/me/drive", keep_args, prune)))
        if p["dest_sharepoint"] and not local_only:
            destinations.append(_destination("SharePoint", sharepoint))
        if p["dest_share"] and not local_only:
            destinations.append(_destination("network share", lambda: _copy_share(zip_path, p["share_path"], keep_args, prune)))
        if prune:
            _prune_local(keep_args, p["keep_pre_update"])
        for name, done, error in destinations:
            results.append(name if done else f"{name} failed: {error}")
            ok = ok and done
        size = os.path.getsize(zip_path) if os.path.exists(zip_path) else None
        message = ("; ".join(results)) + ("" if restore_ok in (None, True) else f"; restore test failed: {restore_detail}")
    except Exception as exc:  # noqa: BLE001 — the run is recorded as failed, never lost
        ok, size, message = False, None, f"backup failed: {exc}"
        if not written:
            try:   # a half-written zip must not linger
                os.remove(partial)
            except OSError:
                pass
    con.execute(
        "INSERT INTO backup_runs (started_at, finished_at, trigger, actor, file, size_bytes, ok, restore_ok, restore_detail, destinations)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (started.isoformat(), datetime.utcnow().isoformat(), trigger, actor, zip_name, size, int(ok),
         None if restore_ok is None else int(restore_ok), restore_detail, message))
    con.execute("DELETE FROM backup_runs WHERE id NOT IN (SELECT id FROM backup_runs ORDER BY id DESC LIMIT 200)")
    con.commit()
    con.close()
    return ok, message


if __name__ == "__main__":
    local = "--local" in sys.argv   # the updater: this server only
    success, msg = run_backup(trigger=PRE_UPDATE_TRIGGER if local else "command line", local_only=local)
    print(msg if success else f"Backup failed: {msg}", file=sys.stdout if success else sys.stderr)
    sys.exit(0 if success else 1)
