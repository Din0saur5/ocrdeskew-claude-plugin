---
description: Clear PDF restrictions that block OCR (the desktop app's unlock, from the CLI)
argument-hint: [file or folder] (blank to be asked)
---

# OCR Unlock

Clear encryption from the PDFs at `$ARGUMENTS` so `ocrdeskew` can read them.

The OCRDeskew desktop app has this feature; the packaged CLI does not. The `ocrdeskew` skill ships `scripts/unlock.py`, which reproduces the app's own `unlock_pdf_file` behaviour using the installed PDF libraries.

## What this does and does not do

It opens each PDF with the **empty password first**, then with any password the user supplies, and rewrites the file without its encryption dictionary. The empty password is what clears *owner-password* restrictions — the permissions flags courts, agencies and e-discovery vendors stamp on productions to block copying and text extraction. Those files open fine for reading; the flag only blocks downstream tools like OCR.

It does **not** guess, brute-force or recover an unknown password. A PDF with a real user password stays `locked` unless the user supplies the password they were given. Never try to work around that — do not attempt password lists the user did not provide, and do not reach for other tools to break encryption. If a file needs a password the user does not have, say so and stop.

## Steps

1. Run `scripts/unlock.py scan` on the inputs first. It writes nothing and tells you, per file, whether it is already open, carries an owner-password restriction that will clear with no password, or needs a real password.
2. Report what you found before changing anything.
3. If any file needs a real password, ask the user for it — describing that you will try it against those specific files and that it will not be echoed into any report. Pass it with `--password`.
4. Ask whether to write `-unlocked` copies or overwrite the originals in place, describing both:
   - **Write `-unlocked` copies (Recommended)** — originals untouched; each cleared file is saved as `<name>-unlocked.pdf` beside it.
   - **Overwrite in place** — each original is replaced by its cleared version. `ocrdeskew` reads the same filename afterward, so nothing downstream has to change.
5. Run `scripts/unlock.py run` with the chosen flags.
6. Summarize per file: `already_unlocked`, `unlocked`, `locked` or `error`, with output paths. Name every file that stayed locked and why.

Re-running is safe: a file that already has an `-unlocked` sibling is skipped rather than processed twice.

Afterward, offer to OCR the results with `/ocr-batch`.
