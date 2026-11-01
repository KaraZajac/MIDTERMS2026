"""A small, dependency-free HTML table extractor for MediaWiki output.

Wikipedia is where 2026 polls, ratings and candidate lists are compiled
under an open license, but its tables are hostile to naive parsing: cells
span rows and columns, sort keys hide in display:none spans, footnote
markers sit inside numbers, and the meaning of a table depends on the
section heading above it. This module turns rendered HTML into a list of
Table objects with

  - the heading path in force where the table starts (h2 > h3 > h4 > h5),
  - the caption and CSS classes,
  - raw rows of Cells (text, header flag, spans, attributes, link titles),
  - grid(): rows with rowspan/colspan expanded, so column j means the same
    thing on every row.

Footnotes (sup.reference), edit links, hidden sort keys, style and script
are dropped from cell text. Nested tables are captured as their own Table
and do not leak text into the enclosing cell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
SKIP_TAGS = {"style", "script", "noscript"}
SKIP_CLASSES = {"reference", "mw-editsection", "sortkey", "mw-ref", "noprint-ref",
                "mw-cite-backlink", "reflist"}
_WS = re.compile(r"\s+")
MAX_SPAN = 400
LS = " "          # internal line separator inside cell text
BLOCK = {"div", "p", "li", "ul", "ol", "dd", "dt"}


@dataclass
class Cell:
    text: str = ""
    header: bool = False
    rowspan: int = 1
    colspan: int = 1
    attrs: dict = field(default_factory=dict)
    links: list = field(default_factory=list)   # (title, href) of <a> inside
    bold: bool = False                            # any <b> text in the cell
    lines: list = field(default_factory=list)    # text split at <br>/<div>/<p>/<li>
    refs: list = field(default_factory=list)     # footnote ids cited in the cell ('cite_note-…')

    def __repr__(self) -> str:  # compact, for debugging
        tag = "th" if self.header else "td"
        return f"<{tag} {self.text!r}>"


@dataclass
class Table:
    headings: tuple            # (h2, h3, h4, h5) text in force at table start
    caption: str = ""
    classes: tuple = ()
    rows: list = field(default_factory=list)      # list[list[Cell]]
    index: int = 0                                 # document order
    hidden: str = ""      # title of an enclosing collapsed block ("Hypothetical polling")

    def grid(self) -> list[list[Cell | None]]:
        return expand(self.rows)

    def texts(self) -> list[list[str]]:
        return [[(c.text if c else "") for c in row] for row in self.grid()]

    @property
    def heading(self) -> str:
        return " > ".join(h for h in self.headings if h)


def expand(rows: list[list[Cell]]) -> list[list[Cell | None]]:
    """Expand rowspan/colspan into a rectangular-ish grid."""
    grid: list[list[Cell | None]] = []
    carry: dict[int, list] = {}   # col -> [remaining_rows, cell]
    for row in rows:
        out: list[Cell | None] = []
        it = iter(row)
        nxt = next(it, None)
        col = 0
        while nxt is not None or any(k >= col for k in carry):
            if col in carry:
                slot = carry[col]
                out.append(slot[1])
                slot[0] -= 1
                if slot[0] <= 0:
                    del carry[col]
                col += 1
                continue
            if nxt is None:
                out.append(None)
                col += 1
                continue
            span = max(1, min(nxt.colspan, 64))
            for _ in range(span):
                if col in carry:          # malformed overlap: carried cell wins
                    break
                out.append(nxt)
                if nxt.rowspan > 1:
                    carry[col] = [min(nxt.rowspan, MAX_SPAN) - 1, nxt]
                col += 1
            nxt = next(it, None)
        grid.append(out)
    return grid


def _int_attr(v: str | None) -> int:
    if not v:
        return 1
    m = re.match(r"\s*(\d+)", v)
    return int(m.group(1)) if m else 1


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._open: list[dict] = []          # stack of open tables (state dicts)
        self._elems: list[tuple[str, bool]] = []   # (tag, skipping)
        self._heads = ["", "", "", ""]       # h2..h5
        self._hidden: list[str] = []         # titles of open hidden-begin blocks
        self._title_buf: list[str] | None = None
        self._head_level: int | None = None
        self._head_buf: list[str] = []
        self._count = 0

    # -- helpers
    def _skipping(self) -> bool:
        return bool(self._elems) and bool(self._elems[-1][1])

    def _cur_table(self) -> dict | None:
        return self._open[-1] if self._open else None

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        if tag == "a" and attrs.get("href", "").startswith("#cite_note"):
            # footnote markers are hidden from the text, but which reference a
            # cell cites is what links a poll row to its source
            st0 = self._cur_table()
            if st0 is not None and st0["cell"] is not None:
                st0["cell"].refs.append(attrs["href"][1:])
        classes = set(attrs.get("class", "").split())
        style = attrs.get("style", "").replace(" ", "").lower()
        skip = (self._skipping() or tag in SKIP_TAGS or bool(classes & SKIP_CLASSES)
                or "display:none" in style)

        if tag in VOID:
            if tag == "br" and not skip:
                self._text(LS)
            return
        if tag in BLOCK and not skip:
            self._text(LS)
        self._elems.append((tag, skip))
        if skip:
            return
        if tag == "div" and "hidden-begin" in classes:
            self._elems[-1] = (tag, skip, "hidden")
            self._hidden.append("")
        elif tag == "div" and "hidden-title" in classes and self._hidden:
            self._elems[-1] = (tag, skip, "title")
            self._title_buf = []

        if tag in ("h2", "h3", "h4", "h5"):
            self._head_level = int(tag[1])
            self._head_buf = []
            return

        if tag == "table":
            self._count += 1
            t = Table(headings=tuple(self._heads), classes=tuple(sorted(classes)),
                      index=self._count, hidden=(self._hidden[-1] or "hidden") if self._hidden else "")
            self._open.append({"table": t, "row": None, "cell": None,
                               "in_caption": False, "depth": len(self._elems)})
            return

        st = self._cur_table()
        if st is None:
            return
        if tag == "caption":
            st["in_caption"] = True
        elif tag == "tr":
            st["row"] = []
            st["table"].rows.append(st["row"])
            st["cell"] = None
        elif tag in ("td", "th"):
            if st["row"] is None:            # cell without <tr>
                st["row"] = []
                st["table"].rows.append(st["row"])
            c = Cell(header=(tag == "th"), rowspan=_int_attr(attrs.get("rowspan")),
                     colspan=_int_attr(attrs.get("colspan")), attrs=attrs)
            st["row"].append(c)
            st["cell"] = c
        elif tag == "a" and st["cell"] is not None:
            st["cell"].links.append((attrs.get("title", ""), attrs.get("href", "")))
        elif tag == "b" and st["cell"] is not None:
            st["cell"]._in_b = getattr(st["cell"], "_in_b", 0) + 1

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        # pop to the matching element (tolerates unclosed children)
        idx = None
        for i in range(len(self._elems) - 1, -1, -1):
            if self._elems[i][0] == tag:
                idx = i
                break
        if idx is None:
            return
        was_skipping = self._elems[idx][1]
        popped = self._elems[idx:]
        del self._elems[idx:]
        for e in popped:
            if len(e) > 2 and e[2] == "hidden" and self._hidden:
                self._hidden.pop()
            elif len(e) > 2 and e[2] == "title" and self._title_buf is not None:
                if self._hidden:
                    self._hidden[-1] = _WS.sub(" ", "".join(self._title_buf)).strip()
                self._title_buf = None
        if was_skipping:
            return
        if tag in BLOCK:
            self._text(LS)

        if tag in ("h2", "h3", "h4", "h5") and self._head_level == int(tag[1]):
            text = _WS.sub(" ", "".join(self._head_buf)).strip()
            lvl = self._head_level - 2
            self._heads[lvl] = text
            for j in range(lvl + 1, 4):
                self._heads[j] = ""
            self._head_level = None
            return

        st = self._cur_table()
        if st is None:
            return
        if tag == "table":
            t = self._open.pop()["table"]
            for row in t.rows:
                for c in row:
                    raw = c.text.replace("\u00a0", " ")
                    c.lines = [ln for ln in (_WS.sub(" ", x).strip() for x in raw.split(LS)) if ln]
                    c.text = " ".join(c.lines)
                    if hasattr(c, "_in_b"):
                        del c._in_b
            t.caption = _WS.sub(" ", t.caption).strip()
            self.tables.append(t)
        elif tag == "caption":
            st["in_caption"] = False
        elif tag in ("td", "th"):
            st["cell"] = None
        elif tag == "tr":
            st["row"] = None
            st["cell"] = None
        elif tag == "b" and st["cell"] is not None and getattr(st["cell"], "_in_b", 0):
            st["cell"]._in_b -= 1

    def _text(self, data: str) -> None:
        if self._title_buf is not None:
            self._title_buf.append(data)
            return
        if self._head_level is not None:
            self._head_buf.append(data)
            return
        st = self._cur_table()
        if st is None:
            return
        if st["in_caption"]:
            st["table"].caption += data
        elif st["cell"] is not None:
            st["cell"].text += data
            if getattr(st["cell"], "_in_b", 0) and data.strip():
                st["cell"].bold = True

    def handle_data(self, data: str) -> None:
        if self._skipping():
            return
        self._text(data)


def extract_tables(html: str) -> list[Table]:
    """All tables in document order of their *closing* tag (inner first)."""
    p = _Extractor()
    p.feed(html)
    p.close()
    return sorted(p.tables, key=lambda t: t.index)


def wikitables(html: str) -> list[Table]:
    return [t for t in extract_tables(html) if "wikitable" in t.classes]


class _RefExtractor(HTMLParser):
    """id -> first external URL for every <li id="cite_note-…"> in the page's
    reference lists (where Wikipedia keeps each poll's source link)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: dict[str, str] = {}
        self._stack: list[tuple[str, str | None]] = []   # (tag, cite id if li)

    def _current(self) -> str | None:
        for tag, cid in reversed(self._stack):
            if cid:
                return cid
        return None

    def handle_starttag(self, tag, attrs_list):
        attrs = {k: (v or "") for k, v in attrs_list}
        if tag in VOID:
            return
        cid = attrs.get("id") if tag == "li" and attrs.get("id", "").startswith("cite_note") else None
        self._stack.append((tag, cid))
        if tag == "a":
            cur = self._current()
            href = attrs.get("href", "")
            if cur and cur not in self.urls and href.startswith("http") and \
                    "external" in attrs.get("class", ""):
                self.urls[cur] = href

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                return


def references(html: str) -> dict:
    p = _RefExtractor()
    p.feed(html)
    p.close()
    return p.urls
