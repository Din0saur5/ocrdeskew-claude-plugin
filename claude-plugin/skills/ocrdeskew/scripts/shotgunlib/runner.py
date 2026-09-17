"""Parallel execution of `ocrdeskew` across work units, and result placement.

Each work unit is one `ocrdeskew` subprocess. Units are dispatched through a
thread pool (the real work happens in child processes, so threads only shepherd
them). A source file's output is only placed — and in destructive mode only
allowed to overwrite the original — after every one of its units succeeded and
the assembled PDF verified against the original page count.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import cpu, pdfops

OCRDESKEW = shutil.which("ocrdeskew")
DEFAULT_UNIT_TIMEOUT = 1800  # 30 min per unit; a long thorough chunk is normal.
SUFFIX = "-deskewed"


class ShotgunError(RuntimeError):
    pass


def _log(message, quiet=False):
    if not quiet:
        print(message, file=sys.stderr, flush=True)


def run_unit(unit, out_path, quality, lang, timeout=DEFAULT_UNIT_TIMEOUT):
    """Run one `ocrdeskew` invocation. Returns (ok, payload_or_error)."""
    if not OCRDESKEW:
        return False, {"error": "ocrdeskew is not installed or not on PATH"}

    cmd = [
        OCRDESKEW, str(unit.path),
        "--quality", quality,
        "--lang", lang,
        "--json",
        "--out", str(out_path),
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, env=cpu.worker_env(),
        )
    except subprocess.TimeoutExpired:
        return False, {"error": f"timed out after {timeout}s", "elapsed": timeout}
    elapsed = time.monotonic() - started

    if proc.returncode != 0:
        # A licensing refusal is JSON on stdout with no per-file results. Surface
        # the message instead of dumping the blob, and mark it fatal: retrying or
        # running the other workers cannot help.
        licensing = _license_refusal(proc.stdout)
        if licensing:
            return False, {"error": licensing["error"], "license_state": licensing["state"],
                           "fatal": True, "elapsed": elapsed}
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        return False, {"error": f"ocrdeskew exited {proc.returncode}: {detail}", "elapsed": elapsed}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return False, {"error": f"unparseable JSON from ocrdeskew: {exc}", "elapsed": elapsed}

    entries = payload.get("results") or []
    if not entries:
        return False, {"error": "ocrdeskew returned no results", "elapsed": elapsed}
    entry = entries[0]
    if not entry.get("ok"):
        return False, {"error": entry.get("error") or "ocrdeskew reported failure", "elapsed": elapsed}

    entry["_elapsed"] = elapsed
    entry["_app_version"] = payload.get("app_version")
    entry["_schema_version"] = payload.get("schema_version")
    return True, entry


def _license_refusal(stdout):
    """Detect the CLI's licensing refusal payload. Returns {error, state} or None."""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or "license_state" not in payload:
        return None
    return {
        "error": payload.get("error") or "ocrdeskew refused to run: a valid licence is required.",
        "state": payload.get("license_state"),
    }


def _span(unit):
    """Describe which part of a source a unit covers."""
    if unit.page_range:
        return f"pages {unit.page_range[0]}-{unit.page_range[1]}"
    return "whole file"


def _label(unit):
    if unit.page_range:
        return f"{unit.source.name} p{unit.page_range[0]}-{unit.page_range[1]}"
    return unit.source.name


def _prepare_units(plans, workdir):
    """Materialize chunk files for split sources. Returns the flat unit list."""
    chunk_root = workdir / "chunks"
    units = []
    for plan in plans:
        if plan.error:
            continue
        if plan.split:
            ranges = [u.page_range for u in plan.units]
            dest = chunk_root / plan.source.stem
            chunks = pdfops.split_pdf(plan.source, ranges, dest)
            for unit, chunk in zip(plan.units, chunks):
                unit.path = chunk
        units.extend(plan.units)
    return units


def _aggregate(entries, pages):
    """Roll per-unit OCR metrics up to a single per-source summary."""
    word_count = 0
    weighted_quality = 0.0
    weighted_confidence = 0.0
    weight = 0
    statuses = []
    for entry, unit_pages in entries:
        result = entry.get("result") or {}
        word_count += result.get("word_count") or 0
        unit_weight = max(1, unit_pages)
        if result.get("quality_score") is not None:
            weighted_quality += result["quality_score"] * unit_weight
        if result.get("confidence") is not None:
            weighted_confidence += result["confidence"] * unit_weight
        weight += unit_weight
        if result.get("audit_status"):
            statuses.append(result["audit_status"])
    return {
        "word_count": word_count,
        "quality_score": round(weighted_quality / weight, 2) if weight else None,
        "confidence": round(weighted_confidence / weight, 2) if weight else None,
        "pages": pages,
        "audit_status": statuses[0] if statuses else None,
    }


def _place_output(produced, plan, destructive, out_dir, backup_dir):
    """Move a verified PDF to its final home. Returns (final_path, note)."""
    source = plan.source
    note = None

    if destructive:
        if plan.is_pdf:
            if backup_dir:
                backup_dir = Path(backup_dir)
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, backup_dir / source.name)
            os.replace(str(produced), str(source))
            return source, "original overwritten in place"
        # An image cannot hold a PDF text layer, so the source image is kept.
        final = source.with_suffix(".pdf")
        os.replace(str(produced), str(final))
        return final, "image converted to PDF; original image kept (in-place replace applies to PDFs only)"

    target_dir = Path(out_dir) if out_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    final = target_dir / f"{source.stem}{SUFFIX}.pdf"
    os.replace(str(produced), str(final))
    return final, note


def execute(plans, workers, quality, lang, destructive=False, out_dir=None,
            backup_dir=None, timeout=DEFAULT_UNIT_TIMEOUT, retries=1, quiet=False):
    """Run every plan's units in parallel, then assemble and place outputs."""
    workdir = Path(tempfile.mkdtemp(prefix="ocrdeskew-shotgun-"))
    out_root = workdir / "out"
    out_root.mkdir(parents=True, exist_ok=True)

    results = {p.source: {"source": str(p.source), "pages": p.pages, "units": [],
                          "ok": None, "error": p.error} for p in plans}
    started = time.monotonic()

    try:
        units = _prepare_units(plans, workdir)
        total = len(units)
        _log(f"[shotgun] dispatching {total} unit(s) across {workers} worker(s)", quiet)

        outputs = {}
        done = 0
        fatal = None
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for unit in units:
                out_path = out_root / f"{unit.source.stem}__u{unit.index:04d}.pdf"
                outputs[id(unit)] = out_path
                futures[pool.submit(run_unit, unit, out_path, quality, lang, timeout)] = unit

            for future in as_completed(futures):
                unit = futures[future]
                ok, payload = future.result()
                done += 1
                if not ok and payload.get("fatal"):
                    fatal = fatal or payload
                elif not ok and retries > 0:
                    _log(f"[shotgun] retrying {unit.path.name}: {payload.get('error')}", quiet)
                    ok, payload = run_unit(unit, outputs[id(unit)], quality, lang, timeout)
                results[unit.source]["units"].append((unit, ok, payload))
                _log(f"[shotgun] {done}/{total} {'ok  ' if ok else 'FAIL'} {_label(unit)}", quiet)

        if fatal:
            # Nothing was placed; every original is untouched.
            raise ShotgunError(fatal["error"])

        for plan in plans:
            record = results[plan.source]
            if plan.error:
                record["ok"] = False
                continue

            unit_records = sorted(record["units"], key=lambda r: r[0].index)
            failures = [(u, p) for u, ok, p in unit_records if not ok]
            if failures:
                record["ok"] = False
                record["error"] = "; ".join(
                    f"{_span(u)}: {p.get('error')}" for u, p in failures
                )
                record["note"] = "original left untouched"
                continue

            entries = [(p, u.pages) for u, _ok, p in unit_records]
            produced_paths = [Path(p["output_path"]) for _u, _ok, p in unit_records]

            if plan.split:
                assembled = workdir / f"{plan.source.stem}__merged.pdf"
                try:
                    pdfops.merge_pdfs(produced_paths, assembled)
                except pdfops.PdfError as exc:
                    record["ok"] = False
                    record["error"] = f"merge failed: {exc}"
                    record["note"] = "original left untouched"
                    continue
            else:
                assembled = produced_paths[0]

            expected = plan.pages if plan.is_pdf else None
            verified, reason = pdfops.verify_pdf(assembled, expected)
            if not verified:
                record["ok"] = False
                record["error"] = f"verification failed: {reason}"
                record["note"] = "original left untouched"
                continue

            final, note = _place_output(assembled, plan, destructive, out_dir, backup_dir)
            record["ok"] = True
            record["output_path"] = str(final)
            record["note"] = note
            record["metrics"] = _aggregate(entries, plan.pages)
            record["chunks"] = len(unit_records)

        for record in results.values():
            record.pop("units", None)

        return {
            "ok": all(r["ok"] for r in results.values()),
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "results": list(results.values()),
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
