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

So: **never point a Cache Rule at HTML without removing negotiation first.**
That is the single change that would turn a working setup into browsers being
served Markdown.

`Vary: Accept` is sent anyway (Rules 1 and 3) because it is correct for every
other cache in the chain — browsers, corporate proxies, anything downstream that
does honour it. It is belt-and-braces, not the thing keeping this safe.

Agents that want Markdown can also be sent to `/index.md` and friends, which are
real files and cannot be confused for anything else.

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

**Rule 2 — canonical on Markdown responses.**
⚠️ **Not deployed. `regex_replace()` does not work on this free zone.**

Two separate rules needing it were built cleanly and both failed to save with no
error shown, while every static-value rule deployed first try. Do not spend time
debugging the expression syntax; the function itself is the problem. If you
retry after a plan change, note that Cloudflare treats a backslash as a string
escape, so the regex must be double-escaped -- the single-escaped form fails
with *expected ", xHH or OOO after \*.

This is polish, not a prerequisite: Rule 1's `noindex` already removes the
duplicate-content risk on its own. Anything needing a per-path value has to be
one static rule per path instead (see Rules 4 and 5).

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

**Rules 4 and 5 — Markdown content negotiation** (URL Rewrite Rules):

    Rule 4:  (http.request.uri.path eq "/"
              and any(http.request.headers["accept"][*] contains "text/markdown"))
             -> rewrite path to /index.md

    Rule 5:  (http.request.uri.path eq "/deals.html"
              and any(http.request.headers["accept"][*] contains "text/markdown"))
             -> rewrite path to /deals.md

**This is what makes Cloudflare's "Markdown Negotiation" check pass**, and the
panel's advice is misleading about it. That check does NOT test a Cloudflare
feature: it requests the page URL with `Accept: text/markdown` and looks at the
Content-Type it gets back. The "Requires Pro or higher" line in the remediation
text is static boilerplate shown regardless. bbi passes the same check with a
hand-built nginx `map $http_accept`, on no paid feature at all.

GitHub Pages cannot vary a response on a request header, so the negotiation has
to happen at the edge. The visitor's URL never changes; the origin serves the
`.md`, already as `text/markdown; charset=utf-8`.

Two consequences worth knowing before touching these:

- **The response-header rules see the REWRITTEN path.** A negotiated `GET /`
  matches `extension eq "md"` and therefore picks up Rule 1's `noindex`. That is
  correct and intended — `noindex` lands on the Markdown representation only,
  never on the HTML a search engine is served — but it means Rule 1 and these
  are coupled. Verified against production: a browser and Googlebot both get
  `text/html` with no `X-Robots-Tag`.
- **`Accept: */*` does not match.** curl's default and most naive clients still
  get HTML. Only an explicit `text/markdown` in Accept negotiates, which is what
  Claude Code's WebFetch sends.

Adding a page means adding a rule; there is no wildcard version, because that
would need `regex_replace()`. `/about.html`, `/join.html` and
`/birmingham-grocery-deals.html` do not negotiate — they are reachable as `.md`
twins at their own URLs, listed in llms.txt. Add rules if that stops being
enough; the cap is 10 Transform Rules and 5 are in use.


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
- **Cloudflare's "Markdown for Agents"** — the Pro-only feature. Not needed:
  Rules 4 and 5 satisfy the same check with a self-built implementation, exactly
  as bbi does. See the note there — the check tests real content negotiation,
  not whether you pay for their feature.

## Current score

Quick Wins **5/5**. Level 2 0/3 and Level 3 0/8 by design (no API, no login, no
agent to expose). Commerce 0/5 — nothing is for sale.

## Verifying

A config that parses proves nothing; check behaviour. After deploying, and after
any Cloudflare rule change:

    curl -sI https://magiccitysavers.com/index.md \
      | grep -iE 'content-type|x-robots-tag|link'
    curl -sI https://magiccitysavers.com/ \
      | grep -iE 'content-type|link|cf-cache-status'
    curl -s  https://magiccitysavers.com/robots.txt | grep -i content-signal

Expected: `.md` returns `text/markdown` and `noindex, follow`; HTML returns
`text/html`, the two `llms-txt` links and **no** `X-Robots-Tag`; both carry
`Vary: Accept`.

And the negotiation itself, which is the part worth re-checking after any rule
change — the second command must NOT return `text/markdown`:

    curl -sI -H 'Accept: text/markdown, */*' https://magiccitysavers.com/ | grep -i content-type
    curl -sI -H 'Accept: text/html'          https://magiccitysavers.com/ | grep -iE 'content-type|x-robots'

A browser or Googlebot receiving `noindex` on `/` would deindex the site. That
is the one failure mode here worth a deliberate check every time.

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
