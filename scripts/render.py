#!/usr/bin/env python3
"""HTML fragments for the prerendered parts of deals.html.

deals.html builds its list client-side by fetching deals.md, so a crawler that
does not run JavaScript -- which is every AI crawler, and Google on its first
pass -- used to see nothing but "Loading deals...". These functions render the
same content at build time so the page has real HTML in it either way.

Markup deliberately mirrors what deals.js emits (.deals-store, .deals-category,
.deals-item, .deals-featured, .deals-price ...) so the prerendered and
client-rendered views are styled by the same rules in styles.css and look the
same. Heading levels match too: deals.js used to build an h1 per store, which
after the page gained a real h1 of its own meant the JS view had one h1 per
store and the no-JS view had a different hierarchy entirely. Both are h2/h3 now
-- if one side changes, change the other.
"""

import html
import re

MONTHS = ("January February March April May June July August September "
          "October November December").split()


def esc(s):
    return html.escape(s, quote=True)


def pretty_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{MONTHS[m - 1]} {d}, {y}"


def deal_li(deal):
    """One <li>, matching the shape deals.js builds so styling is shared."""
    name = esc(deal["name"])
    price = esc(deal["price"])
    price = re.sub(r"(\$[\d.]+(?:/lb)?)", r'<span class="deals-price">\1</span>',
                   price)
    price = re.sub(r"(BOGO)", r'<span class="deals-bogo">\1</span>', price,
                   flags=re.I)

    classes = ["deals-item"]
    if deal["featured"]:
        classes.append("deals-featured")
    badges = ""
    if deal["featured"]:
        badges += '<span class="deals-badge">⭐</span>'
    if deal["repeat"]:
        badges += '<span class="deals-badge">\U0001f501</span>'

    return (f'        <li class="{" ".join(classes)}">{badges}'
            f'<span class="deals-name">{name}</span> — {price}</li>')


def listing(stores):
    """The full store > category > items listing, for inside #deals-content."""
    out = []
    for store in stores:
        if not store["deals"]:
            continue
        out.append(f'      <h2 class="deals-store">{esc(store["name"])}</h2>')
        if store["valid"]:
            out.append(f'      <p class="deals-date">Valid {esc(store["valid"])}</p>')
        by_cat = {}
        for d in store["deals"]:
            by_cat.setdefault(d["category"], []).append(d)
        for cat, items in by_cat.items():
            out.append(f'      <h3 class="deals-category">{esc(cat)}</h3>')
            out.append('      <ul class="deals-list">')
            out.extend(deal_li(d) for d in items)
            out.append("      </ul>")
    return "\n".join(out)


def summary_block(leaders, week_ending, valid_window, count, stores, missing):
    """The 'cheapest per pound' card and the h1.

    This lives OUTSIDE #deals-content on purpose. deals.js overwrites that
    container's innerHTML on load, so anything inside it is lost the moment
    JavaScript runs -- and this summary is the part a human most wants to see.
    Outside the container it survives, and it is also the block that answers the
    question somebody actually typed.
    """
    rows = "\n".join(
        f'          <li class="deals-item"><span class="deals-name">'
        f'{esc(label.capitalize())}</span> — <span class="deals-price">'
        f'${d["per_lb"]:.2f}/lb</span> · {esc(d["name"])} at {esc(d["store"])}'
        f'{" (estimated)" if d["approx"] else ""}</li>'
        for label, d in leaders)

    when = esc(valid_window) if valid_window else f"week ending {pretty_date(week_ending)}"
    intro = f"{count} deals from {esc(', '.join(stores))}."
    if missing:
        intro += f" No ad published this week from {esc(', '.join(missing))}."

    cheapest = ""
    if rows:
        cheapest = f"""
      <section class="card mb-8">
        <h2 class="text-2xl font-bold mb-4">Cheapest per pound this week</h2>
        <ul class="deals-list">
{rows}
        </ul>
      </section>"""

    return f"""      <h1>Birmingham grocery deals — {when}</h1>
      <p class="deals-date">{intro}</p>{cheapest}"""
