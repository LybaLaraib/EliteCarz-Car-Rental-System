import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

# Helper script for filling missing local car images from the database.

def _db():
    import os

    uri = os.getenv("MONGO_URI")
    name = os.getenv("DB_NAME")
    if not uri or not name:
        raise RuntimeError("Missing MONGO_URI / DB_NAME in environment (.env).")
    client = MongoClient(uri, serverSelectionTimeoutMS=6000, connectTimeoutMS=6000, socketTimeoutMS=20000)
    client.admin.command("ping")
    return client[name]


def _safe_filename(s: str) -> str:
    # Car IDs become filenames under static/images/cars.
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", s)
    return s.strip("-").upper() or "CAR"


def _download(url: str, dest: Path) -> bool:
    # Tiny responses are usually placeholders or failed downloads.
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=15, allow_redirects=True, headers={"User-Agent": "EliteCarz/1.0"})
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest.stat().st_size > 10_000
    except Exception:
        return False


def main():
    out_dir = ROOT / "static" / "images" / "cars"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Connecting to MongoDB...", flush=True)
    try:
        db = _db()
    except Exception as e:
        print(f"MongoDB connection failed: {e}", flush=True)
        print("Tip: ensure internet access + Atlas IP allowlist allows your network.", flush=True)
        return
    print("Connected. Fetching cars...", flush=True)
    cars = list(db.cars.find({}).sort("_id", 1))
    if not cars:
        print("No cars found in database.")
        return
    print(f"Found {len(cars)} cars. Downloading images...", flush=True)

    updated = 0
    for car in cars:
        car_id = _safe_filename(str(car.get("_id", "")))
        brand = str(car.get("brand", "car")).strip()
        model = str(car.get("model", "vehicle")).strip()

        dest = out_dir / f"{car_id}.jpg"
        if dest.exists() and dest.stat().st_size > 10_000:
            continue

        q = ",".join([brand, model, "car"]).replace(" ", "+")
        url = f"https://loremflickr.com/1200/800/{q}"
        ok = _download(url, dest)
        if not ok:
            ok = _download("https://loremflickr.com/1200/800/car,sport", dest)

        if ok:
            updated += 1
            db.cars.update_one({"_id": car.get("_id")}, {"$set": {"image_url": f"/static/images/cars/{car_id}.jpg"}})
            print(f"Downloaded: {car_id} ({brand} {model})", flush=True)
        else:
            print(f"Failed: {car_id} ({brand} {model})", flush=True)

    print(f"Done. Downloaded/updated {updated} car images into {out_dir}.")


if __name__ == "__main__":
    main()

