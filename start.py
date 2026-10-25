# One starting point: open the dashboard or refresh the static reports.
from pathlib import Path
import argparse
import subprocess
import sys
from sleep_records import load_records, save_records

ROOT = Path(__file__).resolve().parent


def ensure_database():
    # Seed only a missing database. Restarting must never replace a user's edits.
    database = ROOT / "output/sleep_diary.sqlite"
    if not database.exists():
        save_records(load_records(ROOT / "data/sleep_diary.csv"), database)
        print("Created a local database with generated example nights from the supplied CSV.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", action="store_true", help="Rebuild reports from stored entries, then exit")
    args = parser.parse_args()
    ensure_database()
    if args.reports:
        # Reuse the current Python interpreter so the same installed packages are used.
        subprocess.run([sys.executable, str(ROOT / "sleep_records.py"), "--stored",
                        "--label", "Sleep diary | stored records"], check=True)
        subprocess.run([sys.executable, str(ROOT / "compare_periods.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "export_trends.py")], check=True)
        subprocess.run([sys.executable, str(ROOT / "regression.py")], check=True)
    else:
        from dashboard import app
        print("Open http://127.0.0.1:8050 in your browser. Ctrl+C stops the app.")
        app.run(debug=False, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
