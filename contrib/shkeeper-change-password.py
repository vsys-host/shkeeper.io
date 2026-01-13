#!/usr/bin/python3

# Requires bcrypt module
# For Ubuntu run: apt install python3-pip -y && pip install bcrypt

import bcrypt
import sqlite3
import getpass
import os
import glob


PVC_PATH = "/var/lib/rancher/k3s/storage/pvc-d8776ce1-0073-41c6-844f-f5002dfcebc9_shkeeper_shkeeper-db-claim"

DB_PATH = f"{PVC_PATH}/shkeeper.sqlite"
SESSIONS_PATH = f"{PVC_PATH}/flask_session"

if not os.path.exists(PVC_PATH):
    raise SystemExit(
        f"Path '{PVC_PATH}' does not exist! Please set correct PVC_PATH variable in the script."
    )

changed = False
while not changed:
    try:
        pass1 = getpass.getpass(prompt="Password: ")
        pass2 = getpass.getpass(prompt="Confirm password: ")
    except KeyboardInterrupt:
        print()
        raise SystemExit()
    if pass1 and pass2 and (pass1 == pass2):
        passhash = bcrypt.hashpw(pass1.encode(), bcrypt.gensalt(rounds=10))
        db = sqlite3.connect(DB_PATH)
        with db:
            db.execute(
                'UPDATE user SET passhash = ? WHERE username = "admin"', (passhash,)
            )
        db.close()
        changed = True

        for f in glob.glob(f"{SESSIONS_PATH}/*"):
            os.remove(f)

        print("Shkeeper's password has been successfully changed!")
    else:
        print("Passwords do not match, try again.")
