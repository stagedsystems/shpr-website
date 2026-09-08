# Agent readiness — what is set up, and what must not be changed

How this site presents itself to search engines and AI assistants, why each piece
is the way it is, and the two things that will silently break it.

The site is static HTML on **GitHub Pages**, behind **Cloudflare (free plan)**.
That split matters more than anything else here: GitHub Pages serves the files
and **cannot set a custom response header**, so every header below is added by a
Cloudflare Transform Rule. Change hosting and the headers leave with it.

## Do not enable Cloudflare's "Managed robots.txt"

Cloudflare's **Agent Readiness → Diagnostics** panel flags the missing Content
Signal and gives one remedy: turn on *AI Crawl Control → robots.txt → Cloudflare
managed robots.txt*. **Do not.**

That toggle publishes Cloudflare's own robots.txt **in place of ours**, and its
purpose is to declare the content off-limits for AI training. It is what blocked
GPTBot, ClaudeBot, PerplexityBot and every other named agent on this domain until
2026-09-03. The dashboard will keep suggesting it. The check is already satisfied
by the hand-written `Content-Signal:` line in `robots.txt`.

`search=yes, ai-input=yes`, and `ai-train` deliberately omitted — silence is a
third state that neither grants nor refuses. Adding `ai-train=no` is a different
claim, not a tidier default; decide it on purpose or leave it out.

## Cloudflare ignores `Vary: Accept`

Documented behaviour: <https://developers.cloudflare.com/cache/concepts/vary/>.
Cloudflare varies cached objects on `Accept-Encoding` only.

The consequence: **the static `.md` URLs are the contract, and content
negotiation on `Accept: text/markdown` is a bonus that is only safe while HTML is
uncached at the edge.** Today `curl -sI https://magiccitysavers.com/` returns
`cf-cache-status: DYNAMIC`, so nothing is pinned and there is no bug. Add a Cache
Rule that makes HTML cacheable, however, and one representation gets stored and
served to everyone — which means browsers being handed Markdown.

So: never point a Cache Rule at HTML without removing negotiation first. Agents
that want Markdown should be sent to `/index.md` and friends, which are real
files and cannot be confused for anything else.

## The Cloudflare rules this site depends on

**Rule 1 — noindex on every Markdown response**
(`http_response_headers_transform`):

    Expression:  (http.request.uri.path.extension eq "md")
    Set static:  X-Robots-Tag = "noindex, follow"

`noindex, follow` is the whole reason the twins are safe to publish. Each `.md`
is a duplicate of an HTML page; without it you hand Google four extra copies of
the site and invite it to pick the wrong one. `follow` still lets the links in
them be crawled. The twins are also kept **out of `sitemap.xml`** for the same
reason — `build_seo.py` builds the sitemap from `PAGES`, which is HTML only.

It applies to *every* `.md`, deliberately — the weekly archive under `/deals/`
and the repo files GitHub Pages incidentally serves are all duplicates or
working notes, and none of them should be indexed either.

**Rule 2 — canonical, only where an HTML twin actually exists.**
⚠️ **Not deployed.** The dashboard rejected it on this free zone. Rule 1 already
removes the duplicate-content risk on its own, so this is polish, not a
prerequisite — but if you retry it, two things cost time:

- Cloudflare's expression syntax treats `\` as a string escape, so a regex
  `\.md$` must be written `"\\.md$"`. Writing `"\.md$"` fails with
  *expected ", xHH or OOO after \\*.
- With that fixed the form reported no error and still did not save, which
  points at `regex_replace()` being unavailable on the free plan rather than at
  the syntax. Confirm that before spending more time on the expression.

    Expression:  (http.request.uri.path in {"/index.md" "/about.md" "/join.md"
                  "/birmingham-grocery-deals.md" "/deals.md"})
    Set dynamic: Link = concat("<https://magiccitysavers.com",
                               regex_replace(http.request.uri.path, "\.md$", ".html"),
                               ">; rel=\"canonical\"")

The explicit path list is the point. Deriving the canonical from the path for
*all* `.md` looks tidier and emits `/-> /README.html` and
`/deals/2026-09-06/deals.html` — canonicals pointing at URLs that 404. A
canonical to a dead page is worse than none. Add a path here when a page gains a
twin.

The canonical is emitted **only on Markdown responses**. Do not generalise it to
HTML: the HTML pages carry their own `<link rel="canonical">` (injected by
`build_seo.py`), and a header derived from the request path would disagree with
them on any URL rewritten before it is served.

Note `/index.md` canonicalises to `/index.html`, which redirects to `/`. If that
ever matters, special-case it; it is not worth a rule today.

**Rule 3 — llms.txt discovery on HTML** (the Mintlify convention). Deployed
2026-09-08 and verified live on every HTML response.

It does **not** satisfy Cloudflare's Level 2 "Link Headers" check, contrary to
what that check's name suggests. After deploying it the scan reports *"Link
headers present but no agent-useful relation types found"*, and the check's own
readiness text explains why: it looks for *"where your structured product info
and catalog are located"*. It wants commerce relation types. `llms-txt` and
`llms-full-txt` are not what it is scoring, so Level 2 stays 0/3 and that is the
correct outcome for this site, not a defect. The rule is still worth having —
it is the convention real agents follow.

    Expression:  (http.response.content_type.media_type eq "text/html")
    Set static:  Link = <https://magiccitysavers.com/llms.txt>; rel="llms-txt",
                        <https://magiccitysavers.com/llms-full.txt>; rel="llms-full-txt"

**These rules and a deploy have to land together.** The twins are duplicate
content from the moment they are public until the `noindex` rule exists.

## What is generated, and from where

`scripts/build_seo.py` is the only thing that writes any of it. Run it after
`deals.md` changes and before committing:

| Output | Built from |
|---|---|
| `deals.html` summary + listing | `deals.md` via `scripts/render.py` |
| Deal highlights on `index.html`, `join.html` | `deals.md` |
| Canonical, Open Graph, Twitter, JSON-LD in every `<head>` | each page's own `<title>` and description |
| `index.md`, `about.md`, `join.md`, `birmingham-grocery-deals.md` | the finished HTML, via `scripts/htmlmd.py` |
| `llms.txt`, `llms-full.txt`, `sitemap.xml` | `deals.md` + the twins |

Nothing above is hand-editable — a rerun overwrites it. Hand-edit the regions
*outside* the `<!-- BEGIN … -->` / `<!-- END … -->` markers, and `robots.txt`,
which is static on purpose.

The Q&A in `llms.txt` and the `FAQPage` JSON-LD on `deals.html` come from one
function, `faq_entries()`. Keep it that way. Two copies of a chicken price
disagree within a month, and a page whose visible answer contradicts its own
structured data is worse than one carrying neither.

### The coupling to watch

`htmlmd.py` emits text from `<h1>`–`<h6>`, `<p>` and `<li>` **and nothing else**.
Prose added to a page outside those tags will not appear in its `.md` twin or in
`llms-full.txt`. This does not fail silently: the build prints every non-empty
run it dropped. A clean build prints no such line — if one appears, either move
the text into a real block element or add its class to `CHROME_CLASSES`.

## Deliberately not done

- **Product / Offer structured data.** These are other companies' shelf prices,
  transcribed. We sell nothing. Marking them up as our offers is false
  structured data and the rich result it fishes for earns manual actions.
- **API Catalog, Auth.md** (Cloudflare Level 2) — no API, no login. Cloudflare's
  own text says to skip the catalog when there is no API.
- **All of Level 3** (OAuth, A2A card, Skills Index, MCP card, WebMCP, DNS-AID)
  and **all of Commerce** — for sites that expose an agent or sell something.
- **Cloudflare's "Markdown for Agents"** — Pro-only. Note that the twins do
  **not** make the "Markdown Negotiation" check pass: after publishing all five,
  a rescan still reports *"Site does not support Markdown for Agents"*. That
  check tests Cloudflare's own feature, not whether Markdown is actually
  available at a URL. Passing it would need either Pro, or a Worker doing real
  `Accept: text/markdown` negotiation. The twins deliver the underlying benefit
  regardless — ~80% smaller payloads that agents can fetch today — so this is
  one checkbox worth leaving red.

## Verifying

A config that parses proves nothing; check behaviour. After deploying, and after
any Cloudflare rule change:

    curl -sI https://magiccitysavers.com/index.md \
      | grep -iE 'content-type|x-robots-tag|link'
    curl -sI https://magiccitysavers.com/ \
      | grep -iE 'content-type|link|cf-cache-status'
    curl -s  https://magiccitysavers.com/robots.txt | grep -i content-signal

Expected: `.md` returns `text/markdown` and `noindex, follow` (plus a canonical
`Link` if Rule 2 ever deploys); HTML returns `text/html`, the two `llms-txt`
links once Rule 3 is added, and **no** `X-Robots-Tag`.

## DNS note

The AI Crawl Control → Signals page lists every hostname in the zone and probes
`robots.txt` on each, so the Microsoft 365 service records — `autodiscover`,
`lyncdiscover`, `sip`, `enterpriseregistration`, `enterpriseenrollment` — show
521/526/530 there. That is expected and not a fault: they are already DNS-only,
and there is no web server behind them because there is not meant to be one.
Do not "fix" them.

`_domainconnect` was the real exception: it was proxied, which broke GoDaddy's
DomainConnect discovery (530 Origin DNS Error). Set to DNS-only on 2026-09-08.

`robots.txt` is served `cache-control: max-age=14400`. After changing it, purge
that URL at the edge or the old copy stays live for four hours — a change can be
correct at origin and invisible in production.
