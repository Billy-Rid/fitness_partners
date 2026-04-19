"""
Nashville Fitness Partner Research Tool
=======================================
Finds every fitness studio, gym, and membership group in Nashville
and looks up the owner(s) via the TN Secretary of State registry.

Output: data/fitness_partners.csv

Usage:
    python main.py              # full run
    python main.py --fast       # skip per-studio detail pages
    python main.py --skip-sos   # skip owner lookup (just get studio list)
    python main.py --debug      # show browser window for inspection
"""

import asyncio
import sys
from pathlib import Path

import pandas as pd

from scrapers.google_maps_scraper import run_fitness_scraper
from scrapers.tn_sos import enrich_with_owners

OUTPUT_DIR = Path("data")
OUTPUT_FILE = OUTPUT_DIR / "fitness_partners.csv"

COLUMN_ORDER = [
    "name",
    "owner_names",
    "email",
    "phone",
    "address",
    "category",
    "website",
    "rating",
    "review_count",
    "entity_type",
    "sos_status",
    "date_formed",
    "registered_name",
    "google_maps_url",
]


def _reorder(df: pd.DataFrame) -> pd.DataFrame:
    existing = [c for c in COLUMN_ORDER if c in df.columns]
    extras = [c for c in df.columns if c not in COLUMN_ORDER]
    return df[existing + extras]


def run(skip_details: bool = False, skip_sos: bool = False, debug: bool = False) -> pd.DataFrame:
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("\n=== Nashville Fitness Partner Research Tool ===\n")

    # ── Step 1: Google Maps scraping ──────────────────────────────────────────
    print("[1/2] Scraping Google Maps for Nashville fitness studios...")
    if debug:
        print("      [debug: browser will be visible]\n")

    studios = asyncio.run(run_fitness_scraper(fetch_details=not skip_details, debug=debug))
    print(f"\n  Done. {len(studios)} studios found.\n")

    if not studios:
        print("  No studios found. Try running with --debug to inspect the browser.")
        return pd.DataFrame()

    # ── Step 2: Owner lookup ──────────────────────────────────────────────────
    if not skip_sos:
        print("[2/2] Looking up owners via TN Secretary of State...")
        studios = enrich_with_owners(studios)
        print("\n  Done.\n")
    else:
        print("[2/2] Skipping owner lookup (--skip-sos).\n")

    # ── Step 3: Export ────────────────────────────────────────────────────────
    df = _reorder(pd.DataFrame(studios))
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"  CSV saved to: {OUTPUT_FILE}")
    print(f"  Total studios: {len(df)}")

    if "owner_names" in df.columns:
        with_owners = df["owner_names"].notna() & (df["owner_names"] != "")
        print(f"  Owners found: {with_owners.sum()} / {len(df)}")

    return df


if __name__ == "__main__":
    args = sys.argv[1:]
    run(
        skip_details="--fast" in args,
        skip_sos="--skip-sos" in args,
        debug="--debug" in args,
    )