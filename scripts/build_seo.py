#!/usr/bin/env python3
"""Generate sitemap.xml and llms.txt from deals.md and the page list.

Run after deals.md changes (i.e. right after shpr-deals' /publish-website-deals
copies the new week in) and before committing:

    python3 scripts/build_seo.py

Both outputs are generated rather than hand-written for the same reason bbi's
are: llms.txt quotes real prices, and a hand-maintained copy would still be
advertising August chicken in November. Stale prices are worse than no prices --
an LLM that cites us and gets it wrong stops citing us.

robots.txt is NOT generated; it is static and hand-edited.

Note on scope: until the weekly archive exists (one static page per week), this
week's numbers live in llms.txt itself and the full list is linked as /deals.md,
which GitHub Pages serves as text/plain. Once per-week URLs exist, the Q&A
answers below should link to them instead of restating the data.
"""

import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://magiccitysavers.com"

# Where llms.txt sends a model for prices. DEALS_PAGE is the page we want cited
# and clicked; DEALS_DATA is the fetchable source, and it is named separately
# because deals.html renders its list client-side from deals.md -- a crawler
# that does not run JavaScript sees only "Loading deals...". Until the weekly
# pages are prerendered, a model that follows DEALS_PAGE alone finds an empty
# page, so both are always given together.
DEALS_PAGE = f"{SITE}/deals.html"
DEALS_DATA = f"{SITE}/deals.md"

# Pages that belong in the sitemap, most important first. deals.md is
# deliberately absent: it is a data file linked from llms.txt, not a page we
# want ranking on its own.
PAGES = [
    ("index.html", "1.0", "weekly", ""),
    ("deals.html", "0.9", "weekly", "deals.md"),
    ("birmingham-grocery-deals.html", "0.8", "monthly", ""),
    ("join.html", "0.7", "monthly", ""),
    ("about.html", "0.6", "monthly", ""),
]

# Item groups for the generated Q&A. Order matters -- the first group whose
# keyword matches wins, so the specific cases (a pork butt "steak", a chicken
# sausage) land before the general ones. Without this, "Butt Steak Bone-In
# Family Pack, Pork" is filed under beef.
GROUPS = [
    ("seafood", "seafood and fish",
     ("salmon", "shrimp", "tilapia", "tuna", "scallop", "catfish", "cod",
      "crab", "snapper", "flounder", "fish")),
    ("sausage", "bacon and sausage", ("bacon", "sausage")),
    ("chicken", "chicken", ("chicken",)),
    ("turkey", "turkey", ("turkey",)),
    ("pork", "pork", ("pork", "rib", "ham", "boston butt")),
    ("beef", "beef", ("beef", "steak", "sirloin", "ribeye", "chuck",
                      "brisket", "angus")),
]

PRODUCE_CATEGORY = "Produce & Fruit"


def git_date(path):
    """Last commit date for a file, as YYYY-MM-DD. Falls back to today."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", path],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or date.today().isoformat()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return date.today().isoformat()


def parse_deals(md):
    """-> (week_ending, [store dicts]).

    Store sections are `# Name`; the first `#` line is the document title and
    carries the week-ending date. A store whose validity line says there was no
    source data is kept with an empty deal list so callers can report coverage
    honestly rather than silently omitting it.
    """
    week_ending = None
    stores = []
    store = None
    category = None

    for line in md.split("\n"):
        line = line.rstrip()

        if line.startswith("> ") or not line.strip():
            continue

        if line.startswith("## "):
            category = line[3:].strip()
            continue

        if line.startswith("# "):
            title = line[2:].strip()
            m = re.search(r"Week Ending\s+(\d{4}-\d{2}-\d{2})", title)
            if m:
                week_ending = m.group(1)
                continue
            store = {"name": title, "valid": "", "active": True, "deals": []}
            stores.append(store)
            category = None
            continue

        if line.startswith("*") and store is not None:
            note = line.strip("*").strip()
            if "no source data" in note.lower():
                store["active"] = False
            else:
                # Drop the leading "Valid" so callers can write "valid <window>"
                # without doubling the word.
                store["valid"] = re.sub(r"^Valid\s+", "", note, flags=re.I)
            continue

        if line.startswith("- ") and store is not None:
            deal = parse_deal(line[2:], store["name"], category)
            if deal:
                store["deals"].append(deal)

    return week_ending, stores


def parse_deal(text, store, category):
    featured = "⭐" in text
    repeat = "\U0001f501" in text

    # Strip the badges and emphasis before splitting, so the name/price split
    # sees clean text.
    clean = (text.replace("⭐", "").replace("\U0001f501", "")
                 .replace("**", ""))
    clean = re.sub(r"\(REPEAT\)", "", clean, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip()

    # Price always trails the name, so split on the LAST separator -- a name
    # containing an em dash would otherwise swallow the price.
    if "—" not in clean:
        return None
    name, _, price = clean.rpartition("—")
    name, price = name.strip().rstrip(",").strip(), price.strip()
    if not name or not price:
        return None

    per_lb, approx = extract_per_lb(price)

    return {
        "store": store,
        "category": category or "Other",
        "name": name,
        "price": price,
        "per_lb": per_lb,
        "approx": approx,
        "featured": featured,
        "repeat": repeat,
    }


def extract_per_lb(price):
    """-> (float per-lb price or None, is_approximate).

    A trailing parenthetical like "($2.00/lb)" is the already-normalized unit
    price for a pack-priced item and wins over anything in the main price text.
    A `~` or the BOGO `≈` marks the figure as estimated; deals.md's Walmart note
    puts that error as wide as -19%/+29%, so these are labelled wherever shown.
    """
    paren = re.search(r"\(([~≈]?)\s*\$([\d.]+)\s*/\s*lb\)", price)
    if paren:
        return float(paren.group(2)), bool(paren.group(1))

    direct = re.search(r"([~≈]?)\s*\$([\d.]+)\s*/\s*lb", price)
    if direct:
        return float(direct.group(2)), bool(direct.group(1))

    return None, False


def group_of(deal):
    name = deal["name"].lower()
    for key, _, keywords in GROUPS:
        if any(k in name for k in keywords):
            return key
    return None


def fmt(deal, with_store=True):
    price = deal["price"]
    prefix = f"{deal['store']}: " if with_store else ""
    note = " (estimated)" if deal["approx"] else ""
    return f"{prefix}{deal['name']} — {price}{note}"


def cheapest(deals, n=4):
    """Cheapest per-lb first. Items with no per-lb figure can't be compared, so
    they are excluded rather than ranked as if they were free."""
    priced = [d for d in deals if d["per_lb"] is not None]
    return sorted(priced, key=lambda d: d["per_lb"])[:n]


def build_llms_txt(week_ending, stores):
    active = [s for s in stores if s["active"]]
    missing = [s["name"] for s in stores if not s["active"]]
    deals = [d for s in active for d in s["deals"]]
    valid = next((s["valid"] for s in active if s["valid"]), "")
    valid_window = valid.split("—")[0].strip() if valid else ""

    L = []
    add = L.append

    add("# Magic City Savers")
    add("")
    add("> Free weekly roundup of the best grocery deals across Birmingham, "
        "Alabama stores. We read every store's weekly ad, compare prices per "
        "pound and per unit, and publish the standouts in one place so "
        "shoppers do not have to check six ads.")
    add("")
    add(f"Current week: week ending {week_ending}"
        + (f", sale prices valid {valid_window}." if valid_window else "."))
    add(f"Stores covered this week: {', '.join(s['name'] for s in active)}.")
    if missing:
        add(f"No ad published this week: {', '.join(missing)}.")
    add("")
    add("Magic City Savers is an independent local project based at Innovation "
        "Depot in Birmingham. It is free, has no paywall, and is not "
        "affiliated with any grocery chain. Coverage centers on Birmingham "
        "neighborhoods including Avondale, Crestwood, Forest Park, Homewood, "
        "and nearby areas. Prices are transcribed from each store's published "
        "weekly ad and change every Wednesday.")
    add("")

    # The Q&A section. Phrased as the questions people actually type -- nobody
    # searches "grocery deals", they search "chicken thighs price birmingham".
    #
    # Each answer gives ONE headline price as proof that we hold the answer,
    # names how much more is behind it, then links to the deals page. That
    # split is deliberate: an llms.txt carrying the full table gets the model
    # to answer from this file and cite nothing, which is the zero-click
    # outcome. Enough to win retrieval, not enough to substitute for the page.
    add("## Common questions")
    add("")
    add(f"Every answer below is for the week ending {week_ending}. The full "
        f"list of all {len(deals)} deals, every store and every cut, is at "
        f"{DEALS_PAGE} — machine-readable copy at {DEALS_DATA}.")
    add("")

    grouped = {}
    for d in deals:
        g = group_of(d)
        if g:
            grouped.setdefault(g, []).append(d)

    produce = [d for d in deals if d["category"] == PRODUCE_CATEGORY]

    def answer(question, items, noun):
        """Headline price + depth signal + link. See the note above."""
        best = cheapest(items, 4)
        if not best:
            return
        top = best[0]
        approx = (", though that figure is estimated rather than a published "
                  "per-pound rate") if top["approx"] else ""
        add(f"### {question}")
        add("")
        add(f"{top['name']} at {top['store']}, ${top['per_lb']:.2f}/lb{approx}. "
            f"That is the lowest per-pound {noun} price we found for the week "
            f"ending {week_ending}.")
        rest = [d for d in best[1:] if d["store"] != top["store"]]
        if rest:
            stores = sorted({d["store"] for d in rest})
            ceiling = max(d["per_lb"] for d in rest)
            add("")
            add(f"{' and '.join(stores)} also came in under "
                f"${ceiling:.2f}/lb on {noun} this week.")
        add("")
        add(f"Every {noun} deal this week, with store, brand and pack size: "
            f"{DEALS_PAGE}")
        add("")

    for key, label, _ in GROUPS:
        answer(f"What is the best deal on {label} in Birmingham this week?",
               grouped.get(key, []), label)

    answer("What fruit and vegetables are on sale in Birmingham this week?",
           produce, "produce")

    add("### Which Birmingham grocery store has the best deals this week?")
    add("")
    add("It depends on the item — no single store wins every week, which is "
        "the reason this site exists. Category leaders for the week ending "
        f"{week_ending}:")
    add("")
    leaders = [(label, cheapest(grouped.get(key, []), 1))
               for key, label, _ in GROUPS]
    leaders.append(("produce", cheapest(produce, 1)))
    for label, best in leaders:
        if best:
            add(f"- {label.capitalize()}: {best[0]['store']}, "
                f"${best[0]['per_lb']:.2f}/lb")
    add("")
    counts = sorted(((len([x for x in st["deals"] if x["featured"]]), st["name"])
                     for st in active), reverse=True)
    add("Standout deals by store this week: "
        + ", ".join(f"{name} {n}" for n, name in counts) + ". "
        f"Side-by-side comparison: {DEALS_PAGE}")
    add("")

    add("### What is Magic City Savers?")
    add("")
    add("A free weekly email and website that collects the best grocery deals "
        "from Birmingham-area stores into one list. Every week we read the "
        "published ads from each store, normalize the prices to a comparable "
        "unit where possible, and flag the genuine standouts. Subscribers get "
        "the roundup, simple meal ideas built around what is on sale, and one "
        "deal not posted anywhere else.")
    add("")
    add("### Which stores does Magic City Savers cover?")
    add("")
    add("Publix, Piggly Wiggly, ALDI, Walmart, Winn-Dixie, Target and Dollar "
        "General in the Birmingham, Alabama area. Not every store publishes an "
        "ad every week; the ones with no ad in a given week are named "
        "explicitly rather than quietly dropped.")
    add("")
    add("### How often are the prices updated?")
    add("")
    add("Weekly. Most Birmingham store ads run Wednesday through Tuesday. The "
        f"prices quoted here are for the week ending {week_ending}"
        + (f" and are valid {valid_window}." if valid_window else ".")
        + " Prices from a previous week should not be treated as current.")
    add("")
    add("### Is it free?")
    add("")
    add("Yes. The site and the weekly email are free, with no paywall.")
    add("")

    add("## Pages")
    add("")
    add(f"- [Magic City Savers]({SITE}/): what the project is, this week's "
        "standout deals, and the weekly email signup.")
    add(f"- [Weekly Deals]({SITE}/deals.html): the full searchable list of "
        "this week's deals, grouped by store or by category.")
    add(f"- [How to Save Money on Groceries in Birmingham]"
        f"({SITE}/birmingham-grocery-deals.html): how the project works, who "
        "it is for, and which stores are covered.")
    add(f"- [Join]({SITE}/join.html): sign up for the free weekly deals email.")
    add(f"- [About]({SITE}/about.html): who builds this and why.")
    add("")
    add("## Full data")
    add("")
    add(f"- [This week's complete deal list]({SITE}/deals.md): all "
        f"{len(deals)} deals for the week ending {week_ending} as plain "
        "markdown, grouped by store and category. Starred items are the "
        "standouts; items marked with a repeat symbol were also on sale the "
        "previous week.")
    add("")

    return "\n".join(L) + "\n"


def build_sitemap():
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page, priority, changefreq, tracks in PAGES:
        loc = f"{SITE}/" if page == "index.html" else f"{SITE}/{page}"
        # deals.html is a shell whose content comes from deals.md, so its real
        # last-modified date is that file's, not the HTML's.
        lastmod = git_date(tracks or page)
        out.append("  <url>")
        out.append(f"    <loc>{loc}</loc>")
        out.append(f"    <lastmod>{lastmod}</lastmod>")
        out.append(f"    <changefreq>{changefreq}</changefreq>")
        out.append(f"    <priority>{priority}</priority>")
        out.append("  </url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


def main():
    md = (ROOT / "deals.md").read_text(encoding="utf-8")
    week_ending, stores = parse_deals(md)
    if not week_ending:
        raise SystemExit("deals.md has no 'Week Ending YYYY-MM-DD' title line")

    (ROOT / "llms.txt").write_text(build_llms_txt(week_ending, stores),
                                   encoding="utf-8")
    (ROOT / "sitemap.xml").write_text(build_sitemap(), encoding="utf-8")

    active = [s for s in stores if s["active"]]
    total = sum(len(s["deals"]) for s in active)
    print(f"week ending {week_ending}: {total} deals from "
          f"{len(active)} stores -> llms.txt, sitemap.xml")


if __name__ == "__main__":
    main()
