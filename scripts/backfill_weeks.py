#!/usr/bin/env python3
"""One-time: recover every past week's deals.md from git history.

deals.md is overwritten in place each week, so ~33 weeks of Birmingham grocery
prices exist only as git blobs and have never had a URL. This walks the file's
history, takes the newest version of each distinct week, and writes it to
deals/<week-ending>/deals.md, which is where build_seo.py expects to find the
markdown for a week when it renders the pages.

Run once:

    python3 scripts/backfill_weeks.py
    python3 scripts/build_seo.py

Safe to re-run: a week already on disk is left alone unless --force is passed.
It never touches the root deals.md.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEALS_DIR = ROOT / "deals"
WEEK_RE = re.compile(r"Week Ending\s+(\d{4}-\d{2}-\d{2})")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite weeks already on disk")
    args = ap.parse_args()

    # Newest commit first, so the first version of a week we encounter is the
    # final one -- later commits fixed item names and units (see "Align Walmart
    # tilapia naming", "Align tilapia item name and unit") and those corrections
    # are what should be published.
    shas = git("log", "--format=%H", "--follow", "--", "deals.md").split()

    seen = {}
    for sha in shas:
        try:
            content = git("show", f"{sha}:deals.md")
        except subprocess.CalledProcessError:
            continue
        m = WEEK_RE.search(content)
        if not m:
            continue
        seen.setdefault(m.group(1), content)

    if not seen:
        sys.exit("no weeks found in deals.md history")

    written = skipped = 0
    for week in sorted(seen):
        target = DEALS_DIR / week / "deals.md"
        if target.exists() and not args.force:
            skipped += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(seen[week], encoding="utf-8")
        written += 1

    print(f"{len(seen)} weeks in history ({min(seen)} .. {max(seen)}): "
          f"{written} written, {skipped} already on disk")


if __name__ == "__main__":
    main()
