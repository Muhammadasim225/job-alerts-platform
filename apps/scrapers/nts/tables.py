"""Read the positions table out of a job advert image/PDF page.

Many adverts list posts in a ruled table ("Name of Post | Qualification | No. of
Positions | Age Limit | ..."). Whole-page OCR mixes those columns into unreadable
lines, so this module finds the table grid instead:

  1. OCR the page once for word positions, locate the "Name of Post" header.
  2. Detect the table's horizontal and vertical ruling lines from pixels.
  3. OCR each relevant cell on its own (post name, positions, age, experience,
     qualification, BPS).

Cells that span several rows (e.g. one "35 years" age cell for ten posts) are
detected per column, so every row gets the value of the cell it sits in.

Used only for job listings where the portal gave no structured posts.
"""

import logging
import re

log = logging.getLogger(__name__)

DARK = 150  # grayscale threshold for ruling lines (light-grey rules too)
RENDER_DPI = 300

NAME_HEADER_RE = re.compile(r"^(name|post|posts|designation|position)s?$", re.I)
# Admission adverts: "PROGRAMS | ELIGIBILITY CRITERIA", "Courses | Duration | ..."
PROGRAM_HEADER_RE = re.compile(r"^(programs?|programmes?|courses?|disciplines?)$", re.I)
COLUMN_HEADERS = {
    # "No. of Positions" / "No. of Posts" / "Vacancies" (not "No." alone: "Sr. No." exists too)
    "positions": re.compile(r"^(positions?|posts?|vacanc(y|ies)|seats?)$", re.I),
    "age": re.compile(r"^age$", re.I),
    "experience": re.compile(r"^experience$", re.I),
    "qualification": re.compile(r"^(qualifications?|eligibility|education)$", re.I),
    "bps": re.compile(r"^(bps|b\.p\.s\.?|grade|scale|pay)$", re.I),
}

# Common OCR slips in post names
_OCR_FIXES = [
    (re.compile(r"-(?:ll|Il|lI|il|1l|l1|11)\b"), "-II"),
    (re.compile(r"-(?:lll|IIl|Ill|111)\b"), "-III"),
    (re.compile(r"-(?:l|1|t|\|)\b"), "-I"),
    (re.compile(r"\bAnalvst\b"), "Analyst"),
    (re.compile(r"\s+([)/])"), r"\1"),
    (re.compile(r"([(/])\s+"), r"\1"),
]


def clean_post_name(name: str) -> str:
    name = " ".join(name.split())
    for pattern, repl in _OCR_FIXES:
        name = pattern.sub(repl, name)
    return name.strip(" -|")


_CELL_BULLET_RE = re.compile(r"(?:^|\s)[«»¢•·*~®©°]+\s+")  # not "+": "Intermediate + MS Office"


def clean_cell_text(text: str) -> str:
    """Undo line-wrap artefacts in long cells: 'HEC- recognized' -> 'HEC-recognized'.
    OCR'd bullet glyphs ('«', '¢', '+', '•') become ' • ' separators."""
    text = re.sub(r"(\w)- (\w)", r"\1-\2", " ".join(text.split()))
    text = re.sub(r"\s+[_|]\s+", " ", text)
    text = _CELL_BULLET_RE.sub(" • ", " " + text)
    # A bullet OCR'd as a letter after a full stop: "40% marks. e Age Limit"
    text = re.sub(r"(?<=[.)])\s+[eo]\s+(?=[A-Z])", " • ", text)
    text = re.sub(r"^[\s|•]+", "", text)  # stray table border / bullet at the start
    return text.strip(" •")


def cell_items(text: str) -> list[str]:
    """Split a bulleted cell into its items, dropping OCR garbage."""
    from nts.advert_info import text_quality

    text = re.sub(r"\)\s+\+\s+", ") • ", clean_cell_text(text))  # "...subjects) + Matrix ..." = two items
    items = [re.sub(r"^\+\s+", "", i).strip(" .;") for i in text.split(" • ")]
    return [i for i in items if len(i) > 2 and text_quality(i) >= 0.8]


_CONTACT_RE = re.compile(r"www\.|https?:|@|\.pk\b|\.com\b|(?:\d[\s-]?){7,}", re.I)


def _load_pages(path: str):
    from PIL import Image

    if path.lower().endswith(".pdf"):
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        try:
            return [pdf[i].render(scale=RENDER_DPI / 72).to_pil().convert("L") for i in range(len(pdf))]
        finally:
            pdf.close()
    with Image.open(path) as img:
        img = img.convert("L")
        if img.width < 1600:  # small JPG adverts: upscale so thin rules and text survive
            s = 1600 / img.width
            img = img.resize((int(img.width * s), int(img.height * s)))
        return [img.copy()]


class _Grid:
    def __init__(self, img):
        self.img = img
        self.px = img.load()
        self.w, self.h = img.size

    def hrules(self, x0: int, x1: int, y0: int, y1: int) -> list[int]:
        xs = range(max(0, x0), min(self.w, x1), 3)
        if not xs:
            return []
        out: list[int] = []
        for y in range(max(0, y0), min(self.h, y1)):
            if sum(self.px[x, y] < DARK for x in xs) > 0.85 * len(xs):
                if not out or y - out[-1] > 8:
                    out.append(y)
        return out

    def has_vline(self, x: int, y0: int, y1: int) -> bool:
        """Is there a vertical ruling line near x between y0 and y1?

        Per-row divider bars (drawn separately for each row, slightly offset, with
        gaps between rows) count too, so the test is generous in x and coverage."""
        ys = range(max(0, y0 + 3), min(self.h, y1 - 3), 2)
        if not ys:
            return False
        for xx in range(max(0, x - 12), min(self.w, x + 13)):
            if sum(self.px[xx, y] < DARK for y in ys) > 0.6 * len(ys):
                return True
        return False

    def text_blocks(self, x0: int, x1: int, y0: int, y1: int, min_gap: int = 28) -> list[tuple[int, int]]:
        """Vertical extents of the text blocks inside a cell, split on blank gaps.

        Used when two table rows share one band because the rule between them is
        too faint to detect: each row's text is a tight block, rows are separated
        by blank space."""
        xs = range(max(0, x0 + 8), min(self.w, x1 - 8), 2)
        if not xs:
            return [(y0, y1)]
        inked = [sum(self.px[x, y] < 128 for x in xs) > 1 for y in range(y0 + 3, y1 - 3)]
        blocks, start, blank = [], None, 0
        for i, ink in enumerate(inked):
            y = y0 + 3 + i
            if ink:
                if start is None:
                    start = y
                blank = 0
            elif start is not None:
                blank += 1
                if blank >= min_gap:
                    blocks.append((start, y - blank))
                    start, blank = None, 0
        if start is not None:
            blocks.append((start, y1 - 3 - blank))
        return blocks or [(y0, y1)]

    def vrules(self, y0: int, y1: int) -> list[int]:
        ys = range(max(0, y0), min(self.h, y1), 2)
        if not ys:
            return []
        out: list[int] = []
        for x in range(self.w):
            if sum(self.px[x, y] < DARK for y in ys) > 0.75 * len(ys):
                if not out or x - out[-1] > 8:
                    out.append(x)
        return out


def _words(img):
    import pytesseract

    # psm 11 (sparse text) reads table headers that the column-oriented modes skip
    # (e.g. "Name of the Post | BPS" on the WCLA advert was missed by psm 4)
    d = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
    return [
        {"t": d["text"][i].strip(), "x": d["left"][i], "y": d["top"][i], "w": d["width"][i], "h": d["height"][i]}
        for i in range(len(d["text"]))
        if d["text"][i].strip()
    ]


def _ocr(img, box, config="--psm 6") -> str:
    import pytesseract

    x0, y0, x1, y1 = box
    if x1 - x0 < 10 or y1 - y0 < 10:
        return ""
    return " ".join(pytesseract.image_to_string(img.crop(box), config=config).split())


def _table_on_page(img) -> list[dict]:
    words = _words(img)
    grid = _Grid(img)

    # "Name of Post": a name-ish header word with another header word on the same line
    header = None
    for w in words:
        if w["t"].lower() == "name" and any(
            o is not w and o["t"].lower().startswith(("post", "position", "designation")) and abs(o["y"] - w["y"]) < 20
            for o in words
        ):
            header = w
            break
    # Header words also occur in running text ("... on Diploma Programs", "Applications
    # are invited for the following positions"); the real header shares its line with
    # other column headers such as BPS / Age / Qualification / Eligibility.
    def header_score(w):
        return sum(
            1
            for o in words
            if o is not w and abs(o["y"] - w["y"]) < 25 and any(p.match(o["t"]) for p in COLUMN_HEADERS.values())
        )

    for pattern in (PROGRAM_HEADER_RE, NAME_HEADER_RE):
        if header is not None:
            break
        candidates = [(header_score(w), w) for w in words if pattern.match(w["t"]) and w["t"].lower() != "no."]
        candidates = [c for c in candidates if c[0] > 0]
        if candidates:
            header = max(candidates, key=lambda c: c[0])[1]
    if header is None:
        return []

    # Row boundaries: horizontal rules through the name column
    rows = grid.hrules(header["x"] + 10, header["x"] + max(header["w"], 120), header["y"], grid.h)
    if len(rows) < 3:
        return []
    # Column boundaries from the vertical rules of the first body row. Tables without
    # an outer border (only a divider between columns) use the image edges instead.
    first = next(((a, b) for a, b in zip(rows, rows[1:]) if b - a >= 40), None)
    if first is None:
        return []
    cols = grid.vrules(first[0] + 5, first[1] - 5)
    cols = sorted({0, *cols, grid.w - 1})
    if len(cols) < 3:
        return []

    def column_of(word):
        cx = word["x"] + word["w"] / 2
        return next(((a, b) for a, b in zip(cols, cols[1:]) if a < cx < b), None)

    name_col = column_of(header)
    if name_col is None:
        return []
    other_cols: dict[str, tuple[int, int]] = {}
    for key, pattern in COLUMN_HEADERS.items():
        for w in words:
            if abs(w["y"] - header["y"]) < 70 and pattern.match(w["t"]):
                c = column_of(w)
                if c and c != name_col:
                    other_cols.setdefault(key, c)
                    break

    # "Qualification and Experience" in one column: read it once, as qualification
    if other_cols.get("experience") and other_cols.get("experience") == other_cols.get("qualification"):
        del other_cols["experience"]

    # Each column has its own horizontal rules, which reveals merged cells
    col_rules = {key: grid.hrules(a + 15, b - 15, rows[0] - 3, rows[-1] + 3) for key, (a, b) in other_cols.items()}
    cell_cache: dict[tuple, str] = {}

    def cell_value(key: str, y_mid: float) -> tuple[str, bool]:
        rules = col_rules[key]
        for a, b in zip(rules, rules[1:]):
            if a < y_mid < b:
                box = (other_cols[key][0] + 4, a + 4, other_cols[key][1] - 4, b - 4)
                if box not in cell_cache:
                    cfg = "--psm 6 -c tessedit_char_whitelist=0123456789" if key == "positions" else "--psm 6"
                    cell_cache[box] = _ocr(img, box, cfg)
                spans_rows = sum(1 for r0, r1 in zip(rows, rows[1:]) if a <= r0 and r1 <= b + 2) > 1
                return cell_cache[box], spans_rows
        return "", False

    # Row bands; a band whose name cell holds several separate text blocks is really
    # several rows with a too-faint rule between them, so it is split on the gaps.
    bands: list[tuple[int, int, bool]] = []
    for top, bottom in zip(rows, rows[1:]):
        if bottom - top < 40:  # the table ended (double rule / next section)
            break
        # Past the table's bottom edge the column divider stops; text or a footer box
        # below the table must not be read as a row.
        if not grid.has_vline(name_col[1], top, bottom):
            break
        blocks = grid.text_blocks(name_col[0], name_col[1], top, bottom)
        if len(blocks) < 2:
            bands.append((top, bottom, False))
            continue
        # Cut inside each blank gap of the name column, at the y where the other
        # columns have the least ink, so no cell's text is sliced in half.
        others = [c for c in other_cols.values()]

        def ink_at(y: int) -> int:
            return sum(
                sum(grid.px[x, y] < 128 for x in range(a + 8, b - 8, 3)) for a, b in others
            )

        cuts = [top]
        for a, b in zip(blocks, blocks[1:]):
            gap = range(a[1] + 2, b[0] - 1)
            cuts.append(min(gap, key=ink_at) if len(gap) else (a[1] + b[0]) // 2)
        cuts.append(bottom)
        bands.extend((a, b, True) for a, b in zip(cuts, cuts[1:]))

    def value(key: str, top: int, bottom: int, split: bool) -> tuple[str, bool]:
        if not split:
            return cell_value(key, (top + bottom) / 2)
        # No rule to go by: read this column within the row's own band
        x0, x1 = other_cols[key]
        cfg = "--psm 6 -c tessedit_char_whitelist=0123456789" if key == "positions" else "--psm 6"
        return _ocr(img, (x0 + 4, top + 2, x1 - 4, bottom - 2), cfg), False

    results = []
    for top, bottom, split in bands:
        name = clean_post_name(_ocr(img, (name_col[0] + 4, top + 4, name_col[1] - 4, bottom - 4)))
        if len(name) < 3 or name.lower().startswith("name of"):
            continue
        if _CONTACT_RE.search(name):
            break  # the contact strip under the table (phones, website) is not a row
        row = {"name": name}
        if "positions" in other_cols:
            val, shared = value("positions", top, bottom, split)
            m = re.search(r"\d+", val)
            if m:
                row["total_posts"] = int(m.group())
                row["total_posts_shared"] = shared
        if "age" in other_cols:
            val, _ = value("age", top, bottom, split)
            if re.search(r"\d", val):
                row["age_limit"] = val
        if "experience" in other_cols:
            val, _ = value("experience", top, bottom, split)
            if val:
                row["experience"] = clean_cell_text(val)
        if "qualification" in other_cols:
            val, _ = value("qualification", top, bottom, split)
            if val:
                row["qualification"] = clean_cell_text(val)
        if "bps" in other_cols:
            val, _ = value("bps", top, bottom, split)
            grade = re.search(r"\d{1,2}", val)
            if grade:
                row["details"] = "BPS-" + grade.group()
        results.append(row)
    return results


# --- tables already in text form (VLM output, Word files) -----------------------------

def tables_from_markup(text: str) -> list[list[list[str]]]:
    """HTML <table> and Markdown pipe tables in OCR/VLM output -> [[cells]] per table.
    Row/col spans are expanded so every row has its value (like merged PDF cells)."""
    from parsel import Selector

    tables: list[list[list[str]]] = []
    if "<table" in text.lower():
        for t in Selector(text=text).css("table"):
            grid: list[list[str]] = []
            pending: dict[tuple[int, int], str] = {}  # (row, col) filled by a rowspan above
            for r, tr in enumerate(t.css("tr")):
                row: list[str] = []
                c = 0
                for cell in tr.css("th, td"):
                    while (r, c) in pending:
                        row.append(pending.pop((r, c)))
                        c += 1
                    value = " ".join(" ".join(cell.xpath(".//text()").getall()).split())
                    rowspan = int(cell.attrib.get("rowspan", "1") or 1)
                    colspan = int(cell.attrib.get("colspan", "1") or 1)
                    for _ in range(colspan):
                        row.append(value)
                        for k in range(1, rowspan):
                            pending[(r + k, c)] = value
                        c += 1
                while (r, c) in pending:
                    row.append(pending.pop((r, c)))
                    c += 1
                grid.append(row)
            if grid:
                tables.append(grid)

    block: list[list[str]] = []
    for line in text.splitlines() + [""]:
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):  # skip |---|---|
                block.append(cells)
        elif block:
            tables.append(block)
            block = []
    return tables


def markup_to_text(text: str) -> str:
    """Readable text for fact extraction: table rows as 'a | b | c', tags removed.
    Nanonets describes pictures and logos inside <img>...</img>; those descriptions
    ("A person in a blue uniform ...") are not advert text and are dropped."""
    text = re.sub(r"<img>.*?</img>", "\n", text, flags=re.I | re.S)
    text = re.sub(r"<(watermark|page_number)>.*?</\1>", "\n", text, flags=re.I | re.S)
    text = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", " | ", text, flags=re.I)
    text = re.sub(r"</tr>|<br\s*/?>|</p>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return "\n".join(" ".join(l.split()) for l in text.splitlines() if l.strip())


_HEADER_RES = {
    "name": re.compile(r"name of (the )?posts?|^posts?\b|designation|position|^programs?|programmes?|courses?|discipline", re.I),
    "positions": re.compile(r"no\.? of (posts?|positions?|seats?)|vacanc|positions?$|seats?$", re.I),
    "age": re.compile(r"\bage\b", re.I),
    # before "experience": "Qualification and Experience" is one qualification column
    "qualification": re.compile(r"qualification|eligibility|education", re.I),
    "experience": re.compile(r"experience", re.I),
    "bps": re.compile(r"\b(bps|b\.p\.s|grade|scale|pay)\b", re.I),
}


def _table_header(table: list[list[str]]) -> tuple[int, dict] | None:
    """(header row index, {field: column}) when the table has a post/programme header."""
    for i, row in enumerate(table[:3]):
        found: dict[str, int] = {}
        for j, cell in enumerate(row):
            for key, pattern in _HEADER_RES.items():
                if key not in found and pattern.search(cell or ""):
                    found[key] = j
                    break
        if "name" in found and len(found) >= 2:
            return i, found
    return None


def merge_continued_tables(tables: list[list[list[str]]]) -> list[list[list[str]]]:
    """A table cut across two OCR strips arrives as two tables, the second without a
    header; append such headerless parts to the table before them (same width)."""
    merged: list[list[list[str]]] = []
    for table in tables:
        if (
            merged
            and table
            and _table_header(table) is None
            and _table_header(merged[-1]) is not None
            and abs(len(table[0]) - len(merged[-1][0])) <= 1
        ):
            merged[-1] = merged[-1] + table
        else:
            merged.append(table)
    return merged


def rows_from_tables(tables: list[list[list[str]]]) -> list[dict]:
    """Post/programme rows (same shape as extract_post_table) from structured tables."""
    rows: list[dict] = []
    for table in merge_continued_tables(tables):
        header = _table_header(table)
        if header is None:
            continue
        header_i, cols = header
        # "Qualification and Experience" in one column: keep it as qualification
        if "experience" in cols and cols.get("experience") == cols.get("qualification"):
            cols.pop("experience")
        for row in table[header_i + 1 :]:
            get = lambda k: (row[cols[k]] if k in cols and cols[k] < len(row) else "").strip()  # noqa: E731
            name = clean_post_name(get("name"))
            if len(name) < 3 or _CONTACT_RE.search(name) or re.fullmatch(r"(total|grand total)\W*", name, re.I):
                continue
            item: dict = {"name": name}
            m = re.search(r"\d+", get("positions"))
            if m:
                item["total_posts"] = int(m.group())
            if re.search(r"\d", get("age")):
                item["age_limit"] = get("age")
            if get("experience"):
                item["experience"] = clean_cell_text(get("experience"))
            if get("qualification"):
                item["qualification"] = clean_cell_text(get("qualification"))
            grade = re.search(r"\d{1,2}", get("bps"))
            if grade:
                item["details"] = "BPS-" + grade.group()
            if rows and rows[-1]["name"] == name and all(rows[-1].get(k) in (None, v) for k, v in item.items()):
                continue  # strip overlap / rowspan repeat of the same row
            rows.append(item)
    return rows


def extract_post_table(path: str) -> list[dict]:
    """Posts found in the advert's positions table(s); [] when there is no such table."""
    posts: list[dict] = []
    try:
        for img in _load_pages(path):
            posts.extend(_table_on_page(img))
    except Exception:
        log.exception("Table extraction failed for %s", path)
    return posts
