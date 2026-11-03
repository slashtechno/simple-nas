#!/usr/bin/env python3
"""Read or write Dockge's disableAuth setting, which switches Dockge's own login off.

Dockge reads the setting from the `setting` table of <data dir>/dockge.db on every connection: the
value is JSON-encoded and its type is 'general' (the settings page only rewrites rows of that type).
Dockge keeps the database in WAL mode while it runs, so a write from outside the container is lost
when the running process checkpoints: write only while the container is stopped. Reading is safe
either way.

    disable-auth.py <dockge.db> get          prints no-db, no-user, unset, true or false
    disable-auth.py <dockge.db> set <bool>   writes 'true' or 'false'

Run it as root: Dockge's image has no USER line, so the database belongs to root.
"""
import json
import os
import sqlite3
import sys


def read(conn):
    """Print what the setting currently is, or why it cannot be read."""
    try:
        if conn.execute('SELECT count(*) FROM "user"').fetchone()[0] == 0:
            print("no-user")
            return
        row = conn.execute("SELECT value FROM setting WHERE key = 'disableAuth'").fetchone()
    except sqlite3.OperationalError:   # the container has not created its tables yet
        print("no-db")
        return
    if not row:
        print("unset")
        return
    print("true" if json.loads(row[0]) else "false")


def write(conn, value):
    """Store the value as Dockge does: JSON text, type 'general'."""
    with conn:
        conn.execute(
            "INSERT INTO setting (key, value, type) VALUES ('disableAuth', ?, 'general')"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, type = excluded.type",
            (json.dumps(value == "true"),),
        )


def main():
    db, action = sys.argv[1], sys.argv[2]
    if not os.path.exists(db):
        print("no-db")
        return
    conn = sqlite3.connect(db)
    try:
        if action == "get":
            read(conn)
        else:
            write(conn, sys.argv[3])
    finally:
        conn.close()


main()
