"""
stamp_hashes.py

Run this script at build/release time to compute and stamp SHA-256 hashes
into all DB entries in wpi_db.json.

Usage:
    python stamp_hashes.py
    python stamp_hashes.py --db path/to/wpi_db.json
"""


import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from gui.components.utils.wpi_hash import compute_hash


def stamp(db_path: Path):
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    stamped = 0
    for entry in db.get("entries", []):
        data = entry.get("data")
        if data is None:
            print(f"  [SKIP] Entry '{entry['metadata']['id']}' has no data block.")
            continue
        h = compute_hash(data)
        entry["metadata"]["hash"] = h
        stamped += 1
        print(f"  [OK]   {entry['metadata']['id']} → {h[:32]}...")

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=True)

    print(f"\nStamped {stamped} entries into {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).parent / "wpi_db.json",
    )
    args = parser.parse_args()
    stamp(args.db)