---
name: ocr-unlock
description: Clear restrictions from local PDFs using an empty password or passwords the user provides, with the OCRDeskew plugin's local unlock helper. Does not recover unknown passwords.
---

# OCR Unlock

Read `../ocrdeskew/SKILL.md` for the shared `unlock.py` path. It requires
Python 3 plus pypdf or PyPDF2; the OCRDeskew CLI is not required for this route.

Run `unlock.py scan INPUT...` first. It writes nothing. Report files that are
already readable, clearable with an empty password, or require a supplied
password. Ask for a password only for files that need one. Never guess or
brute-force passwords. Use `--password-file` with a user-provided local file
when possible so passwords do not appear in command-line arguments or reports.

Establish whether to write `-unlocked` copies (recommended) or replace originals
in place (destructive). Honor the user's stated choice for this job; request
replacement authorization only if it is missing. Then run:

```bash
python3 "$PLUGIN_ROOT/claude-plugin/skills/ocrdeskew/scripts/unlock.py" run ./production
```

Add `--out DIR`, `--recursive`, `--password-file FILE`, or `--destructive` only
as appropriate to the request. Unknown user passwords stay locked. Summarize
`already_unlocked`, `unlocked`, `locked`, and `error`, with output paths. Never
echo supplied passwords. Continue to OCR only when the user requested it.
