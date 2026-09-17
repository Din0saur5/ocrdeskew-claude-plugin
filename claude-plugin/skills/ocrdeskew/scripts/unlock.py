#!/usr/bin/env python3
"""Clear PDF encryption so `ocrdeskew` can read the file.

The OCRDeskew desktop app can unlock a restricted PDF; the packaged CLI has no
flag for it. This script reproduces the app's own `unlock_pdf_file` behaviour using the PDF
libraries already installed, so the same capability is reachable from Claude
Code. Status vocabulary and output naming deliberately match the app's, so a
file unlocked here is indistinguishable from one unlocked in the GUI.

What it does: opens a PDF with the **empty password first**, then with any
passwords you supply, and rewrites the file without its encryption dictionary.
The empty password is what clears *owner-password* restrictions -- the
permissions flags that courts, agencies and e-discovery vendors routinely stamp
on productions to block copying and text extraction. Those files open fine for
reading; the flag only blocks downstream tools such as OCR.

What it does not do: it does not guess, brute-force or recover an unknown
password. A PDF carrying a real user password stays `locked` unless you supply
the password you were given. That boundary is deliberate.

    unlock.py scan INPUT...
    unlock.py run  INPUT... [--password PW] [--password-file FILE] [--destructive]
"""

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # The bundled app ships the older library under another name.
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except ImportError:
        print("Neither pypdf nor PyPDF2 is installed; cannot process PDFs.", file=sys.stderr)
        sys.exit(2)

# Status vocabulary matches the desktop app's PdfUnlockResult exactly.
ALREADY_OPEN = "already_unlocked"
CLEARED = "unlocked"
NEEDS_PASSWORD = "locked"
ERROR = "error"

SUFFIX = "-unlocked"


def normalize_passwords(passwords):
    """Drop blanks and duplicates, keep order. Mirrors the app's helper."""
    normalized, seen = [], set()
    for password in passwords or []:
        if password is None:
            continue
        candidate = password.rstrip("\r")
        if not candidate.strip() or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def build_output_path(source, directory=None, suffix=SUFFIX):
    """`name-unlocked.pdf`, then `-unlocked-2`, `-3`... so nothing is clobbered."""
    source = Path(source)
    parent = Path(directory) if directory else source.parent
    parent.mkdir(parents=True, exist_ok=True)
    candidate = parent / f"{source.stem}{suffix}.pdf"
    counter = 2
    while candidate.exists():
        candidate = parent / f"{source.stem}{suffix}-{counter}.pdf"
        counter += 1
    return candidate


def _record(source, status, restricted, **extra):
    record = {
        "source_path": str(source),
        "status": status,
        "encrypted": restricted,
        "password_used": None,
        "output_path": None,
        "replaced_original": False,
        "error": None,
    }
    record.update(extra)
    return record


def _open_with(file_bytes, passwords):
    """Try the empty password, then each supplied one.

    Returns (reader_or_None, password_used, saw_rejection, last_exception).
    """
    opened, used, saw_rejection, last_error = None, None, False, None
    for password in [""] + normalize_passwords(passwords):
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            accepted = reader.decrypt(password)
        except Exception as exc:
            last_error = exc
            continue
        if accepted:
            opened, used = reader, password
            break
        saw_rejection = True
    return opened, used, saw_rejection, last_error


def inspect(path):
    """Report a file's state without writing anything."""
    path = Path(path)
    try:
        file_bytes = path.read_bytes()
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        return _record(path, ERROR, False, error=str(exc))

    if not reader.is_encrypted:
        return _record(path, ALREADY_OPEN, False)

    opened, used, _seen, _err = _open_with(file_bytes, [])
    if opened is not None:
        return _record(path, NEEDS_PASSWORD, True, password_used=used,
                       error="owner-password restriction; clears with no password")
    return _record(path, NEEDS_PASSWORD, True, error="needs the document's password")


def clear_restrictions(path, passwords=(), destructive=False, out_dir=None):
    """Rewrite one PDF without its encryption dictionary. Returns a record dict."""
    source = Path(path)
    try:
        file_bytes = source.read_bytes()
        initial = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        return _record(source, ERROR, False, error=str(exc))

    if not initial.is_encrypted:
        return _record(source, ALREADY_OPEN, False)

    opened, used, saw_rejection, last_error = _open_with(file_bytes, passwords)
    if opened is None:
        if last_error is not None and not saw_rejection:
            return _record(source, ERROR, True, error=str(last_error))
        return _record(source, NEEDS_PASSWORD, True,
                       error="no supplied password opened this file")

    writer = PdfWriter()
    try:
        for page in opened.pages:
            writer.add_page(page)
    except Exception as exc:
        return _record(source, ERROR, True, error=str(exc))

    if destructive:
        # Write beside the original, then swap atomically -- same as the app.
        staging = source.with_name(f".{source.name}.unlocking")
        try:
            with staging.open("wb") as handle:
                writer.write(handle)
            os.replace(staging, source)
        except Exception as exc:
            staging.unlink(missing_ok=True)
            return _record(source, ERROR, True, error=str(exc))
        return _record(source, CLEARED, True, password_used=used,
                       output_path=str(source), replaced_original=True)

    destination = build_output_path(source, out_dir)
    try:
        with destination.open("wb") as handle:
            writer.write(handle)
    except Exception as exc:
        return _record(source, ERROR, True, error=str(exc))
    return _record(source, CLEARED, True, password_used=used,
                   output_path=str(destination))


def collect(inputs, recursive=False):
    """Resolve inputs to PDFs, skipping pairs we already produced."""
    files, missing = [], []
    for raw in inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            missing.append(str(path))
            continue
        if path.is_dir():
            found = path.rglob("*.pdf") if recursive else path.glob("*.pdf")
            files.extend(sorted(p.resolve() for p in found if p.is_file()))
        elif path.suffix.lower() == ".pdf":
            files.append(path.resolve())

    # An `x-unlocked.pdf` beside `x.pdf` means x was handled already; skip both.
    generated, superseded = set(), set()
    for path in files:
        match = re.match(r"^(?P<base>.+)-unlocked(?:-\d+)?$", path.stem, re.IGNORECASE)
        if not match:
            continue
        origin = path.with_name(f"{match.group('base')}.pdf")
        if origin.exists() and origin != path:
            generated.add(path)
            superseded.add(origin)
    return [p for p in files if p not in generated and p not in superseded], missing


def _gather_passwords(args):
    supplied = list(getattr(args, "password", None) or [])
    if getattr(args, "password_file", None):
        supplied += Path(args.password_file).expanduser().read_text().splitlines()
    return supplied


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="unlock.py",
        description="Clear PDF encryption so ocrdeskew can read the file.")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Report which PDFs are restricted. Writes nothing.")
    run = sub.add_parser("run", help="Clear restrictions from the encrypted PDFs.")
    for sp in (scan, run):
        sp.add_argument("inputs", nargs="+", help="PDF files and/or directories.")
        sp.add_argument("--recursive", action="store_true", help="Descend into subdirectories.")
        sp.add_argument("--json-out", help="Write the JSON report here instead of stdout.")
    run.add_argument("--password", action="append",
                     help="A password to try. Repeatable. The empty password is always tried first.")
    run.add_argument("--password-file", help="File of candidate passwords, one per line.")
    run.add_argument("--destructive", action="store_true",
                     help="Overwrite each original in place instead of writing -unlocked copies.")
    run.add_argument("--out", help="Directory for the unlocked copies.")

    args = parser.parse_args(argv)
    files, missing = collect(args.inputs, args.recursive)
    if missing:
        raise SystemExit("These input paths do not exist:\n  " + "\n  ".join(missing))
    if not files:
        raise SystemExit("No PDF files were found in the given inputs.")

    if args.command == "scan":
        records = [inspect(path) for path in files]
    else:
        if args.destructive and args.out:
            raise SystemExit("--destructive overwrites the originals; it cannot be combined with --out.")
        supplied = _gather_passwords(args)
        records = [clear_restrictions(path, supplied, args.destructive, args.out) for path in files]

    counts = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
        # Never echo a supplied password into a report the user might share.
        if record.get("password_used"):
            record["password_used"] = "<supplied>"

    payload = {"command": args.command, "counts": counts, "results": records}
    text = json.dumps(payload, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text)
        print(f"[unlock] report written to {args.json_out}", file=sys.stderr)
    else:
        print(text)

    print("[unlock] " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())), file=sys.stderr)
    return 1 if counts.get(ERROR) else 0


if __name__ == "__main__":
    sys.exit(main())
