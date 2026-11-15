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
    "oliveandaura": ".env.oliveandaura",
}
DEFAULT_BACKEND_PORTS = {
    "iplug": "8000",
    "oak": "8001",
    "oakandloom": "8001",
    "tyrepapa": "8002",
    "oliveandaura": "8003",
}

if len(sys.argv) < 3 or sys.argv[1] not in STORES:
    raise SystemExit(
        "Usage: venv/bin/python manage_store.py {iplug|oak|tyrepapa|oliveandaura} "
        "<django command> [arguments]"
    )

store = sys.argv[1]
command = sys.argv[2]
safe_without_beauty_database = {"check", "makemigrations", "help", "diffsettings", "startapp"}
if store == "oliveandaura" and command not in safe_without_beauty_database:
    env_path = Path(__file__).with_name(STORES[store])
    database_url = ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                database_url = line.partition("=")[2].strip().strip("\"'")
                break
    if not database_url:
        raise SystemExit(
            "Olive & Aura has no DATABASE_URL yet. Add its dedicated beauty database "
            "to .env.oliveandaura before running database or server commands."
        )

os.environ["ESTORE_ENV_FILE"] = STORES[store]
command_args = sys.argv[2:]
if command == "runserver" and not any(not arg.startswith("-") for arg in command_args[1:]):
    command_args.append(DEFAULT_BACKEND_PORTS[store])
sys.argv = [str(Path(__file__).with_name("manage.py")), *command_args]
runpy.run_path(sys.argv[0], run_name="__main__")
