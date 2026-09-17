---
description: Audit PDFs for missing or unreliable searchable text without repairing them
argument-hint: [file or folder] (blank to be asked)
---

# OCR Audit

Report the state of the text layer in the documents at `$ARGUMENTS`. **Read-only** — repair nothing.

Use this before committing a large batch to a slow `thorough` run, or to answer "is this production actually searchable?"

## Steps

1. Confirm the paths exist. Name any that do not and stop.
2. Run `scripts/unlock.py scan` to find restricted PDFs. An encrypted file cannot be assessed and is a finding in its own right.
3. Run `scripts/shotgun.py plan` to report the batch size, page count, how it would be parallelized and the worker count this machine supports. This writes nothing.
4. For a text-layer assessment, run `ocrdeskew --quality fast --json` against an output directory in the scratchpad, never over the sources, and read each result's `audit_status`, `word_count` and `quality_score`. Say plainly that this produced throwaway copies for assessment only.
5. Report:
   - Files with **no usable text layer** — these need OCR.
   - Files with a **low-confidence** layer (`quality_score` well under the rest of the batch) — these are the candidates for `thorough`.
   - Files that are **restricted** — these need `/ocr-unlock` first.
   - Files that look **fine** — leave them alone; re-OCR gains nothing and costs time.
6. Recommend a plan: which files to run at which quality, and roughly what it will cost in wall-clock time based on the worker count `plan` reported.

Do not start the repair run from this command. End with the recommendation and let the user choose, then hand off to `/ocr-batch`.
