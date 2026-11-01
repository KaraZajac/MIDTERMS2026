"""Values-only xlsx reading with the stdlib (zipfile + ElementTree) — enough
for the simple workbooks Silver Bulletin and the FEC publish. Same approach
as TOCSIN's reader, extended to pick a sheet by name."""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(ref: str) -> int:
    """'C5' -> 2"""
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
        else:
            break
    return n - 1


def sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
    return [s.get("name") for s in wb.iter(f"{NS}sheet")]


def _sheet_file(z: zipfile.ZipFile, name: str | None) -> str:
    if name is None:
        return min(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    for s in wb.iter(f"{NS}sheet"):
        if s.get("name") == name:
            t = target[s.get(f"{RNS}id")]
            return "xl/" + t.lstrip("/").removeprefix("xl/")
    raise KeyError(f"no sheet {name!r}")


def xlsx_rows(path: Path, sheet: str | None = None) -> list[list[str]]:
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{NS}t")) for si in root]
        root = ET.fromstring(z.read(_sheet_file(z, sheet)))
    rows = []
    for row in root.iter(f"{NS}row"):
        out: list[str] = []
        for c in row.iter(f"{NS}c"):
            idx = _col_index(c.get("r", ""))
            if c.get("t") == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(f"{NS}t"))
            else:
                v = c.find(f"{NS}v")
                val = "" if v is None or v.text is None else (
                    shared[int(v.text)] if c.get("t") == "s" else v.text)
            while len(out) < idx:
                out.append("")
            out.append(val)
        rows.append(out)
    return rows
