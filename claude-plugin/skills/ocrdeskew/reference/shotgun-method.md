# Shotgun Method — sizing, chunking and tuning

Reference detail for `scripts/shotgun.py`. The skill's SKILL.md covers when to
use it; this covers how it decides what it decides.

## Why it exists

`ocrdeskew` processes one input at a time in one process. On a modern machine
that leaves most of the CPU idle for the length of a batch. The Shotgun Method
runs many `ocrdeskew` processes concurrently and, when there are not enough
files to go around, splits large PDFs into page ranges so the parallelism has
something to chew on.

Nothing here reimplements OCR. Every page is still processed by `ocrdeskew`
itself; this is scheduling and reassembly only.

## Worker sizing

`shotgunlib/cpu.py`:

```
cpu_ceiling    = logical_cpus - 2          # leave the machine usable
memory_ceiling = total_ram_gb // per_worker_gb
workers        = min(cpu_ceiling, memory_ceiling, 32)
workers        = min(workers, total_work_units)
```

`per_worker_gb` by quality: `fast` 0.8, `balanced` 1.2, `thorough` 2.0. A
worker holds a rendered 300-DPI page bitmap, so memory becomes the binding
ceiling before cores do on small-RAM machines running `thorough`.

Each worker runs with `OMP_THREAD_LIMIT=1` (and the matching OpenBLAS/MKL/
NumExpr variables). Without this, tesseract's own OpenMP pool would expand
inside every worker and the workers would thrash each other — plain
`ocrdeskew` measured ~486% CPU on a single file, so N workers unconstrained
would oversubscribe badly.

`--workers N` overrides the whole calculation.

## Chunking

`shotgunlib/planner.py`:

- Target is `workers × 2` work units, so a slow page cannot strand a core.
- If the file count already meets that target, nothing is split — file-level
  fan-out only, and no merge step ever runs.
- Otherwise the page-heaviest PDFs are split first, until the target is met.
- Chunk size is clamped to 2–40 pages. Below 2 the process startup starts to
  matter; above 40 a chunk becomes its own bottleneck.
- Only PDFs with at least 4 pages are eligible to split. Images never are.
- `--no-split` disables page-level splitting entirely.

## Safety model

A source file is only touched after all of this passes:

1. Every one of its units exited zero and reported `ok` in `ocrdeskew`'s JSON.
   A failed unit gets one automatic retry first (`--retries`).
2. For split files, the chunks merged in page order without error.
3. The assembled PDF exists, is non-empty, starts with `%PDF-`, and has
   **exactly** the original page count.

If any step fails, the file is reported failed with its reason and the original
is left exactly as it was. In destructive mode the replacement is an
`os.replace` of a fully written temp file, so there is no window where the
original is truncated or half-written.

`--backup-dir` copies each original (with `copy2`, preserving timestamps)
before its destructive overwrite.

Images in destructive mode produce `<name>.pdf` beside the source and keep the
source image — a PNG cannot hold a PDF text layer.

All intermediate chunks and per-unit outputs live in a `mkdtemp` directory that
is removed on exit, including on failure.

## Measured

MacBook, 18 logical CPUs (6 performance / 12 efficiency), 36 GB RAM, one
24-page scanned PDF at `--quality balanced`:

| Run | Wall clock | Peak CPU | Words | Pages |
|---|---|---|---|---|
| Plain `ocrdeskew` | 5m 02s | 486% | 4361 | 24 |
| Shotgun, 12 workers | 1m 46s | 1499% | 4361 | 24 |

A 7-file / 48-page folder at `--quality fast` finished in 24.6s across 16
workers and 24 units.

Identical word count; page count preserved through split and merge. Speedup
scales with available units — a folder of many files saturates more workers
than a single PDF that can only be cut so fine.

## Dependencies

- `python3`
- `qpdf` (preferred for split/merge — tolerates damaged scanner output) or the
  `pypdf` package as fallback
- `ocrdeskew` on `PATH`

With none of the PDF tools present, page-level splitting is unavailable;
file-level fan-out still works for multi-file batches.
