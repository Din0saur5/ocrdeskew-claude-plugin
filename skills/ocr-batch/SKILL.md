---
name: ocr-batch
description: Repair a file or folder into searchable PDFs with OCRDeskew, including optional parallel Shotgun processing. Use for batch OCR and deskew requests with local files.
---

# OCR Batch

Read `../ocrdeskew/SKILL.md` for helper locations, validation, settings, and
report fields. Preserve the user's choices already established for this job.

1. Confirm every input path exists. Ask for a path if absent.
2. Scan PDF restrictions with the shared `unlock.py scan` helper. Report locked
   files and, if needed, use `../ocr-unlock/SKILL.md` before OCR. Do not silently
   change encrypted originals. Pass unlocked outputs into repair rather than
   processing both the encrypted original and its unlocked copy.
3. Establish output mode, quality, and parallelism as described in the main skill.
4. Run `shotgun.py plan` with the selected quality, recursion, and worker options.
   Show the planned workers and any page splitting.
5. Run `shotgun.py run` with the selected settings. For serial processing, use
   `--workers 1 --no-split`. For direct CLI calls, expand folder inputs into file
   paths first, use `--json`, and give batch outputs a directory with `--out`.
6. Summarize outputs, successful and failed files, quality scores, word counts,
   duration, and workers. Original images are retained even if replacement was
   chosen. Name low-confidence and failed files; use `../ocr-triage/SKILL.md`
   when diagnosis is requested. Do not automatically escalate to external AI.
