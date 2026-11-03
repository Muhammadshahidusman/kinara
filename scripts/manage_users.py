"""Create or update Kinara logins (stored as argon2 hashes in the active store).

Run:  uv run python scripts/manage_users.py add shahid --role admin --name "Muhammad Shahid Usman"
      uv run python scripts/manage_users.py add ac_ravi --role field_officer
      uv run python scripts/manage_users.py disable ac_ravi
      uv run python scripts/manage_users.py list
The password is asked for interactively (or read from KINARA_NEW_PASSWORD for automation).
Uses PostGIS when DATABASE_URL is set, otherwise data/processed/users.json.
"""

from __future__ import annotations

import argparse
import getpass
import os

from kinara.api.auth import hash_password
from kinara.api.store import ROLES, open_store

MIN_PASSWORD = 8


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="create a user or reset their password / role")
    add.add_argument("username")
    add.add_argument("--role", choices=ROLES, required=True)
    add.add_argument("--name", default="")
    dis = sub.add_parser("disable", help="block a user from signing in (history is kept)")
    dis.add_argument("username")
    sub.add_parser("list")
    a = ap.parse_args()

    store = open_store()
    if a.cmd == "list":
        for u in store.users():
            print(f"{u['username']:20s} {u['role']:14s} {'active' if u['active'] else 'disabled':9s} {u['full_name']}")
        return
    if a.cmd == "disable":
        u = store.user(a.username)
        if not u:
            raise SystemExit(f"no user {a.username}")
        store.put_user(a.username, u["password_hash"], u["role"], u.get("full_name", ""), active=False)
        print(f"disabled {a.username}")
        return
    pw = os.getenv("KINARA_NEW_PASSWORD") or getpass.getpass(f"password for {a.username}: ")
    if len(pw) < MIN_PASSWORD:
        raise SystemExit(f"password must be at least {MIN_PASSWORD} characters")
    if not os.getenv("KINARA_NEW_PASSWORD") and getpass.getpass("again: ") != pw:
        raise SystemExit("passwords differ")
    store.put_user(a.username, hash_password(pw), a.role, a.name)
    print(f"saved {a.username} ({a.role}) in the {store.name} store")


if __name__ == "__main__":
    main()
