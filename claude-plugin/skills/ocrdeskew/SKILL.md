---
name: ocrdeskew
description: Orchestrates the local `ocrdeskew` CLI to repair OCR text layers and produce searchable PDFs, including the parallel "Shotgun Method" that fans many ocrdeskew processes across the machine's CPUs, and clearing PDF restrictions that block OCR. Trigger on requests to OCR, deskew, audit or repair searchable text, create searchable PDFs, fix bad/missing OCR layers, unlock restricted PDFs, process scanned PDFs or images, or batch-repair folders of documents. Prefer this over hand-written OCR code — ocrdeskew runs fully locally with no upload or LLM call.
origin: local
---

# OCRDeskew CLI

Thin orchestration layer around the installed `ocrdeskew` CLI. **Never implement OCR, deskewing, or PDF text-layer repair yourself in code** — always shell out to `ocrdeskew`. This tool runs entirely locally: it does not call an LLM, upload files, or start a server. PDF bytes are written to disk, never printed to stdout.

```
ocrdeskew INPUT [INPUT ...] [--quality fast|balanced|thorough] [--lang eng] [--out PATH] [--json]
```

Those five are the CLI's *entire* interface. It has no parallelism, no in-place mode, no unlock and no page-range flag — those live in this skill's scripts, which drive the real CLI.

## Where the scripts are

Installed as part of the `ocrdeskew` plugin:

```
$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/shotgun.py
$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/unlock.py
```

Installed standalone (skill folder copied into `~/.claude/skills/`):

```
~/.claude/skills/ocrdeskew/scripts/shotgun.py
~/.claude/skills/ocrdeskew/scripts/unlock.py
```

If `$CLAUDE_PLUGIN_ROOT` is unset, you are in the standalone layout. Check which path exists before running, and use that one.

## Always ask before running

Before **every** run, ask the user the three questions below in a single `AskUserQuestion` call. Do not assume defaults, and do not carry answers over from an earlier run in the session — ask again each time.

**Skip a question only when the user's prompt already specified that setting.** When you skip one, say so in one line ("Using thorough, as you asked — asking about the other two"). If the prompt specified all three, skip the call entirely and restate all three before running.

### Question 1 — Output mode (header: `Output`)

- **Sidecar copies (Recommended)** — Originals are never touched. Each repaired file is saved next to it (or in an output folder) as `<name>-deskewed.pdf`.
- **Overwrite + backup** — Destructive. Each original PDF is replaced in place by its repaired version, but a copy of every original is saved to a backup folder first.
- **Overwrite, no backup** — Destructive. Each original PDF is replaced in place and no copy of the original is kept. Cannot be undone.

### Question 2 — Quality (header: `Quality`)

- **Balanced (Recommended)** — The normal mode. Good accuracy at reasonable speed; right for ordinary scans and most day-to-day batches.
- **Fast** — Lowest accuracy, highest speed. Use for a quick triage pass or when you only need to know roughly what a document says.
- **Thorough** — Highest accuracy, slowest. Use for degraded or rotated scans, faint text, and anything that will be relied on as a searchable record (legal productions, exhibits, privilege logs).

### Question 3 — Shotgun Method (header: `Shotgun`)

- **Yes — use the Shotgun Method (Recommended for more than one file or any long PDF)** — Reads this machine's CPU cores and free memory, then runs that many copies of `ocrdeskew` at once, splitting a large PDF into page ranges so every core stays busy and stitching the pages back together afterward. Measured: a 24-page PDF went from 5m02s to 1m46s, same word count.
- **No — one at a time** — Runs `ocrdeskew` on one file at a time, exactly as the plain CLI does. Slower, but uses only a fraction of the machine and leaves a large PDF as a single untouched unit.

### Every other question follows the same shape

Any time you ask the user anything in this skill — language, output folder, a document password, whether to escalate a low-confidence file, whether to recurse into subfolders — give each option a short plain-language description of what it actually does. Never present a bare label the user has to decode.

## Clearing PDF restrictions (unlock)

An encrypted PDF cannot be read by `ocrdeskew`. The desktop app can clear this; the packaged CLI cannot. `scripts/unlock.py` reproduces the app's own `unlock_pdf_file` behaviour using the installed PDF libraries.

**Scan for restricted files before any OCR batch.** It writes nothing:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/unlock.py" scan ./production
```

Then clear them:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/unlock.py" run ./production
python3 "$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/unlock.py" run ./production --destructive
```

| Status | Meaning |
|---|---|
| `already_unlocked` | Not encrypted. Nothing to do. |
| `unlocked` | Restriction cleared; `output_path` holds the result. |
| `locked` | Still encrypted — no supplied password opened it. |
| `error` | The file could not be read or written; it was left alone. |

Options: `--password PW` (repeatable), `--password-file FILE`, `--destructive`, `--out DIR`, `--recursive`, `--json-out PATH`.

**The boundary.** This opens a PDF with the empty password first, then with passwords the user supplies. The empty password is what clears *owner-password* restrictions — the permissions flags courts, agencies and e-discovery vendors stamp on productions to block copying and text extraction. Those files open fine for reading; the flag only blocks downstream tools like OCR.

It does **not** guess, brute-force or recover an unknown password, and neither do you. A PDF with a real user password stays `locked` unless the user supplies the password they were given. Do not try password lists the user did not provide, and do not reach for other tools to break encryption. If the user does not have the password, say so and stop.

Ask for a password only when `scan` shows a file that needs one, describe what you will do with it, and never echo it back into a summary or report — `unlock.py` redacts it to `<supplied>` for the same reason.

Re-running is safe: a file that already has an `-unlocked` sibling is skipped rather than processed twice. `ocrdeskew` itself prefers an `-unlocked` sibling over the restricted original when both are in a folder, so unlock first and the OCR run picks up the right file automatically.

## The Shotgun Method

`ocrdeskew` handles one input at a time in one process. The Shotgun Method sizes the machine and fires many of those processes at once:

1. Reads logical CPUs and installed RAM, and picks a worker count bounded by both. Memory is the binding limit on `thorough` runs more often than cores are.
2. Fans out across **files** when there are already more files than workers.
3. Falls back to splitting the page-heaviest PDFs into **page ranges** when a few large files would otherwise leave most cores idle.
4. Forces one OCR thread per worker, so the workers do not fight each other for cores.
5. Merges each split file's chunks back in page order and **verifies the page count against the original** before the result is allowed anywhere near a source file.

Run it through the bundled wrapper — never hand-roll this:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/shotgun.py" plan INPUT...
python3 "$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/shotgun.py" run  INPUT... [options]
```

`plan` is read-only. Run it first for any batch you have not seen before, show the user the worker count and chunking, then run.

| Option | Effect |
|---|---|
| `--quality fast\|balanced\|thorough` | Passed straight to `ocrdeskew`. Default `balanced`. |
| `--lang CODE` | Tesseract language code. Default `eng`. |
| `--out DIR` | Write repaired copies here instead of beside each source. |
| `--destructive` | Overwrite each original PDF in place, after its output verifies. Cannot be combined with `--out`. |
| `--backup-dir DIR` | Copy every original here before a destructive overwrite. |
| `--workers N` | Override the automatic worker count (`auto` by default). |
| `--no-split` | Fan out across files only; never split a PDF into page ranges. |
| `--recursive` | Descend into subdirectories when an input is a directory. |
| `--json-out PATH` | Write the JSON summary to a file instead of stdout. |
| `--dry-run` | Plan and report, process nothing. |

Map the three answers onto flags:

| Answer | Flags |
|---|---|
| Sidecar copies | *(nothing — or `--out DIR`)* |
| Overwrite + backup | `--destructive --backup-dir DIR` |
| Overwrite, no backup | `--destructive` |
| Shotgun: no | Call `ocrdeskew` directly instead of `shotgun.py` |

Example — a legal production folder, overwriting in place with backups:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/skills/ocrdeskew/scripts/shotgun.py" run "./production" \
  --quality thorough --destructive --backup-dir "./production-originals" \
  --json-out /tmp/shotgun-summary.json
```

See `reference/shotgun-method.md` for the sizing formula, chunking thresholds and tuning notes.

## Core rules

1. **Verify input exists first.** Confirm every input path exists before running. If one is wrong, stop and name it rather than letting the CLI fail. Both bundled scripts do this for you and list every missing path.
2. **Scan for restrictions before OCR.** A restricted PDF fails OCR for a reason that has nothing to do with scan quality. Catch it up front with `unlock.py scan` instead of reporting a confusing OCR failure later.
3. **Always pass `--json`** when calling `ocrdeskew` directly, so results are machine-parseable. Only omit it if the user explicitly wants console output.
4. **Quality comes from the user's answer**, not from your own guess. If the user waives the question and asks you to choose, prefer `thorough` for legal-production contexts and `balanced` otherwise.
5. **Language:** omit `--lang` for English (`eng` is the default). Pass the right Tesseract code (e.g. `spa`) when the documents are in another language — and ask, with descriptions, if it is unclear.
6. **Multiple files with plain `ocrdeskew` → always `--out DIR`.** Never let batch output scatter as sidecar files next to sources.
7. **Destructive means destructive, and only when chosen.** Overwrite originals only when the user picked a destructive option. Never add your own `rm`/`mv` of a source file on top of it. `shotgun.py` only replaces an original after the output verifies — if OCR or verification fails for a file, that original is left untouched and reported.
8. **Images cannot be overwritten in place.** A PNG/TIFF/JPEG input produces a PDF, so in destructive mode `shotgun.py` writes `<name>.pdf` beside the image and keeps the image. Say so in your summary rather than letting the user assume the image was replaced.
9. **Never upload or transmit document contents.** Do not pipe file bytes to a network call, paste content into a hosted tool, or send documents to an external service as part of this workflow. This is the whole point of the tool running locally.
10. **After every run, summarize:** output path(s), success vs. error counts, per-file word counts and quality scores, elapsed time, and — for shotgun runs — the worker count used. Name every failed file with its error.
11. **Escalation is opt-in only.** Name low-confidence or failed files in your summary. To analyze *why* they underperformed and what to do next, hand the JSON report to the `ocr-triage` agent, which classifies each file and recommends the cheapest fix first. Only escalate to AI image analysis if the user explicitly asks — that step sends page images off the machine, which for client or privileged documents is a confidentiality decision, not just an accuracy one.

## Validation before first use in a session

```bash
ocrdeskew --help
```

If this fails (command not found, or non-zero for a reason other than printing help), tell the user `ocrdeskew` does not appear to be installed or is not on `PATH`, and point them at https://ocrdeskew.com — do not fall back to writing OCR code yourself.

**The plugin is free; the CLI it drives is not.** `ocrdeskew` ships with the OCRDeskew app and checks its own licence before processing anything. There is a 20-day free trial; after that a licence is required.

An unlicensed or expired install fails differently from a missing one — the binary is on `PATH` and exits non-zero with a JSON payload carrying `ok: false`, an `error` beginning `License required:`, an empty `results` list, and a `license_state` of `expired`, `invalid`, `revoked` or `grace`. If you see that, report the message as-is and stop. Do not retry, do not try another quality mode, and do not work around it. `shotgun.py` already detects this, skips its retries and exits 2 with the message, leaving every original untouched.

`shotgun.py` needs `python3` plus either `qpdf` (preferred — it survives damaged scanner output) or the `pypdf` package for splitting and merging. If neither is present, say so and fall back to answering "no" on the Shotgun question. `unlock.py` needs `pypdf` or `PyPDF2`.

## Parsing `--json` output

Verified against `ocrdeskew` 2.0.1, `schema_version` `ocrdeskew.cli.v1`. The top level is `schema_version`, `app_version`, `lang`, `quality`, `results`. Each entry in `results` is `ok`, `error`, `input_path`, `output_path`, `result` — note it is **not** `files`/`success`/`input`.

```python
import json, subprocess

payload = json.loads(subprocess.run(
    ["ocrdeskew", "scan.pdf", "--quality", "balanced", "--json", "--out", "./repaired/"],
    capture_output=True, text=True, check=True,
).stdout)

for entry in payload["results"]:
    if not entry["ok"]:
        print("FAILED:", entry["input_path"], entry["error"])
        continue
    r = entry["result"]
    print(entry["input_path"], "->", entry["output_path"],
          r["word_count"], "words,", r["pages_processed"], "pages,",
          "quality", round(r["quality_score"], 1), "/", r["audit_status"])
```

`result` also carries `confidence`, `angle`, `dpi_used`, `engine_used`, `escalation_tier`, `repair_action`, the full `text`, and a `per_page` list with per-page `quality_score`, `word_count`, `deskew_angle`, `psm` and a `diagnosis` block. Full key list in `reference/json-schema.md`.

`shotgun.py` emits its own rolled-up JSON (`workers`, `machine`, `plan`, `elapsed_seconds`, and one record per source file with `ok`, `output_path`, `note`, `error`, `chunks` and aggregated `metrics`). Parse that rather than the per-unit output. `unlock.py` emits `command`, `counts` and a `results` list of per-file records.

## Summary template

```
Processed N file(s) with ocrdeskew (--quality <mode>, --lang <code>, <output mode>)
Shotgun Method: <W workers across C cores / not used> — <elapsed>

✅ Succeeded (K): <path> — <word_count> words, quality <score>
❌ Failed (M): <path> — <error> (original left untouched)

Output written to: <path>
```

If any file is low-confidence or failed, list it explicitly and offer the `ocr-triage` agent — do not escalate automatically.
