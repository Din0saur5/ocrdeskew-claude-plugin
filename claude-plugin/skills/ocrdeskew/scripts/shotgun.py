#!/usr/bin/env python3
"""Shotgun Method — parallel orchestration for the local `ocrdeskew` CLI.

`ocrdeskew` processes one input at a time in a single process. This wrapper
reads the machine's CPU and memory, decides how many copies of `ocrdeskew` it
can run at once, splits the work (across files, or across page ranges of a
large PDF), runs the fan-out, stitches split PDFs back together and verifies
the result before placing it.

It never reimplements OCR, deskewing or text-layer repair — every page is
processed by `ocrdeskew` itself.

    shotgun.py plan  INPUT... [--quality MODE]
    shotgun.py run   INPUT... [--quality MODE] [--destructive] [--out DIR]

`plan` is read-only: it reports the machine, the worker count and the chunking
it would use, and touches nothing.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shotgunlib import cpu, planner, runner  # noqa: E402

QUALITIES = ("fast", "balanced", "thorough")


def _add_shared_args(parser):
    parser.add_argument("inputs", nargs="+", help="Files and/or directories to process.")
    parser.add_argument("--quality", choices=QUALITIES, default="balanced",
                        help="OCR quality/speed mode passed to ocrdeskew. Default: balanced.")
    parser.add_argument("--lang", default="eng", help="Tesseract language code. Default: eng.")
    parser.add_argument("--workers", default="auto",
                        help="Parallel ocrdeskew processes, or 'auto' to size from this machine.")
    parser.add_argument("--no-split", action="store_true",
                        help="Never split a PDF into page ranges; fan out across files only.")
    parser.add_argument("--recursive", action="store_true",
                        help="Descend into subdirectories when an input is a directory.")


def _resolve_workers(requested, quality, unit_hint=None):
    machine = cpu.detect_machine()
    if str(requested).lower() == "auto":
        workers, why = cpu.recommend_workers(quality, machine, unit_hint)
        return workers, why, machine
    try:
        workers = max(1, int(requested))
    except ValueError:
        raise SystemExit(f"--workers must be an integer or 'auto', got {requested!r}")
    return workers, "set explicitly with --workers", machine


def _collect(args):
    files, missing = planner.expand_inputs(args.inputs, args.recursive)
    if missing:
        raise SystemExit(
            "These input paths do not exist:\n  " + "\n  ".join(missing)
        )
    if not files:
        raise SystemExit("No supported PDF or image files were found in the given inputs.")
    return files


def _plan_for(args):
    """Size the machine, build the work plan, then trim workers to the real unit count."""
    files = _collect(args)
    workers, why, machine = _resolve_workers(args.workers, args.quality)
    plans = planner.build_plan(files, workers, allow_split=not args.no_split)
    summary = planner.summarize(plans, workers)
    if summary["units"] < workers:
        workers = max(1, summary["units"])
        why += f"; trimmed to {workers} because there are only {summary['units']} work unit(s)"
        summary["workers"] = workers
    return plans, summary, workers, why, machine


def cmd_plan(args):
    plans, summary, workers, why, machine = _plan_for(args)

    print(f"Machine: {machine['logical_cpus']} logical CPUs "
          f"({machine['performance_cpus']} performance / {machine['efficiency_cpus']} efficiency), "
          f"{machine['memory_gb']} GB RAM")
    print(f"Workers: {workers}  ({why})")
    print(f"Inputs:  {summary['files']} file(s), {summary['pages']} page(s)")
    print(f"Plan:    {summary['units']} work unit(s) — {summary['mode']}")
    if summary["split_files"]:
        print(f"         {summary['split_files']} large PDF(s) split into page ranges")
    for plan in plans:
        if plan.error:
            print(f"  !! {plan.source.name}: {plan.error}")
        elif plan.split:
            print(f"  -> {plan.source.name}: {plan.pages}p split into {len(plan.units)} chunk(s)")
    if summary["unreadable"]:
        print(f"\n{summary['unreadable']} file(s) could not be read and would be skipped.")
    return 0


def cmd_run(args):
    plans, summary, workers, why, machine = _plan_for(args)

    if args.destructive and args.out:
        raise SystemExit("--destructive writes over the originals; it cannot be combined with --out.")

    mode = "DESTRUCTIVE (originals overwritten)" if args.destructive else "sidecar copies"
    print(f"[shotgun] {summary['files']} file(s), {summary['pages']} page(s) -> "
          f"{summary['units']} unit(s), {workers} worker(s), --quality {args.quality}, {mode}",
          file=sys.stderr)

    if args.dry_run:
        print("[shotgun] --dry-run: nothing was processed.", file=sys.stderr)
        return 0

    try:
        outcome = runner.execute(
            plans, workers, args.quality, args.lang,
            destructive=args.destructive,
            out_dir=args.out,
            backup_dir=args.backup_dir,
            timeout=args.timeout,
            retries=args.retries,
            quiet=args.quiet,
        )
    except runner.ShotgunError as exc:
        print(f"\n[shotgun] {exc}", file=sys.stderr)
        print("[shotgun] No files were changed. See https://ocrdeskew.com to activate or renew.",
              file=sys.stderr)
        return 2
    outcome["machine"] = machine
    outcome["workers"] = workers
    outcome["worker_sizing"] = why
    outcome["quality"] = args.quality
    outcome["lang"] = args.lang
    outcome["destructive"] = bool(args.destructive)
    outcome["plan"] = summary

    payload = json.dumps(outcome, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(payload)
        print(f"[shotgun] JSON summary written to {args.json_out}", file=sys.stderr)
    else:
        print(payload)

    succeeded = sum(1 for r in outcome["results"] if r["ok"])
    failed = len(outcome["results"]) - succeeded
    print(f"[shotgun] done in {outcome['elapsed_seconds']}s — {succeeded} ok, {failed} failed",
          file=sys.stderr)
    return 0 if failed == 0 else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="shotgun.py",
        description="Run many ocrdeskew processes in parallel, sized to this machine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan", help="Show the machine sizing and chunking, change nothing.")
    _add_shared_args(plan_parser)
    plan_parser.set_defaults(func=cmd_plan)

    run_parser = sub.add_parser("run", help="Execute the parallel run.")
    _add_shared_args(run_parser)
    run_parser.add_argument("--out", help="Output directory for repaired copies.")
    run_parser.add_argument("--destructive", action="store_true",
                            help="Overwrite each original PDF in place once its output verifies.")
    run_parser.add_argument("--backup-dir",
                            help="Copy each original here before a destructive overwrite.")
    run_parser.add_argument("--timeout", type=int, default=runner.DEFAULT_UNIT_TIMEOUT,
                            help="Per-unit timeout in seconds.")
    run_parser.add_argument("--retries", type=int, default=1,
                            help="Retries for a failed unit before the file is marked failed.")
    run_parser.add_argument("--json-out", help="Write the JSON summary here instead of stdout.")
    run_parser.add_argument("--dry-run", action="store_true", help="Plan and report, but do not run.")
    run_parser.add_argument("--quiet", action="store_true", help="Suppress per-unit progress lines.")
    run_parser.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    if not shutil.which("ocrdeskew"):
        raise SystemExit(
            "ocrdeskew is not installed, or not on PATH.\n"
            "\n"
            "This plugin drives the OCRDeskew CLI; it does no OCR of its own.\n"
            "Download OCRDeskew and start a 20-day free trial, or activate a\n"
            "licence, at https://ocrdeskew.com\n"
            "\n"
            "The macOS app installs the CLI to /usr/local/bin. Once it is in\n"
            "place, `ocrdeskew --help` should print usage."
        )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
