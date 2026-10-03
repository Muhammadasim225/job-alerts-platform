"""Turn downloaded advertisements into plain text.

Two tiers:
  1. PDFs: pdfplumber text extraction, page by page.
  2. Pages with (almost) no text, and image adverts (NTS portal ads are usually
     JPGs): Tesseract OCR. PDF pages are rendered with pypdfium2, so no poppler
     install is needed.

Tesseract is a system binary. In Docker it is installed in the image; on Windows
install it and set TESSERACT_CMD if it is not on PATH.
"""

import json
import re
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import config

log = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff"}
OCR_DPI = 300


class OcrUnavailable(RuntimeError):
    pass


@dataclass
class PageText:
    page: int
    method: str  # "text" | "ocr" | "text+ocr" | "empty"
    chars: int
    text: str


@dataclass
class ParsedDocument:
    path: str
    kind: str  # "pdf" | "image" | "docx"
    method: str  # "text" | "ocr" | "vlm" | "mixed" | "failed"
    pages: list[PageText] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Tables read structurally (Word tables, or HTML/Markdown tables from the VLM):
    # each table is a list of rows, each row a list of cell strings.
    tables: list[list[list[str]]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)

    def to_dict(self) -> dict:
        return {**asdict(self), "text": self.text}


def _tesseract():
    import pytesseract

    if config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
    try:
        pytesseract.get_tesseract_version()
    except (pytesseract.TesseractNotFoundError, OSError) as exc:
        raise OcrUnavailable(
            "Tesseract is not installed or not on PATH (set TESSERACT_CMD). "
            "Scanned PDFs and image adverts cannot be read without it."
        ) from exc
    return pytesseract


def ocr_image(image) -> str:
    """OCR a PIL image. Grayscale + upscale small images for better accuracy."""
    from PIL import ImageOps

    pytesseract = _tesseract()
    img = ImageOps.grayscale(image)
    if img.width < 1500:
        scale = 1500 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    # psm 4 = single column of variable-sized text; suits ad layouts better than the default
    return pytesseract.image_to_string(img, lang=config.OCR_LANGS, config="--psm 4")


def _line_key(line: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", line.lower())


def _looks_like_text(line: str) -> bool:
    """Filter OCR noise from logos/photos: mostly letters/digits and at least one real word."""
    line = line.strip()
    if len(line) < 4:
        return False
    good = sum(c.isalnum() or c in " .,:;()%/&+-'" for c in line)
    return good / len(line) >= 0.8 and re.search(r"[A-Za-z]{3,}", line) is not None


def merge_ocr_texts(primary: str, secondary: str) -> str:
    """primary + the lines of secondary it lacks (same de-dup and noise rules as the
    multi-pass banner OCR)."""
    from nts.advert_info import text_quality

    lines = primary.splitlines()
    seen = {_line_key(l) for l in lines if _line_key(l)}
    blob = _line_key(primary)
    extra = []
    for line in secondary.splitlines():
        key = _line_key(line)
        if not key or key in seen or key in blob or not _looks_like_text(line) or text_quality(line) < 0.8:
            continue
        seen.add(key)
        extra.append(line.strip())
    if extra:
        lines += ["", "[also read by Tesseract]", *extra]
    return "\n".join(lines)


def ocr_banner(image) -> str:
    """OCR designed banners (coloured backgrounds, white/yellow text on dark boxes).

    A single grayscale pass only reads dark-on-light text. Extra passes on a
    thresholded and an inverted-thresholded copy, in sparse-text mode, recover the
    headline text ("REGISTRATION OPEN", "SESSION 2026-27", "Age Limit: 14-35")
    that designed banners put on dark or coloured shapes. Lines are merged in
    reading order of the main pass, with new lines from the extra passes appended.
    """
    from PIL import Image, ImageOps

    pytesseract = _tesseract()
    gray = ImageOps.grayscale(image)
    if gray.width < 2000:
        scale = 2000 / gray.width
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS)

    main = pytesseract.image_to_string(gray, lang=config.OCR_LANGS, config="--psm 4")
    lines = [l.rstrip() for l in main.splitlines()]
    seen = {_line_key(l) for l in lines if _line_key(l)}

    extra: list[str] = []
    for variant in (
        gray.point(lambda v: 255 if v > 150 else 0),
        ImageOps.invert(gray).point(lambda v: 255 if v > 150 else 0),
    ):
        text = pytesseract.image_to_string(variant, lang=config.OCR_LANGS, config="--psm 11")
        for line in text.splitlines():
            key = _line_key(line)
            if not key or key in seen or not _looks_like_text(line):
                continue
            # Skip fragments of lines we already have ("REGISTRATION" inside "REGISTRATION OPEN")
            if len(key) >= 6 and any(key in s for s in seen):
                continue
            seen.add(key)
            extra.append(line.strip())

    if extra:
        lines += ["", "[extra OCR passes]", *extra]
    return "\n".join(lines).strip()


def _has_hollow_table(page) -> bool:
    """A ruled table whose cells are mostly empty: its text is drawn as vector
    outlines, so the page needs OCR even though the rest of it has real text.
    (Seen on NTS adverts, e.g. the ISMO June 2026 positions table.)"""
    for table in page.extract_tables():
        cells = [c for row in table for c in row]
        if len(table) >= 4 and len(cells) >= 8:
            empty = sum(1 for c in cells if not (c or "").strip())
            if empty / len(cells) > 0.8:
                return True
    return False


def parse_pdf(path: Path) -> ParsedDocument:
    import pdfplumber

    doc = ParsedDocument(path=str(path), kind="pdf", method="text")
    # page index -> "replace" (no usable text) or "append" (text layer is incomplete)
    ocr_pages: dict[int, str] = {}
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").strip()
            if len(text) < config.MIN_TEXT_CHARS_PER_PAGE:
                doc.pages.append(PageText(i + 1, "empty", len(text), text))
                ocr_pages[i] = "replace"
            else:
                doc.pages.append(PageText(i + 1, "text", len(text), text))
                if _has_hollow_table(page):
                    ocr_pages[i] = "append"

    if ocr_pages:
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(str(path))
            try:
                for i, mode in ocr_pages.items():
                    image = pdf[i].render(scale=OCR_DPI / 72).to_pil()
                    vlm_text = _vlm_page(image, doc)
                    label = "vlm" if vlm_text else "ocr"
                    text = vlm_text or ocr_image(image).strip()
                    if mode == "replace":
                        doc.pages[i] = PageText(i + 1, label, len(text), text)
                    elif text:
                        combined = f"{doc.pages[i].text}\n\n[{label.upper()}]\n{text}"
                        doc.pages[i] = PageText(i + 1, f"text+{label}", len(combined), combined)
            finally:
                pdf.close()
        except OcrUnavailable as exc:
            doc.warnings.append(str(exc))

    methods = {p.method for p in doc.pages if p.text and p.method != "empty"}
    if not methods:
        doc.method = "failed"
    elif methods == {"text"}:
        doc.method = "text"
    elif methods == {"ocr"}:
        doc.method = "ocr"
    elif methods == {"vlm"}:
        doc.method = "vlm"
    else:
        doc.method = "mixed"
    return doc


def parse_image(path: Path) -> ParsedDocument:
    from PIL import Image

    doc = ParsedDocument(path=str(path), kind="image", method="ocr")
    with Image.open(path) as img:
        img.load()
        image = img.convert("RGB")

    # Stylized banners: a vision-language model reads layout and tables far better
    # than Tesseract. Used only when configured; any failure falls back to Tesseract.
    vlm_text = _vlm_page(image, doc)
    if vlm_text:
        # The VLM reads layout far better but sometimes skips small badges
        # ("NASTP Kharian", "Merit Based Scholarship") that Tesseract does read, so
        # Tesseract's lines that the VLM missed are appended (free, local).
        try:
            vlm_text = merge_ocr_texts(vlm_text, ocr_banner(image))
        except OcrUnavailable:
            pass
        doc.method = "vlm"
        doc.pages.append(PageText(1, "vlm", len(vlm_text), vlm_text))
        return doc

    try:
        text = ocr_banner(image).strip()
        doc.pages.append(PageText(1, "ocr", len(text), text))
        if not text:
            doc.method = "failed"
    except OcrUnavailable as exc:
        doc.method = "failed"
        doc.warnings.append(str(exc))
    return doc


def _vlm_page(image, doc: "ParsedDocument") -> str | None:
    """VLM text for one page image, with its tables added to doc.tables; None if unavailable/failed."""
    from nts import vlm
    from nts.tables import markup_to_text, tables_from_markup

    if not vlm.vlm_available():
        return None
    try:
        raw = vlm.ocr_image(image)
    except Exception as exc:
        log.warning("VLM OCR failed, using Tesseract: %s", exc)
        doc.warnings.append(f"VLM OCR failed: {exc}")
        return None
    doc.tables.extend(tables_from_markup(raw))
    return markup_to_text(raw).strip() or None


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(path: Path) -> ParsedDocument:
    """Word files are zipped XML: read paragraphs and tables directly, no OCR needed."""
    import zipfile
    import xml.etree.ElementTree as ET

    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    body = root.find(f"{_W}body")

    def text_of(el) -> str:
        return " ".join("".join(t.text or "" for t in p.iter(f"{_W}t")) for p in el.iter(f"{_W}p")).strip()

    doc = ParsedDocument(path=str(path), kind="docx", method="text")
    lines: list[str] = []
    for el in body if body is not None else []:
        if el.tag == f"{_W}p":
            t = " ".join(text_of(el).split())
            if t:
                lines.append(t)
        elif el.tag == f"{_W}tbl":
            table = [[" ".join(text_of(tc).split()) for tc in tr.findall(f"{_W}tc")] for tr in el.findall(f"{_W}tr")]
            doc.tables.append(table)
            lines += [" | ".join(row) for row in table]
    text = "\n".join(lines)
    doc.pages.append(PageText(1, "text", len(text), text))
    if not text:
        doc.method = "failed"
    return doc


def parse_file(path: str | Path) -> ParsedDocument:
    path = Path(path)
    if not path.is_absolute():
        path = config.DATA_DIR / path
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return parse_pdf(path)
        if suffix == ".docx":
            return parse_docx(path)
        if suffix in IMAGE_SUFFIXES:
            return parse_image(path)
        return ParsedDocument(str(path), "unknown", "failed", warnings=[f"Unsupported file type {suffix}"])
    except Exception as exc:
        log.exception("Parsing failed for %s", path)
        return ParsedDocument(str(path), suffix.lstrip("."), "failed", warnings=[f"{type(exc).__name__}: {exc}"])


def save_parsed(listing_id: str, docs: list[ParsedDocument]) -> str:
    """Keep the extracted text next to the pipeline output for manual review."""
    folder = config.PARSED_DIR
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{listing_id}.json"
    out.write_text(json.dumps([d.to_dict() for d in docs], ensure_ascii=False, indent=2), encoding="utf8")
    return str(out.relative_to(config.DATA_DIR))


if __name__ == "__main__":
    # Manual check: uv run python -m nts.parser path/to/file.pdf
    import sys

    for arg in sys.argv[1:]:
        d = parse_file(arg)
        print(f"== {arg}  method={d.method}  pages={len(d.pages)}  warnings={d.warnings}")
        print(d.text[:3000])
