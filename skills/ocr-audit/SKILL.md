---
name: ocr-audit
description: Assess a local folder's searchable PDF text and OCR readiness without changing originals. Use before choosing an OCRDeskew repair batch; assessment may create temporary copies.
---

# OCR Audit

Read `../ocrdeskew/SKILL.md` for helper locations and CLI validation. This audit
does not change source files. It can run fast OCR into temporary scratch copies
to assess text; explain that it is not a zero-processing metadata-only scan.

1. Confirm the input paths and requested folder recursion.
2. Run `unlock.py scan` to identify restricted PDFs; report them as findings,
   without unlocking or changing them.
3. Run `shotgun.py plan` to report file/page counts, workers, and planned splits.
4. For text assessment, enumerate unencrypted supported input files. Run the
   plain `ocrdeskew` CLI at `--quality fast --json`, with `--out` pointing at a
   fresh scratch directory outside the input folder. Save JSON reports locally;
   read only `ok`, `error`, `audit_status`, `word_count`, and `quality_score`
   into the model context. Do not print extracted text or overwrite originals.
5. Classify files with missing, weak, or usable text, plus restricted/unreadable
   files. State which conclusions are based on fast OCR assessment.
6. Recommend a repair plan and stop. Do not launch the production repair job
   unless already requested. Keep assessment outputs clearly separate from
   repaired deliverables. Remove only scratch files you created when no longer
   needed; leave source files and pre-existing outputs alone.
