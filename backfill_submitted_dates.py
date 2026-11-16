#!/usr/bin/env python3
"""One-time backfill of the "Submitted" date for trips that were marked
Submitted or Reimbursed before the app started recording dates.

The real dates weren't recorded, so each is estimated as one business day
(Mon-Fri) after the trip's end date. Weekends are skipped; holidays are not.
Reimbursed dates can't be estimated and are left blank. Trips that already
have a submitted date are never touched.

Shows what it would change and writes nothing unless you add --apply:

    python3 backfill_submitted_dates.py            # preview only
    python3 backfill_submitted_dates.py --apply    # back up the database, then write
"""
import datetime
import shutil
import sys

from database import DB_PATH, get_db


def next_business_day(end_date):
    d = datetime.date.fromisoformat(end_date) + datetime.timedelta(days=1)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def main():
    apply = "--apply" in sys.argv[1:]
    print(f"Database: {DB_PATH}")

    conn = get_db()
    rows = conn.execute(
        "SELECT trips.id, trips.status, trips.end_date, clients.name AS client "
        "FROM trips JOIN clients ON clients.id = trips.client_id "
        "WHERE trips.status IN ('submitted', 'reimbursed') "
        "AND (trips.submitted_at IS NULL OR trips.submitted_at = '') "
        "ORDER BY trips.end_date, trips.id"
    ).fetchall()

    changes, skipped = [], []
    for r in rows:
        try:
            changes.append((r["id"], r["client"], r["status"], r["end_date"], next_business_day(r["end_date"])))
        except (TypeError, ValueError):
            skipped.append((r["id"], r["client"], r["end_date"]))

    if not changes and not skipped:
        print("Nothing to backfill: every Submitted/Reimbursed trip already has a submitted date.")
        return

    print(f"\n{'ID':>4}  {'Status':<11} {'Ends':<11} {'Submitted (est.)':<17} Client")
    for tid, client, status, end, new in changes:
        print(f"{tid:>4}  {status:<11} {end:<11} {new:<17} {client}")
    for tid, client, end in skipped:
        print(f"{tid:>4}  skipped: no usable end date ({end!r}) -- {client}")
    print(f"\n{len(changes)} trip(s) to update, {len(skipped)} skipped.")

    if not apply:
        print("Preview only -- nothing was changed. Run again with --apply to write these dates.")
        return

    backup = DB_PATH.with_name(f"{DB_PATH.name}.bak-{datetime.date.today().isoformat()}")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(DB_PATH, backup)
    print(f"Backed up the database to {backup}")

    conn.executemany(
        "UPDATE trips SET submitted_at = ? WHERE id = ? AND (submitted_at IS NULL OR submitted_at = '')",
        [(new, tid) for tid, _, _, _, new in changes],
    )
    conn.commit()
    print(f"Done: updated {len(changes)} trip(s).")


if __name__ == "__main__":
    main()
