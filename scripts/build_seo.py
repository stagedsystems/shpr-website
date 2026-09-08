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

import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htmlmd
import render

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://magiccitysavers.com"

# Where llms.txt sends a model for prices. DEALS_PAGE is the page we want cited
# and clicked; DEALS_DATA is the same week as raw markdown, offered alongside it
# for anything that would rather parse text than HTML. Both are safe to hand out
# now that inject_deals_html() prerenders the deals into DEALS_PAGE -- before
# that it was a shell reading "Loading deals..." to anything without JavaScript.
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
# Item classification runs in three passes, because one flat keyword list gets
# it wrong. Product form beats species: a chicken sausage is a sausage. Explicit
# species beats cut name: "Butt Steak Bone-In Family Pack, Pork" is pork and
# "Beef Back Ribs" is beef. With a single list ordered pork-before-beef, the
# keyword "rib" claimed 77 beef-named items across 24 archived weeks, and in
# four of those weeks it changed which item got published as the cheapest beef.
FORMS = (
    ("sausage", ("bacon", "sausage")),
)
SPECIES = (
    ("seafood", ("salmon", "shrimp", "tilapia", "tuna", "scallop", "catfish",
                 "cod", "crab", "snapper", "flounder", "crawfish", "lobster",
                 "oyster", "haddock", "pollock", "mahi", "swai", "whiting")),
    ("chicken", ("chicken",)),
    ("turkey", ("turkey",)),
    # "beef" needs word boundaries or it eats "Beefsteak Tomato", which was
    # published as the cheapest beef deal for week ending 2026-09-06.
    ("beef", (r"\bbeef\b",)),
    # "ham" needs word boundaries or it eats "Hamburger"; without it here,
    # "Bone-In Ham Steak" fell through to the beef cut list and matched "steak".
    ("pork", ("pork", r"\bham\b", r"\bhams\b", r"\bhocks?\b")),
)
# Cut names, consulted only when no species is stated. Beef before pork so
# "ribeye" is not eaten by "rib".
CUTS = (
    # A "ribeye chop" is pork; a "ribeye steak" is beef. Checked before the beef
    # list so plain "ribeye" does not claim it. Deliberately not a bare "chop"
    # keyword -- that would file "Chopped Romaine Lettuce" as pork, and lamb
    # chops are better left unclassified than filed as the wrong animal.
    ("pork", (r"\bribeye chops?\b",)),
    # "steak" is bounded for the same reason as "beef" above: unbounded, it
    # matched "Beefsteak Tomato" here even once the species pass stopped doing so.
    ("beef", ("ribeye", "rib eye", "sirloin", "brisket", "angus", "chuck",
              "t-bone", "porterhouse", "filet mignon", "flank", "skirt steak",
              "tri-tip", "tri tip", r"\bsteaks?\b")),
    ("pork", ("spare rib", "sparerib", "baby back", "boston butt", "rib",
              "boneless half loin")),
    ("seafood", ("fish",)),
)

# Output order: how the categories are presented, and the labels they carry.
GROUPS = [
    ("chicken", "chicken"),
    ("beef", "beef"),
    ("pork", "pork"),
    ("seafood", "seafood and fish"),
    ("sausage", "bacon and sausage"),
    ("turkey", "turkey"),
]

PRODUCE_CATEGORY = "Produce & Fruit"

# The archive writes "no data" eight different ways. Only 9 of 151 such markers
# use the "no source data" phrasing this once tested for, so 142 stores with an
# empty deal list were being advertised as covered -- the precise failure the
# parse_deals docstring claims to prevent.
NO_DATA_RE = re.compile(
    r"no (?:source )?(?:data|deals)|not (?:yet )?collected|raw extract empty",
    re.I)

# GROUPS is ordered for correct keyword matching, not for prominence. Meta
# descriptions lead with the categories people actually search, so seafood does
# not open all 33 pages just because it sorts first in the matcher.
BILLING_ORDER = ("chicken", "beef", "pork", "produce", "seafood and fish",
                 "bacon and sausage", "turkey")


def git_date(path):
    """Last-modified date for the sitemap, as YYYY-MM-DD.

    The last commit that touched the file, EXCEPT when the working tree copy
    already differs from HEAD -- which is the normal case here, because this
    script rewrites index.html, join.html and deals.html and the docstring says
    to run it before committing. Reading the commit date alone published a
    homepage lastmod of 2025-12-29 on a page that had just been regenerated,
    while also declaring changefreq weekly.
    """
    try:
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", path],
                               cwd=ROOT).returncode != 0
        if dirty:
            return date.today().isoformat()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
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
            # Remove every emphasis marker, not just an outer pair: a line like
            # "*Valid Jul 22-28, 2026* — Irondale Supercenter" closes its
            # emphasis mid-line, and str.strip("*") left the inner one to render.
            note = line.replace("*", "").strip().strip("()").strip()
            if NO_DATA_RE.search(note) or "[" in note:
                # "[date range]" is the unfilled template placeholder; it is not
                # a sale window and must not be rendered as one.
                pass
            elif not store["valid"]:
                # First note wins. Some weeks put several *-prefixed lines under
                # a store (location, an estimation caveat); those are not
                # validity windows, and last-wins let them overwrite the real one.
                # Drop the leading "Valid" so callers can write "valid <window>".
                store["valid"] = re.sub(r"^Valid\s+", "", note, flags=re.I)
            continue

        if line.startswith("- ") and store is not None:
            deal = parse_deal(line[2:], store["name"], category)
            if deal:
                store["deals"].append(deal)

    # Coverage is decided by whether a store actually has deals, not by whether
    # its note matched a phrase. The archive writes "no data" eight different
    # ways and sometimes just leaves the "[date range]" placeholder, so matching
    # prose left 142 empty stores advertised as covered. A store with no deals
    # is not covered, whatever its note says.
    for store in stores:
        store["active"] = bool(store["deals"])

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
    """Classify an item. See FORMS/SPECIES/CUTS above for why it is three passes."""
    name = deal["name"].lower()
    for table in (FORMS, SPECIES, CUTS):
        for key, keywords in table:
            # A keyword starting with \b is a regex needing word boundaries;
            # everything else is a plain substring.
            if any(re.search(k, name) if k.startswith("\\b") else k in name
                   for k in keywords):
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


def valid_window(stores):
    """The sale window, with any store-location suffix removed.

    Defined once because it was being derived three ways: llms.txt split on the
    em dash, the deals.html h1 and the homepage line did not, so the same run
    could publish "Aug 26 - Sep 1, 2026" in one place and
    "Aug 26 - Sep 1, 2026 — Irondale Supercenter" in another.
    """
    raw = next((s["valid"] for s in stores if s["active"] and s["valid"]), "")
    return raw.split("—")[0].strip() if raw else ""


def category_leaders(deals):
    """[(label, cheapest deal)] per category, for the pages and for llms.txt.

    One implementation so a page and the llms.txt entry describing it can never
    disagree about which store won a category.
    """
    grouped = {}
    for d in deals:
        g = group_of(d)
        if g:
            grouped.setdefault(g, []).append(d)
    out = []
    for key, label in GROUPS:
        best = cheapest(grouped.get(key, []), 1)
        if best:
            out.append((label, best[0]))
    produce = cheapest([d for d in deals if d["category"] == PRODUCE_CATEGORY], 1)
    if produce:
        out.append(("produce", produce[0]))
    # GROUPS is ordered so keyword matching is correct (pork before beef, so a
    # pork "butt steak" is not filed as beef). That is the wrong order to show a
    # reader, who came for chicken and beef, so sort for prominence on the way
    # out and leave the matcher's order alone.
    return sorted(out, key=lambda ld: (BILLING_ORDER.index(ld[0])
                                       if ld[0] in BILLING_ORDER
                                       else len(BILLING_ORDER)))


def week_dirs():
    """Every archived week on disk, newest first."""
    root = ROOT / "deals"
    if not root.is_dir():
        return []
    weeks = [p.name for p in root.iterdir()
             if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)
             and (p / "deals.md").exists()]
    return sorted(weeks, reverse=True)


def inject_deals_html(week_ending, stores, leaders):
    """Prerender the current week into deals.html.

    Two regions, and the split matters. deals.js overwrites #deals-content on
    load, so the full listing goes in there -- with JavaScript the page is
    unchanged, without it the deals are still in the HTML. The summary goes
    ABOVE that container, where deals.js cannot reach it, so the "cheapest per
    pound" answer survives for human visitors too.

    Everything outside the markers is hand-maintained and left alone.
    """
    path = ROOT / "deals.html"
    src = path.read_text(encoding="utf-8")
    active = [s for s in stores if s["active"]]
    missing = [s["name"] for s in stores if not s["active"]]
    deals = [d for s in active for d in s["deals"]]
    window = valid_window(stores)

    def region(name, body):
        return (f"      <!-- BEGIN {name}: generated by scripts/build_seo.py -->\n"
                f"{body}\n      <!-- END {name} -->")

    summary = region("summary", render.summary_block(
        leaders, week_ending, window, len(deals),
        [s["name"] for s in active], missing))
    listing = region("deals", render.listing(active))

    # The summary sits between the header and the search/group controls.
    marker = '    <div class="deals-controls">'
    if marker not in src:
        raise SystemExit("deals.html: could not find the deals-controls div")
    src = re.sub(r"      <!-- BEGIN summary:.*?<!-- END summary -->\n", "",
                 src, flags=re.S)
    src = src.replace(marker, f"{summary}\n{marker}", 1)

    pattern = re.compile(
        r'(<main id="deals-content" class="deals-content">)(.*?)(</main>)', re.S)
    if not pattern.search(src):
        raise SystemExit("deals.html: could not find the deals-content main element")
    src = pattern.sub(lambda m: f"{m.group(1)}\n{listing}\n    {m.group(3)}", src)

    path.write_text(src, encoding="utf-8")
    return len(deals)


def inject_highlights(week_ending, stores, leaders):
    """Refresh the "Recent Birmingham Grocery Deals" list on index.html and
    join.html from the current week.

    Both carried the same six deals hand-typed in December 2025. By September
    four of them were not on sale anywhere and one was half its real price --
    the homepage advertised a Publix strip steak at $7.99/lb against an actual
    $14.99/lb. A page that quotes a price has to be generated from the same file
    the price came from, or it lies within a month.

    The trailing line is also the homepage's only link to deals.html, which had
    no internal links pointing at it at all.
    """
    active = [s for s in stores if s["active"]]
    total = sum(len(s["deals"]) for s in active)
    window = valid_window(stores)

    items = []
    for _, d in leaders:
        # Trim at the first comma: pack sizes and grades are detail the deals
        # page carries, and the homepage list has one line to be scannable in.
        name = d["name"].split(",")[0].strip()
        # Publix brands its own products "Publix Chicken Leg Quarters", which
        # renders as "Publix: Publix Chicken Leg Quarters" once the store is
        # prefixed. Drop the duplicate.
        if name.lower().startswith(d["store"].lower() + " "):
            name = name[len(d["store"]) + 1:]
        # Estimated figures are labelled everywhere else (fmt(), summary_block,
        # llms.txt). Unlabelled here, the homepage could state a price ~29% off
        # as fact -- deals.md's own Walmart note puts the band at -19%/+29%.
        note = " (est.)" if d["approx"] else ""
        items.append(f'          <li class="deal-item">{render.esc(d["store"])}: '
                     f'{render.esc(name)} — <strong>${d["per_lb"]:.2f}/lb</strong>'
                     f'{note}</li>')

    when = render.esc(window) if window else render.pretty_date(week_ending)
    body = "\n".join([
        '          <!-- BEGIN highlights: generated by scripts/build_seo.py -->',
        *items,
        '          <!-- END highlights -->',
    ])
    tail = (f'        <p class="text-sm text-gray-600 text-center mt-4">Week of '
            f'{when} — <a href="deals.html">see all {total} deals</a></p>')

    pattern = re.compile(
        r'(Recent Birmingham Grocery Deals</h2>\s*<ul class="deals-list">)'
        # The trailing \s* inside the optional group matters: without it the
        # whitespace after </p> survives each run and the block drifts down the
        # file one blank line at a time.
        r'(.*?)(</ul>)(\s*(?:<p class="text-sm text-gray-600 text-center mt-4">.*?</p>\s*)?)',
        re.S)

    # Check both pages before writing either. Writing index.html and then
    # failing on join.html left the two on different weeks, behind a non-zero
    # exit that looked like nothing had happened.
    pending = {}
    for page in ("index.html", "join.html"):
        src = (ROOT / page).read_text(encoding="utf-8")
        if not pattern.search(src):
            raise SystemExit(f"{page}: could not find the Recent Deals list")
        pending[page] = pattern.sub(
            lambda m: f"{m.group(1)}\n{body}\n        {m.group(3)}\n{tail}\n      ",
            src, count=1)
    for page, src in pending.items():
        (ROOT / page).write_text(src, encoding="utf-8")
    return list(pending)


def faq_entries(week_ending, stores):
    """The generated Q&A, built once and rendered twice.

    llms.txt prints these as Markdown; build_faq_jsonld() emits the same
    questions as schema.org FAQPage on deals.html. They are generated from one
    function for the same reason llms.txt is generated at all -- two copies of
    a chicken price drift apart within a month, and a page whose visible answer
    and structured answer disagree is worse than one carrying neither.

    Each entry is {"q", "paras", "link"}. "link" is the "see the full list"
    pointer: llms.txt wants it, the JSON-LD does not, because the JSON-LD lives
    on the very page it would be pointing at.
    """
    active = [s for s in stores if s["active"]]
    deals = [d for s in active for d in s["deals"]]
    window = valid_window(stores)

    grouped = {}
    for d in deals:
        g = group_of(d)
        if g:
            grouped.setdefault(g, []).append(d)

    produce = [d for d in deals if d["category"] == PRODUCE_CATEGORY]

    entries = []

    def answer(question, items, noun):
        """Headline price + depth signal + link. See the note in build_llms_txt."""
        best = cheapest(items, 4)
        if not best:
            return
        top = best[0]
        approx = (", though that figure is estimated rather than a published "
                  "per-pound rate") if top["approx"] else ""
        paras = [f"{top['name']} at {top['store']}, ${top['per_lb']:.2f}/lb"
                 f"{approx}. That is the lowest per-pound {noun} price we found "
                 f"for the week ending {week_ending}."]
        rest = [d for d in best[1:] if d["store"] != top["store"]]
        if rest:
            names = sorted({d["store"] for d in rest})
            joined = (names[0] if len(names) == 1
                      else " and ".join([", ".join(names[:-1]), names[-1]]))
            # "at or under", not "under": ceiling is the price of the most
            # expensive item listed, so with a single other store the strict
            # form was always false.
            ceiling = max(d["per_lb"] for d in rest)
            paras.append(f"{joined} also came in at or under "
                         f"${ceiling:.2f}/lb on {noun} this week.")
        entries.append({
            "q": question,
            "paras": paras,
            "link": (f"Every {noun} deal this week, with store, brand and pack "
                     f"size: {DEALS_PAGE}"),
        })

    for key, label in GROUPS:
        answer(f"What is the best deal on {label} in Birmingham this week?",
               grouped.get(key, []), label)

    answer("What fruit and vegetables are on sale in Birmingham this week?",
           produce, "produce")

    leaders = [(label, cheapest(grouped.get(key, []), 1))
               for key, label in GROUPS]
    leaders.append(("produce", cheapest(produce, 1)))
    rows = "\n".join(f"- {label.capitalize()}: {best[0]['store']}, "
                     f"${best[0]['per_lb']:.2f}/lb"
                     for label, best in leaders if best)
    counts = sorted(((len([x for x in st["deals"] if x["featured"]]), st["name"])
                     for st in active), reverse=True)
    entries.append({
        "q": "Which Birmingham grocery store has the best deals this week?",
        "paras": [
            "It depends on the item \u2014 no single store wins every week, which "
            "is the reason this site exists. Category leaders for the week "
            f"ending {week_ending}:",
            rows,
        ],
        "link": ("Standout deals by store this week: "
                 + ", ".join(f"{name} {n}" for n, name in counts) + ". "
                 f"Side-by-side comparison: {DEALS_PAGE}"),
    })

    entries.append({
        "q": "What is Magic City Savers?",
        "paras": ["A free weekly email and website that collects the best "
                  "grocery deals from Birmingham-area stores into one list. "
                  "Every week we read the published ads from each store, "
                  "normalize the prices to a comparable unit where possible, "
                  "and flag the genuine standouts. Subscribers get the roundup, "
                  "simple meal ideas built around what is on sale, and one deal "
                  "not posted anywhere else."],
        "link": None,
    })
    entries.append({
        "q": "Which stores does Magic City Savers cover?",
        "paras": ["Publix, Piggly Wiggly, ALDI, Walmart, Winn-Dixie, Target and "
                  "Dollar General in the Birmingham, Alabama area. Not every "
                  "store publishes an ad every week; the ones with no ad in a "
                  "given week are named explicitly rather than quietly dropped."],
        "link": None,
    })
    entries.append({
        "q": "How often are the prices updated?",
        "paras": ["Weekly. Most Birmingham store ads run Wednesday through "
                  "Tuesday. The prices quoted here are for the week ending "
                  f"{week_ending}"
                  + (f" and are valid {window}." if window else ".")
                  + " Prices from a previous week should not be treated as "
                  "current."],
        "link": None,
    })
    entries.append({
        "q": "Is it free?",
        "paras": ["Yes. The site and the weekly email are free, with no paywall."],
        "link": None,
    })
    return entries


def build_llms_txt(week_ending, stores):
    active = [s for s in stores if s["active"]]
    missing = [s["name"] for s in stores if not s["active"]]
    deals = [d for s in active for d in s["deals"]]
    window = valid_window(stores)

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
        + (f", sale prices valid {window}." if window else "."))
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

    for e in faq_entries(week_ending, stores):
        add(f"### {e['q']}")
        add("")
        for para in e["paras"]:
            add(para)
            add("")
        if e["link"]:
            add(e["link"])
            add("")

    add("## Pages")
    add("")
    add(f"- [Magic City Savers]({SITE}/): what the project is, this week's "
        "standout deals, and the weekly email signup.")
    add(f"- [Weekly Deals]({SITE}/deals.html): the full list of this week's "
        "deals, grouped by store and category, with the cheapest per-pound "
        "price in each category called out at the top.")
    add(f"- [How to Save Money on Groceries in Birmingham]"
        f"({SITE}/birmingham-grocery-deals.html): how the project works, who "
        "it is for, and which stores are covered.")
    add(f"- [Join]({SITE}/join.html): sign up for the free weekly deals email.")
    add(f"- [About]({SITE}/about.html): who builds this and why.")
    add("")
    add("## Full data")
    add("")
    add(f"- [This week's deals]({SITE}/deals.html): all {len(deals)} deals for "
        f"the week ending {week_ending}, by store and category.")
    add(f"- [Plain markdown copy]({SITE}/deals.md): the same week as text, if "
        "that is easier to parse than the page.")
    add(f"- [Everything in one fetch]({SITE}/llms-full.txt): every page above "
        f"plus the complete deal list for the week ending {week_ending}.")
    add("")
    add("Every page also has a Markdown twin at the same path with a .md "
        "extension — /index.md, /about.md, /join.md, "
        "/birmingham-grocery-deals.md — if you would rather not parse the "
        "HTML. They are the same content, about 80% smaller.")
    add("")

    return "\n".join(L) + "\n"


def head_region(name, body):
    """A generated block inside <head>, delimited so reruns replace it."""
    return (f"  <!-- BEGIN {name}: generated by scripts/build_seo.py -->\n"
            f"{body}\n"
            f"  <!-- END {name} -->")


def replace_head_region(src, name, body, page):
    """Swap the named region into <head>, or insert it before </head>."""
    block = head_region(name, body)
    pattern = re.compile(
        rf"  <!-- BEGIN {name}: generated by scripts/build_seo\.py -->.*?"
        rf"  <!-- END {name} -->", re.S)
    if pattern.search(src):
        return pattern.sub(lambda _: block, src, count=1)
    if "</head>" not in src:
        raise SystemExit(f"{page}: no </head> to inject {name} into")
    return src.replace("</head>", f"{block}\n</head>", 1)


def page_meta(src, page):
    """The page's own <title> and description, reused rather than restated.

    Retyping either into an og: tag creates a second copy that drifts from the
    first. Everything below is derived from what the page already says.
    """
    title = re.search(r"<title>(.*?)</title>", src, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', src)
    if not title:
        raise SystemExit(f"{page}: no <title> to build social tags from")
    if not desc:
        raise SystemExit(f"{page}: no meta description to build social tags from")
    return " ".join(title.group(1).split()), desc.group(1)


def build_jsonld(page, week_ending, stores):
    """schema.org for one page, or None if the page warrants none.

    Deliberately NOT used: Product and Offer. Those describe something the
    publisher sells, and we sell nothing -- these are other companies' shelf
    prices, transcribed. Marking them up as our offers would be false structured
    data, and the rich result it fishes for is the kind that earns a manual
    action. Organization, WebSite and FAQPage are all true as written.
    """
    org = {
        "@type": "Organization",
        "@id": f"{SITE}/#organization",
        "name": "Magic City Savers",
        "url": f"{SITE}/",
        "logo": f"{SITE}/mcc_full_logo.png",
        "description": ("Free weekly roundup of the best grocery deals across "
                        "Birmingham, Alabama stores."),
        "areaServed": {
            "@type": "City",
            "name": "Birmingham",
            "addressRegion": "AL",
            "addressCountry": "US",
        },
        "sameAs": ["https://instagram.com/magiccitysavers"],
    }
    website = {
        "@type": "WebSite",
        "@id": f"{SITE}/#website",
        "url": f"{SITE}/",
        "name": "Magic City Savers",
        "inLanguage": "en-US",
        "publisher": {"@id": f"{SITE}/#organization"},
    }

    if page == "index.html":
        graph = [org, website]
    elif page == "deals.html":
        # The page really does answer these questions -- the "cheapest per
        # pound" block at the top is the same data these answers quote.
        graph = [{
            "@type": "FAQPage",
            "@id": f"{DEALS_PAGE}#faq",
            "isPartOf": {"@id": f"{SITE}/#website"},
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": e["q"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": "\n\n".join(e["paras"]),
                    },
                }
                for e in faq_entries(week_ending, stores)
            ],
        }]
    else:
        return None

    doc = {"@context": "https://schema.org", "@graph": graph}
    body = json.dumps(doc, indent=2, ensure_ascii=False)
    body = "\n".join("    " + line for line in body.splitlines())
    return ('  <script type="application/ld+json">\n'
            + body + "\n  </script>")


def inject_head_tags(week_ending, stores):
    """Canonical, Open Graph, Twitter and JSON-LD on every page.

    None of this existed: no page declared a canonical, and a link to the site
    shared anywhere rendered as a bare URL with no title, description or image.

    og:image is the logo, so the card type is summary rather than
    summary_large_image -- a 1:1 logo stretched into a 1.91:1 banner is the
    broken-looking result, and claiming the large card without art sized for it
    is how you get it.
    """
    written = []
    pending = {}
    for page, _, _, _ in PAGES:
        path = ROOT / page
        src = path.read_text(encoding="utf-8")
        title, desc = page_meta(src, page)
        url = f"{SITE}/" if page == "index.html" else f"{SITE}/{page}"

        lines = [
            f'  <link rel="canonical" href="{url}">',
            f'  <meta property="og:type" content="website">',
            f'  <meta property="og:site_name" content="Magic City Savers">',
            f'  <meta property="og:title" content="{render.esc(title)}">',
            f'  <meta property="og:description" content="{render.esc(desc)}">',
            f'  <meta property="og:url" content="{url}">',
            f'  <meta property="og:image" content="{SITE}/mcc_full_logo.png">',
            f'  <meta property="og:locale" content="en_US">',
            f'  <meta name="twitter:card" content="summary">',
            f'  <meta name="twitter:title" content="{render.esc(title)}">',
            f'  <meta name="twitter:description" content="{render.esc(desc)}">',
            f'  <meta name="twitter:image" content="{SITE}/mcc_full_logo.png">',
        ]
        jsonld = build_jsonld(page, week_ending, stores)
        if jsonld:
            lines.append(jsonld)

        # Validate every page before writing any, for the reason spelled out in
        # inject_highlights: a half-applied run is worse than a failed one.
        pending[page] = replace_head_region(src, "headtags", "\n".join(lines), page)
        written.append(page)

    for page, out in pending.items():
        (ROOT / page).write_text(out, encoding="utf-8")
    return written


def build_markdown_twins():
    """A .md alongside every HTML page, for agents that would rather not parse
    a layout.

    deals.html is absent on purpose: deals.md already IS its twin, generated
    upstream from the real data rather than scraped back out of the rendered
    page.

    These carry no <link rel="canonical"> of their own -- Markdown has nowhere
    to put one. The canonical and the noindex ride on response headers set by a
    Cloudflare Transform Rule; see docs/agent-readiness.md. Without that rule
    these are duplicate content, so they are also kept out of sitemap.xml.
    """
    out = []
    for page, _, _, _ in PAGES:
        if page == "deals.html":
            continue
        src = (ROOT / page).read_text(encoding="utf-8")
        url = f"{SITE}/" if page == "index.html" else f"{SITE}/{page}"
        body, lost = htmlmd.to_markdown(src, url)
        name = "index.md" if page == "index.html" else page[:-5] + ".md"
        (ROOT / name).write_text(body, encoding="utf-8")
        out.append((name, lost))
    return out


def build_llms_full_txt(week_ending, twins):
    """Every page plus this week's prices, in one fetch (llmstxt.org)."""
    L = [f"# Magic City Savers — full text",
         "",
         f"Everything on {SITE} as one document: all five pages, then the "
         f"complete deal list for the week ending {week_ending}. Generated by "
         "scripts/build_seo.py; do not edit by hand.",
         ""]
    for name, _ in twins:
        url = f"{SITE}/" if name == "index.md" else f"{SITE}/{name[:-3]}.html"
        L += [f"---", "", f"Source: {url}", "",
              (ROOT / name).read_text(encoding="utf-8").rstrip(), ""]
    L += ["---", "", f"Source: {DEALS_PAGE}", "",
          (ROOT / "deals.md").read_text(encoding="utf-8").rstrip(), ""]
    return "\n".join(L) + "\n"


def build_sitemap():
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page, priority, changefreq, tracks in PAGES:
        loc = f"{SITE}/" if page == "index.html" else f"{SITE}/{page}"
        # deals.html is regenerated from deals.md, so its real last-modified
        # date is that file's, not the HTML's.
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

    # Keep each week's markdown after deals.md rolls over. These are data, not
    # pages -- robots.txt disallows /deals/ -- and they exist so price history
    # is available later without digging through git blobs. See
    # scripts/backfill_weeks.py, which recovered the ones predating this.
    archived = ROOT / "deals" / week_ending / "deals.md"
    archived.parent.mkdir(parents=True, exist_ok=True)
    if not archived.exists() or archived.read_text(encoding="utf-8") != md:
        shutil.copyfile(ROOT / "deals.md", archived)

    active = [s for s in stores if s["active"]]
    deals = [d for s in active for d in s["deals"]]
    leaders = category_leaders(deals)

    inject_deals_html(week_ending, stores, leaders)
    inject_highlights(week_ending, stores, leaders)
    # After the content injections, not before: the head tags read each page's
    # title and description, and the twins are made from the finished HTML.
    inject_head_tags(week_ending, stores)
    twins = build_markdown_twins()

    (ROOT / "llms.txt").write_text(build_llms_txt(week_ending, stores),
                                   encoding="utf-8")
    (ROOT / "llms-full.txt").write_text(build_llms_full_txt(week_ending, twins),
                                        encoding="utf-8")
    (ROOT / "sitemap.xml").write_text(build_sitemap(), encoding="utf-8")

    weeks = len(week_dirs())
    print(f"week ending {week_ending}: {len(deals)} deals from {len(active)} "
          f"stores prerendered into deals.html")
    print("refreshed the deal highlights on index.html and join.html")
    print(f"wrote canonical/OpenGraph/JSON-LD into {len(PAGES)} pages")
    print(f"wrote {', '.join(n for n, _ in twins)}, llms.txt, llms-full.txt, "
          f"sitemap.xml; {weeks} weeks of data under deals/")

    # Prose living outside a heading, <p> or <li> never reaches the twins. Say
    # so on the run that introduces it rather than letting it go missing quietly.
    for name, lost in twins:
        if lost:
            print(f"  note: {name} dropped text outside a heading/p/li: "
                  + "; ".join(repr(x) for x in lost))


if __name__ == "__main__":
    main()
