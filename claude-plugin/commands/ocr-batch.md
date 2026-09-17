---
description: OCR and deskew a file or folder into searchable PDFs, with parallel batch processing
argument-hint: [file or folder] (blank to be asked)
---

# OCR Batch

Repair the OCR text layer of the documents at `$ARGUMENTS` and write searchable PDFs.

Use the `ocrdeskew` skill for this. Follow it exactly — in particular, ask the three setup questions (output mode, quality, Shotgun Method) before running anything, with a short plain-language description on every option. Do not assume defaults.

If `$ARGUMENTS` is empty, ask which file or folder to process first, describing what you will do with it.

Steps:

1. Confirm the paths exist. Name any that do not and stop rather than letting the CLI fail.
2. Check for restricted PDFs with `scripts/unlock.py scan` before OCR. An encrypted PDF cannot be read by `ocrdeskew`. If any are found, tell the user which ones and offer to clear them (see the `/ocr-unlock` command) before continuing.
3. Ask the three setup questions.
4. Run `scripts/shotgun.py plan` first for any batch you have not seen, and show the user the worker count and chunking.
5. Run, then summarize using the skill's summary template: output paths, success and failure counts, per-file word counts and quality scores, elapsed time, and the worker count used.
6. Name every low-confidence or failed file explicitly. Offer the `ocr-triage` agent for those — do not escalate on your own.
