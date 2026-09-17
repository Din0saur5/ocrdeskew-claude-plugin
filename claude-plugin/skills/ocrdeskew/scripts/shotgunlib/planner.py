"""Work-unit planning: turn a list of inputs into parallelizable units.

Two levels of fan-out:

1. **File level** — when there are already more files than workers, each file is
   one unit. Nothing is split, so nothing has to be stitched back together.
2. **Page level** — when a few large PDFs would otherwise leave most workers
   idle, the biggest PDFs are split into page-range chunks until there is
   enough work to saturate the machine.

Page-level splitting is only worth its merge risk when it actually buys
parallelism, so the planner reaches for it last.
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import pdfops

# Chunks smaller than this spend more time on process startup than on OCR.
MIN_CHUNK_PAGES = 2
MAX_CHUNK_PAGES = 40
# Aim for this many units per worker so slow pages cannot strand a core.
UNITS_PER_WORKER = 2


@dataclass
class WorkUnit:
    """One `ocrdeskew` invocation."""
    source: Path
    path: Path                      # What the worker actually reads (source or chunk).
    index: int = 0                  # Chunk ordinal within the source.
    page_range: tuple = None        # None when the whole file is one unit.
    pages: int = 1


@dataclass
class SourcePlan:
    source: Path
    pages: int
    is_pdf: bool
    split: bool = False
    units: list = field(default_factory=list)
    error: str = None


def expand_inputs(inputs, recursive=False):
    """Resolve paths and directories into a sorted list of supported files.

    Returns (files, missing_paths).
    """
    files, missing = [], []
    for raw in inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            missing.append(str(path))
            continue
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for child in sorted(path.glob(pattern)):
                if child.is_file() and child.suffix.lower() in pdfops.SUPPORTED_SUFFIXES:
                    files.append(child.resolve())
            continue
        files.append(path.resolve())

    seen, unique = set(), []
    for path in files:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique, missing


def _chunk_size(pages, target_chunks):
    """Pages per chunk that yields roughly `target_chunks` chunks."""
    size = max(MIN_CHUNK_PAGES, -(-pages // max(1, target_chunks)))
    return min(size, MAX_CHUNK_PAGES)


def build_plan(files, workers, allow_split=True):
    """Build a SourcePlan per file, splitting large PDFs only when it helps."""
    plans = []
    for path in files:
        try:
            pages = pdfops.page_count(path)
            plans.append(SourcePlan(source=path, pages=pages, is_pdf=pdfops.is_pdf(path)))
        except pdfops.PdfError as exc:
            plans.append(SourcePlan(source=path, pages=0, is_pdf=True, error=str(exc)))

    healthy = [p for p in plans if p.error is None]
    target_units = workers * UNITS_PER_WORKER
    unit_total = len(healthy)

    if allow_split and unit_total < target_units:
        # Split the page-heaviest PDFs first — they are what is stranding cores.
        candidates = sorted(
            (p for p in healthy if p.is_pdf and p.pages >= MIN_CHUNK_PAGES * 2),
            key=lambda p: p.pages,
            reverse=True,
        )
        for plan in candidates:
            if unit_total >= target_units:
                break
            deficit = target_units - unit_total + 1
            size = _chunk_size(plan.pages, min(deficit, plan.pages // MIN_CHUNK_PAGES))
            ranges = pdfops.page_ranges(plan.pages, size)
            if len(ranges) < 2:
                continue
            plan.split = True
            plan.units = [
                WorkUnit(source=plan.source, path=plan.source, index=i,
                         page_range=r, pages=r[1] - r[0] + 1)
                for i, r in enumerate(ranges)
            ]
            unit_total += len(ranges) - 1

    for plan in healthy:
        if not plan.units:
            plan.units = [WorkUnit(source=plan.source, path=plan.source, pages=plan.pages)]

    return plans


def summarize(plans, workers):
    """Human-readable plan summary, plus the counts a caller may want."""
    healthy = [p for p in plans if p.error is None]
    unreadable = [p for p in plans if p.error is not None]
    split_plans = [p for p in healthy if p.split]
    units = sum(len(p.units) for p in healthy)
    pages = sum(p.pages for p in healthy)
    return {
        "files": len(healthy),
        "unreadable": len(unreadable),
        "pages": pages,
        "units": units,
        "split_files": len(split_plans),
        "workers": workers,
        "mode": "page-level split" if split_plans else "file-level fan-out",
    }
