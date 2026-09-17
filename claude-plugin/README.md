# OCRDeskew for Claude Code

Drive [OCRDeskew](https://ocrdeskew.com) from Claude Code: repair OCR text layers,
produce searchable PDFs, clear PDF restrictions that block OCR, and process large
batches in parallel across every core on the machine.

Everything runs locally. No document leaves the computer.

## Install

```
/plugin marketplace add Din0saur5/ocrdeskew-claude-plugin
/plugin install ocrdeskew
```

## Requirements

| Requirement | Why | If missing |
|---|---|---|
| **[OCRDeskew](https://ocrdeskew.com) installed and licensed**, `ocrdeskew` on `PATH` | Does all OCR and deskewing | The plugin refuses to run and says so — it will not write its own OCR code |
| **python3** | Runs the batch and unlock wrappers | Parallel processing and unlock unavailable |
| **qpdf** *or* **pypdf** | Splits and merges PDFs | Batches still fan out across files; a single large PDF cannot be split |

The macOS app installs `ocrdeskew` to `/usr/local/bin`. Verify with `ocrdeskew --help`.

### Licensing

**This plugin is free. The CLI it drives requires an OCRDeskew licence.**

The plugin contains no OCR of its own — it orchestrates the `ocrdeskew` binary that ships with the app, and that binary checks its own licence before processing anything. OCRDeskew includes a **20-day free trial**; after that a licence is required. See [ocrdeskew.com](https://ocrdeskew.com) for plans.

Installing this plugin without OCRDeskew gets you commands that cleanly tell you what is missing, and nothing else.

If your trial or licence has lapsed, a run stops immediately with the licence message, exits 2, and leaves every original file untouched — it does not partially process a batch.

## Commands

| Command | What it does |
|---|---|
| `/ocr-batch [path]` | OCR and deskew a file or folder into searchable PDFs |
| `/ocr-audit [path]` | Report which files lack usable searchable text — read-only, repairs nothing |
| `/ocr-unlock [path]` | Clear PDF restrictions that block OCR |

You can also just describe what you want ("make this production searchable") — the
skill triggers on its own.

## It asks before it runs

Every run starts with three questions, each option described in plain language:

- **Output** — sidecar copies, overwrite with backups, or overwrite with none
- **Quality** — fast, balanced or thorough
- **Shotgun Method** — parallel processing, or one file at a time

Nothing is assumed, and answers are not carried over between runs. A setting you
state up front is not asked about again.

## The Shotgun Method

`ocrdeskew` processes one file at a time in one process, which leaves most of a
modern machine idle. The Shotgun Method reads the CPU and RAM, runs that many
copies at once, and splits large PDFs into page ranges when there are not enough
files to keep every core busy.

Measured on an 18-core machine, one 24-page PDF at `--quality balanced`:

| | Wall clock | Words | Pages |
|---|---|---|---|
| Plain `ocrdeskew` | 5m 02s | 4361 | 24 |
| Shotgun, 12 workers | **1m 46s** | 4361 | 24 |

Split files are merged back in page order and the page count is **verified against
the original** before any result is placed. If OCR, merge or verification fails for
a file, that original is left untouched and reported.

Details in `skills/ocrdeskew/reference/shotgun-method.md`.

## Unlocking restricted PDFs

The desktop app can clear a restricted PDF; the CLI has no flag for it. The plugin
closes that gap, reproducing the app's own behaviour.

It opens a PDF with the empty password first, then any password you supply. The
empty password is what clears **owner-password restrictions** — the permissions
flags courts and e-discovery vendors stamp on productions to block text
extraction. Those files open fine for reading; the flag only blocks OCR.

It does **not** guess, brute-force or recover an unknown password. A PDF with a
real user password stays locked unless you supply the password you were given.
Passwords you do supply are redacted from every report.

Details in `skills/ocrdeskew/reference/unlock.md`.

## Triage agent

When a batch finishes with failures or low scores, the `ocr-triage` agent reads
the JSON report and classifies each file: re-run at thorough, unlock first,
rescan at higher DPI, genuinely blank, or local options exhausted.

It reads `escalation_tier` to tell the difference between a file the local engine
can still improve and one where it has run out of road. Only in that last case
does it suggest AI image analysis — and it says plainly that this step sends page
images off the machine, which for client or privileged material is a
confidentiality decision, not just an accuracy one. It recommends; it never
escalates on its own.

## What is in here

```
claude-plugin/
├── .claude-plugin/plugin.json
├── commands/           ocr-batch, ocr-audit, ocr-unlock
├── agents/             ocr-triage
└── skills/ocrdeskew/
    ├── SKILL.md
    ├── reference/      json-schema, shotgun-method, unlock
    └── scripts/        shotgun.py, unlock.py, shotgunlib/
```

## License

The plugin — this directory's manifest, commands, agent, skill and wrapper
scripts — is [MIT licensed](LICENSE).

That covers the plugin only. The OCRDeskew application and its `ocrdeskew`
binary are proprietary and licensed separately; see
[ocrdeskew.com](https://ocrdeskew.com).

## Using it without the plugin

Copy `skills/ocrdeskew/` into `~/.claude/skills/`. The skill detects the
standalone layout and adjusts its script paths. You lose the slash commands and
the triage agent; the skill itself works the same.
