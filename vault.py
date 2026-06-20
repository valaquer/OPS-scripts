#!/usr/bin/env python3
"""Encrypted vault — SQLCipher-backed secure storage for confidential teammate data."""

import argparse
import json
import os
import subprocess
import sys

SQLCIPHER = "/opt/homebrew/bin/sqlcipher"
KEYCHAIN_SERVICE_PREFIX = "vault-"


def _get_key(teammate):
    """Retrieve vault key from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", f"{KEYCHAIN_SERVICE_PREFIX}{teammate}", "-w"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def _set_key(teammate, key):
    """Store vault key in macOS Keychain."""
    subprocess.run(
        ["security", "add-generic-password", "-s", f"{KEYCHAIN_SERVICE_PREFIX}{teammate}",
         "-a", teammate, "-w", key, "-U"],
        check=True, capture_output=True
    )


def _generate_key():
    """Generate a 64-char hex key (32 bytes)."""
    return os.urandom(32).hex()


def _run_sql(db_path, key, sql, expect_output=False):
    """Run SQL against an encrypted SQLCipher database."""
    commands = f"PRAGMA key = \"x'{key}'\";\n.headers off\n{sql}"
    result = subprocess.run(
        [SQLCIPHER, db_path],
        input=commands, capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0 and result.stderr.strip():
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    output = result.stdout.strip()
    # PRAGMA key echoes "ok" — strip it
    if output.startswith("ok\n"):
        output = output[3:].strip()
    elif output == "ok":
        output = ""
    return output


def _teammate_from_path(db_path):
    """Extract teammate name from vault path like 'felix/vault.db'."""
    parts = os.path.normpath(db_path).split(os.sep)
    for i, part in enumerate(parts):
        if part == "honeybloom" and i + 1 < len(parts):
            return parts[i + 1]
    return os.path.basename(os.path.dirname(os.path.abspath(db_path)))


def cmd_init(args):
    """Create a new encrypted vault."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)

    if os.path.exists(db_path):
        print(f"Vault already exists at {db_path}")
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    key = _generate_key()
    _set_key(teammate, key)

    _run_sql(db_path, key, """
CREATE TABLE _meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
INSERT INTO _meta (key, value) VALUES ('version', '1');
INSERT INTO _meta (key, value) VALUES ('owner', '""" + teammate + """');
""")

    print(f"Vault created at {db_path}")
    print(f"Key stored in Keychain under '{KEYCHAIN_SERVICE_PREFIX}{teammate}'")


def cmd_create_table(args):
    """Create a new table with custom columns."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    table = args.table
    columns = args.columns  # e.g. "date TEXT, kg REAL, notes TEXT"

    sql = f"CREATE TABLE IF NOT EXISTS [{table}] (id INTEGER PRIMARY KEY AUTOINCREMENT, {columns}, updated_at TEXT DEFAULT (datetime('now')));"
    _run_sql(db_path, key, sql)
    print(f"Table '{table}' created.")


def cmd_put(args):
    """Insert or update a record."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    table = args.table
    data = json.loads(args.data)  # e.g. '{"date": "2026-06-11", "kg": 89.1, "notes": "comfort ate"}'

    cols = ", ".join(f"[{k}]" for k in data.keys())
    vals = ", ".join(f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" for v in data.values())

    sql = f"INSERT INTO [{table}] ({cols}) VALUES ({vals});"
    _run_sql(db_path, key, sql)
    print(f"Record added to '{table}'.")


def cmd_get(args):
    """Look up records by column value."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    table = args.table
    sql = f".mode json\nSELECT * FROM [{table}]"

    if args.where:
        col, val = args.where.split("=", 1)
        val = val.replace("'", "''")
        sql += f" WHERE [{col.strip()}] = '{val.strip()}'"

    sql += " ORDER BY id;"
    output = _run_sql(db_path, key, sql, expect_output=True)
    if output:
        rows = json.loads(output)
        for row in rows:
            row.pop("updated_at", None)
            for k, v in row.items():
                print(f"  {k}: {v}")
            print()
    else:
        print("No records found.")


def cmd_dump(args):
    """Dump all records from a table."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    sql = f".mode json\nSELECT * FROM [{args.table}] ORDER BY id;"
    output = _run_sql(db_path, key, sql, expect_output=True)
    if output:
        rows = json.loads(output)
        for row in rows:
            row.pop("updated_at", None)
            for k, v in row.items():
                print(f"  {k}: {v}")
            print()
    else:
        print(f"Table '{args.table}' is empty.")


def cmd_delete(args):
    """Delete a record by id."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    sql = f"DELETE FROM [{args.table}] WHERE id = {args.id};"
    _run_sql(db_path, key, sql)
    print(f"Record {args.id} deleted from '{args.table}'.")


def cmd_update(args):
    """Update a record by id."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    data = json.loads(args.data)
    sets = ", ".join(f"[{k}] = '{str(v).replace(chr(39), chr(39)+chr(39))}'" for k, v in data.items())
    sql = f"UPDATE [{args.table}] SET {sets}, updated_at = datetime('now') WHERE id = {args.id};"
    _run_sql(db_path, key, sql)
    print(f"Record {args.id} updated in '{args.table}'.")


def cmd_tables(args):
    """List all tables in the vault."""
    db_path = args.path
    teammate = _teammate_from_path(db_path)
    key = _get_key(teammate)
    if not key:
        print(f"No Keychain key found for '{KEYCHAIN_SERVICE_PREFIX}{teammate}'", file=sys.stderr)
        sys.exit(1)

    sql = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_meta' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    output = _run_sql(db_path, key, sql, expect_output=True)
    if output:
        for line in output.strip().split("\n"):
            print(f"  {line}")
    else:
        print("No tables.")


def main():
    parser = argparse.ArgumentParser(description="Encrypted vault — SQLCipher-backed secure storage")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new encrypted vault")
    p_init.add_argument("path", help="Path to vault.db")

    p_ct = sub.add_parser("create-table", help="Create a table with custom columns")
    p_ct.add_argument("path", help="Path to vault.db")
    p_ct.add_argument("table", help="Table name")
    p_ct.add_argument("columns", help='Column definitions, e.g. "date TEXT, kg REAL, notes TEXT"')

    p_put = sub.add_parser("put", help="Insert a record")
    p_put.add_argument("path", help="Path to vault.db")
    p_put.add_argument("table", help="Table name")
    p_put.add_argument("data", help='JSON object, e.g. \'{"date": "2026-06-11", "kg": 89.1}\'')

    p_get = sub.add_parser("get", help="Look up records")
    p_get.add_argument("path", help="Path to vault.db")
    p_get.add_argument("table", help="Table name")
    p_get.add_argument("--where", help='Filter, e.g. "category=banking"')

    p_dump = sub.add_parser("dump", help="Dump all records from a table")
    p_dump.add_argument("path", help="Path to vault.db")
    p_dump.add_argument("table", help="Table name")

    p_update = sub.add_parser("update", help="Update a record by id")
    p_update.add_argument("path", help="Path to vault.db")
    p_update.add_argument("table", help="Table name")
    p_update.add_argument("id", type=int, help="Record id")
    p_update.add_argument("data", help='JSON object with fields to update')

    p_del = sub.add_parser("delete", help="Delete a record by id")
    p_del.add_argument("path", help="Path to vault.db")
    p_del.add_argument("table", help="Table name")
    p_del.add_argument("id", type=int, help="Record id")

    p_tables = sub.add_parser("tables", help="List all tables")
    p_tables.add_argument("path", help="Path to vault.db")

    args = parser.parse_args()
    cmds = {
        "init": cmd_init,
        "create-table": cmd_create_table,
        "put": cmd_put,
        "get": cmd_get,
        "dump": cmd_dump,
        "update": cmd_update,
        "delete": cmd_delete,
        "tables": cmd_tables,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
