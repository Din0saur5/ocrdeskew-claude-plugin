# Clearing PDF restrictions

Reference detail for `scripts/unlock.py`. SKILL.md covers when to use it; this
covers what it does and why it matches the desktop app.

## Why it exists

The OCRDeskew desktop app can clear a restricted PDF. The packaged CLI has no
flag for it, so a restricted file simply fails OCR with an error that looks like
a scan-quality problem but is not one. This script closes that gap using the PDF
libraries already installed, reproducing the app's own `unlock_pdf_file`
behaviour.

## What it actually does

Opens the PDF with the **empty password first**, then with each password the
user supplied, and rewrites the pages into a new document with no encryption
dictionary.

The empty password is the important part. Two different things are called
"password protected":

- **Owner password / permissions restriction** — the file opens for anyone, but
  carries flags that forbid copying, printing or text extraction. Courts,
  agencies and e-discovery vendors stamp these on productions routinely. The
  empty password opens these, which is why it is tried first, and why most
  restricted files in a legal production clear with no password at all.
- **User password** — the file will not open at all without the password. These
  stay `locked` unless the user supplies the password they were given.

## What it does not do

It does not guess, brute-force, or recover an unknown password, and no password
list is built into it. This boundary is deliberate; do not add cracking behavior
to this script or reach for other tools to get around it. A file whose password
the user does not have is a dead end — report it and stop.

Supplied passwords are redacted to `<supplied>` in the JSON report so a report
can be shared or attached to a matter file without leaking a document password.

## Statuses

Matches the app's `PdfUnlockResult` vocabulary exactly:

| Status | Meaning |
|---|---|
| `already_unlocked` | Not encrypted. Untouched. |
| `unlocked` | Cleared. `output_path` holds the result. |
| `locked` | Encrypted, and no supplied password opened it. Untouched. |
| `error` | Could not be read or written. Untouched. |

`scan` uses the same vocabulary but reports `locked` with a note distinguishing
"clears with no password" from "needs the document's password", so you can tell
the user up front whether they need to go find a password at all.

## Output naming and idempotency

Non-destructive output is `<stem>-unlocked.pdf`, colliding into
`-unlocked-2.pdf`, `-3.pdf` and so on — nothing is ever clobbered.

A file that already has an `-unlocked` sibling is skipped on a re-run, and so is
the sibling itself, matching the app's `collect_unlock_candidate_files`. Running
twice over a folder is safe and does nothing the second time.

`ocrdeskew` itself prefers an `-unlocked` sibling over the restricted original
when both sit in a folder (`collect_effective_pdf_files`), so unlocking first
and then OCR'ing the folder picks up the right file with no extra bookkeeping.

## Destructive mode

`--destructive` writes to a hidden sibling `.{name}.unlocking` and then
`os.replace`s it over the original — the same atomic swap the app uses. There is
no window in which the original is truncated or half-written. On any failure the
staging file is removed and the original is left exactly as it was.

## Dependencies

`pypdf` (preferred) or `PyPDF2`. No network access, no external binary.
