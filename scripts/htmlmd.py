#!/usr/bin/env python3
"""Turn one of this site's hand-written HTML pages into Markdown.

Written for THIS site's markup, not as a general converter. The pages are
hand-authored and consistent: every piece of prose lives in an <h1>-<h6>, a <p>
or an <li>, and everything else is layout. So the rule is simple -- those three
are the only tags that emit text, and every other element is transparent.

That rule has a failure mode worth stating plainly, because it is the one that
bites: text added to a page OUTSIDE those tags does not appear in the Markdown.
On a sibling project that happened silently and the twins quietly lost content
for weeks. Here it does not: to_markdown() returns every non-whitespace run it
skipped, build_seo.py prints them, and you find out on the same run.

Site chrome (the logo/nav header, the footer, the <nav> bar) is dropped on
purpose -- it is identical on every page and repeating it five times in
llms-full.txt is noise an agent has to read past. about.html's bare <header>,
which holds the page's real <h1>, is kept: only <header class="header"> is
chrome.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

# Dropped whole, contents and all.
SKIP = {"script", "style", "nav", "footer", "svg", "form", "head"}

# Navigation affordances that happen to sit outside <nav>. They are controls,
# not prose: "← Back to Magic City Savers" is a thing to click on a rendered
# page and noise in a document being read detached from one. Listed explicitly
# so the dropped-text report stays empty on a clean build -- a warning that
# fires every single run is one you stop reading, which defeats the point of
# having it.
CHROME_CLASSES = {"back-btn"}

BLOCK = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}

HEADING = {f"h{n}": "#" * n for n in range(1, 7)}

# Never carry an end tag, so they must not move the depth counter.
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class _Converter(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.out = []          # finished markdown blocks
        self.buf = []          # text of the block being built
        self.block = None      # tag name of the open block, or None
        self.depth = 0         # open non-void elements
        self.skip_from = None  # self.depth at which the current skip began
        self.href = None       # href of the <a> currently open
        self.link_start = None # len(self.buf) when that <a> opened
        self.lost = []         # non-whitespace text dropped outside a block

    # -- helpers ---------------------------------------------------------

    @property
    def skipping(self):
        return self.skip_from is not None

    def _flush(self):
        if self.block is None:
            return
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        # The ✓ that opens every benefit-item is decoration; the bullet already
        # says "this is one of a list".
        text = text.lstrip("✓").strip()
        if text:
            if self.block in HEADING:
                self.out.append(f"{HEADING[self.block]} {text}")
            elif self.block == "li":
                self.out.append(f"- {text}")
            else:
                self.out.append(text)
        self.buf = []
        self.block = None

    def _chrome(self, tag, attrs):
        """Site furniture: the repeated logo/nav header, or a nav control.

        A bare <header> is a real page header (about.html keeps its <h1> in
        one); only <header class="header"> is the shared chrome.
        """
        classes = set(dict(attrs).get("class", "").split())
        if tag == "header":
            return "header" in classes
        return bool(classes & CHROME_CLASSES)

    # -- parser callbacks ------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            if tag == "br" and not self.skipping and self.block is not None:
                self.buf.append(" ")
            return

        # Depth is tracked even inside a skipped subtree: it is what tells the
        # matching end tag where the skip stops. Keying off the tag NAME breaks
        # as soon as a skipped <a class="back-btn"> sits inside kept markup.
        self.depth += 1
        if self.skipping:
            return
        if tag in SKIP or self._chrome(tag, attrs):
            self._flush()
            self.skip_from = self.depth
            return

        if tag in BLOCK:
            # <li> wraps <div class="benefit-text">; a nested block would
            # otherwise split one bullet across two lines.
            if self.block is None:
                self._flush()
                self.block = tag
            return

        if tag in ("ul", "ol"):
            self._flush()
        elif tag == "a":
            self.href = dict(attrs).get("href")
            self.link_start = len(self.buf)
        elif tag in ("strong", "b"):
            self.buf.append("**")
        elif tag in ("em", "i"):
            self.buf.append("*")

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.skipping:
            if self.depth == self.skip_from:
                self.skip_from = None
            self.depth -= 1
            return
        self.depth -= 1

        if tag in BLOCK:
            if self.block == tag:
                self._flush()
        elif tag == "a":
            self._close_link()
        elif tag in ("strong", "b"):
            self.buf.append("**")
        elif tag in ("em", "i"):
            self.buf.append("*")

    def _close_link(self):
        if self.href is None:
            return
        href, start, self.href = self.href, self.link_start, None
        text = "".join(self.buf[start:]).strip()
        if not text:
            return
        # Relative hrefs have to become absolute: the twins are read detached
        # from the site, and "deals.html" resolves against whatever the reader
        # happens to think the base is.
        if href.startswith("#"):
            return
        url = urljoin(self.base, href)
        del self.buf[start:]
        self.buf.append(f"[{text}]({url})")

    def handle_data(self, data):
        if self.skipping:
            return
        if self.block is not None:
            self.buf.append(data)
        elif data.strip() and re.search(r"\w", data):
            # Symbol-only runs -- the 🛒 and 🍽️ card glyphs -- are decoration,
            # and reporting them on every build is how a warning becomes
            # something you stop reading. Anything with a word character in it
            # is potentially prose that has gone missing, so that still reports.
            self.lost.append(data.strip())

    def close(self):
        super().close()
        self._flush()


def _join(blocks):
    """Blank line between blocks, single newline between sibling bullets."""
    out = ""
    for i, b in enumerate(blocks):
        if i:
            both_items = b.startswith("- ") and blocks[i - 1].startswith("- ")
            out += "\n" if both_items else "\n\n"
        out += b
    return out


def to_markdown(source, base_url):
    """Return (markdown, dropped) for one HTML page."""
    c = _Converter(base_url)
    c.feed(source)
    c.close()
    return _join(c.out).strip() + "\n", c.lost
