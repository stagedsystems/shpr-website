---
description: Load quick context about the shpr-website project
---

# shpr-website Quick Context

## Purpose
Public website for Magic City Savers (https://magiccitysavers.com): this week's
Birmingham grocery deals, an evergreen deals guide, an about page and a join
(sign-up) page. Built to be found by Google and cited by AI assistants.

## Hosting
Static HTML on **GitHub Pages** (`stagedsystems/shpr-website`, deploys on push
to `main`, ~1 minute) behind **Cloudflare (free plan)**. GitHub Pages cannot set
response headers, redirects or content negotiation, so all of that lives in
Cloudflare rules. **Read [docs/agent-readiness.md](../../docs/agent-readiness.md)
before touching Cloudflare, robots.txt or anything SEO-related.** It lists the
settings that must not be changed and why.

## Pages
| Page | Twin | Notes |
|---|---|---|
| [index.html](../../index.html) | `index.md` | Homepage; canonical URL is `/` |
| [deals.html](../../deals.html) | `deals.md` | This week's deals, prerendered + enhanced by `deals.js` |
| [birmingham-grocery-deals.html](../../birmingham-grocery-deals.html) | `birmingham-grocery-deals.md` | Evergreen guide |
| [join.html](../../join.html) | `join.md` | HubSpot sign-up form |
| [about.html](../../about.html) | `about.md` | |

`deals/<week-ending>/deals.md` is the weekly archive (markdown only).

## Generated vs hand-edited
[scripts/build_seo.py](../../scripts/build_seo.py) is the only thing that writes
generated content. Rerunning it overwrites:
- Everything between `<!-- BEGIN … -->` / `<!-- END … -->` markers in the HTML
  (head tags: canonical/OG/JSON-LD; deal highlights; deals summary + list)
- The `.md` twins (via `scripts/htmlmd.py`), `llms.txt`, `llms-full.txt`,
  `sitemap.xml`, and the `deals/` archive

Hand-edit: HTML **outside** the markers, `styles.css`, `deals.js`, `robots.txt`
(static on purpose). After any HTML edit, rerun `python3 scripts/build_seo.py`
so the twins and `llms-full.txt` pick it up, and commit the outputs together.

CI ([.github/workflows/build-check.yml](../../.github/workflows/build-check.yml))
reruns the build and **fails if any generated file is stale**.

## Weekly update
Driven from shpr-deals: `/publish-website-deals` copies
`weekly/WE_yyyy-mm-dd/2_deals-formatted-all.md` → `deals.md`, runs
`build_seo.py`, then commits "Update weekly deals for week ending yyyy-mm-dd".

## Rules that are easy to break
- **Link home as `/`, never `index.html`.** The `index.html` links caused a
  Search Console "Duplicate without user-selected canonical" (fixed 2026-09-16,
  commit e412a4f). Internal links should match the canonical URLs.
- **http→https is a Cloudflare setting** (SSL/TLS → Edge Certificates → Always
  Use HTTPS, on since 2026-09-16). Don't rely on GitHub Pages for it.
- **Don't enable Cloudflare "Managed robots.txt"**: it replaces ours and
  blocks AI crawlers.
- **Don't add a Cache Rule for HTML**: Cloudflare ignores `Vary: Accept`, so
  browsers would get served the Markdown twins.
- **Adding a page means adding a Cloudflare Markdown-negotiation rule** and an
  entry in `PAGES` in `build_seo.py`. 8 of 10 Transform Rules are used.
- Prose must live in `<h1>`–`<h6>`, `<p>` or `<li>` to reach the `.md` twin;
  the build prints a `note:` line for anything it dropped.
- Static assets (robots.txt, styles.css, images) are cached at the edge for 4h:
  purge the URL in Cloudflare after changing one.

## Quick checks
```bash
curl -sI http://magiccitysavers.com/ | grep -iE '^HTTP|location'      # 301 → https
curl -sI https://magiccitysavers.com/ | grep -iE 'content-type|x-robots' # text/html, NO x-robots-tag
curl -sI https://magiccitysavers.com/index.md | grep -i x-robots         # noindex, follow
gh run list --limit 3                                                    # CI + Pages deploy
```

## Related
- `../shpr-deals`: weekly deals pipeline that feeds `deals.md`
- `~/REPOS/ss-shpr`: orchestration project / backlog
