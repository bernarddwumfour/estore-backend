"""Run a Django management command using one store's environment."""
import os
import runpy
import sys
from pathlib import Path

STORES = {
    "iplug": ".env.iplug",
    "oak": ".env.oakandloom",
    "oakandloom": ".env.oakandloom",
    "tyrepapa": ".env.tyrepapa",
}

if len(sys.argv) < 3 or sys.argv[1] not in STORES:
    raise SystemExit(
        "Usage: venv/bin/python manage_store.py {iplug|oak|tyrepapa} "
        "<django command> [arguments]"
    )

os.environ["ESTORE_ENV_FILE"] = STORES[sys.argv[1]]
sys.argv = [str(Path(__file__).with_name("manage.py")), *sys.argv[2:]]
runpy.run_path(sys.argv[0], run_name="__main__")
