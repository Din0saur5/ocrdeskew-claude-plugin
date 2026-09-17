"""PDF page counting, splitting and merging for the Shotgun Method.

`qpdf` is preferred because it survives damaged scanner output that pure-Python
readers reject; `pypdf` is the fallback so the skill still works without
Homebrew. Every merge is verified against the original page count before any
result is allowed near a source file.
"""

import logging
import shutil
import subprocess
from pathlib import Path

# pypdf narrates damaged files on stderr; we report those failures ourselves.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic"}
SUPPORTED_SUFFIXES = PDF_SUFFIXES | IMAGE_SUFFIXES

QPDF = shutil.which("qpdf")


class PdfError(RuntimeError):
    """Raised when a PDF cannot be read, split or merged."""


def is_pdf(path):
    return Path(path).suffix.lower() in PDF_SUFFIXES


def _run(cmd, timeout=300):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise PdfError(f"{cmd[0]} failed: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc.stdout


def page_count(path):
    """Number of pages in a PDF. Images count as one page."""
    path = Path(path)
    if not is_pdf(path):
        return 1
    if QPDF:
        try:
            return int(_run([QPDF, "--show-npages", str(path)], timeout=60).strip())
        except (PdfError, ValueError, subprocess.SubprocessError):
            pass  # Fall through to pypdf rather than failing the whole batch.
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise PdfError(
            f"cannot read page count for {path.name}: qpdf unavailable and pypdf not installed"
        ) from exc
    try:
        return len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise PdfError(f"cannot read page count for {path.name}: {exc}") from exc


def page_ranges(total_pages, chunk_size):
    """Split a page count into inclusive 1-based (start, end) ranges."""
    ranges = []
    start = 1
    while start <= total_pages:
        end = min(start + chunk_size - 1, total_pages)
        ranges.append((start, end))
        start = end + 1
    return ranges


def split_pdf(source, ranges, dest_dir):
    """Write one chunk PDF per page range. Returns the chunk paths in order."""
    source, dest_dir = Path(source), Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    chunks = []

    if QPDF:
        for index, (start, end) in enumerate(ranges):
            chunk = dest_dir / f"{source.stem}__chunk{index:04d}.pdf"
            _run([QPDF, "--empty", "--pages", str(source), f"{start}-{end}", "--", str(chunk)])
            chunks.append(chunk)
        return chunks

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    for index, (start, end) in enumerate(ranges):
        chunk = dest_dir / f"{source.stem}__chunk{index:04d}.pdf"
        writer = PdfWriter()
        for page_no in range(start - 1, end):
            writer.add_page(reader.pages[page_no])
        with open(chunk, "wb") as handle:
            writer.write(handle)
        chunks.append(chunk)
    return chunks


def merge_pdfs(chunks, dest):
    """Concatenate chunk PDFs, preserving each chunk's OCR text layer."""
    chunks = [Path(c) for c in chunks]
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if QPDF:
        cmd = [QPDF, "--empty", "--pages"]
        for chunk in chunks:
            cmd += [str(chunk), "1-z"]
        cmd += ["--", str(dest)]
        _run(cmd, timeout=900)
        return dest

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for chunk in chunks:
        for page in PdfReader(str(chunk)).pages:
            writer.add_page(page)
    with open(dest, "wb") as handle:
        writer.write(handle)
    return dest


def verify_pdf(path, expected_pages=None):
    """Sanity-check a produced PDF. Returns (ok, reason)."""
    path = Path(path)
    if not path.exists():
        return False, "output file was not created"
    if path.stat().st_size == 0:
        return False, "output file is empty"
    try:
        with open(path, "rb") as handle:
            if handle.read(5) != b"%PDF-":
                return False, "output is not a PDF"
    except OSError as exc:
        return False, f"output unreadable: {exc}"
    if expected_pages is None:
        return True, "ok"
    try:
        actual = page_count(path)
    except PdfError as exc:
        return False, f"page count unreadable: {exc}"
    if actual != expected_pages:
        return False, f"page count mismatch: expected {expected_pages}, got {actual}"
    return True, "ok"
