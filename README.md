# OCRDeskew for Claude Code

The official [Claude Code](https://claude.com/claude-code) plugin for
[OCRDeskew](https://ocrdeskew.com) — repair OCR text layers, produce searchable
PDFs, clear PDF restrictions that block OCR, and process large batches in
parallel across every core on the machine.

Everything runs locally. No document leaves the computer.

## Install

```
/plugin marketplace add Din0saur5/ocrdeskew-claude-plugin
/plugin install ocrdeskew
```

Then try `/ocr-audit` on a folder of scans — it is read-only and reports what
would need repair.

## Requires OCRDeskew

**This plugin is free and MIT licensed. The CLI it drives is not.**

The plugin performs no OCR itself — it orchestrates the `ocrdeskew` binary that
ships with the OCRDeskew desktop app, which checks its own licence before
processing anything. OCRDeskew includes a **20-day free trial**; after that a
licence is required. See [ocrdeskew.com](https://ocrdeskew.com).

Installed without OCRDeskew, the commands cleanly report what is missing and do
nothing else.

## What you get

| | |
|---|---|
| `/ocr-batch` | OCR and deskew a file or folder into searchable PDFs |
| `/ocr-audit` | Report which files lack usable searchable text — read-only |
| `/ocr-unlock` | Clear PDF restrictions that block OCR |
| `ocr-triage` agent | Classify a finished batch's failures and recommend next steps |

Plus the `ocrdeskew` skill, which triggers on its own when you describe what you
want ("make this production searchable").

### The Shotgun Method

`ocrdeskew` processes one file at a time in one process, leaving most of a modern
machine idle. The Shotgun Method reads the CPU and RAM, runs that many copies at
once, and splits large PDFs into page ranges when there are not enough files to
keep every core busy.

Measured on an 18-core machine, one 24-page PDF at `--quality balanced`:

| | Wall clock | Words | Pages |
|---|---|---|---|
| Plain `ocrdeskew` | 5m 02s | 4361 | 24 |
| Shotgun, 12 workers | **1m 46s** | 4361 | 24 |

Split files are merged back in page order and the page count is verified against
the original before any result is placed. If OCR, merge or verification fails for
a file, that original is left untouched and reported.

### It asks before it runs

Every run starts with three questions — output mode, quality, and whether to
parallelize — each option described in plain language. Nothing is assumed, and
answers are not carried between runs.

## Documentation

Full details in [`claude-plugin/README.md`](claude-plugin/README.md), and in the
skill's reference docs:

- [`shotgun-method.md`](claude-plugin/skills/ocrdeskew/reference/shotgun-method.md) — worker sizing, chunking, safety model
- [`unlock.md`](claude-plugin/skills/ocrdeskew/reference/unlock.md) — what unlocking does and does not do
- [`json-schema.md`](claude-plugin/skills/ocrdeskew/reference/json-schema.md) — the CLI's `--json` output

## License

[MIT](LICENSE), covering this plugin only — see [NOTICE](NOTICE) for the exact
scope. The OCRDeskew application and its `ocrdeskew` binary are proprietary and
licensed separately.
