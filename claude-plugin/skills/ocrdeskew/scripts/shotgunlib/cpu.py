"""Machine capability detection and worker-count recommendation.

The Shotgun Method fans `ocrdeskew` out across many OS processes. How many is
safe depends on two ceilings: CPU threads and RAM. OCR at 300 DPI holds a full
rendered page bitmap per worker, so memory is the binding constraint on
thorough runs more often than cores are.
"""

import os
import platform
import subprocess

# Leave headroom so the machine stays usable while a batch runs.
RESERVED_CPUS = 2
MAX_WORKERS = 32

# Approximate peak resident memory per worker, by quality mode (GB).
MEMORY_PER_WORKER_GB = {"fast": 0.8, "balanced": 1.2, "thorough": 2.0}

# Each worker is one process; tesseract's OpenMP pool would multiply that.
SINGLE_THREAD_ENV = {
    "OMP_THREAD_LIMIT": "1",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def _sysctl_int(key):
    try:
        out = subprocess.run(
            ["sysctl", "-n", key], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


def _memory_gb():
    memsize = _sysctl_int("hw.memsize")
    if memsize:
        return memsize / (1024 ** 3)
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return 8.0  # Conservative floor when the platform will not say.


def detect_machine():
    """Return a snapshot of the CPU/memory resources available for fan-out."""
    logical = os.cpu_count() or 1
    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "logical_cpus": logical,
        "performance_cpus": _sysctl_int("hw.perflevel0.logicalcpu"),
        "efficiency_cpus": _sysctl_int("hw.perflevel1.logicalcpu"),
        "physical_cpus": _sysctl_int("hw.physicalcpu") or logical,
        "memory_gb": round(_memory_gb(), 1),
    }


def recommend_workers(quality, machine=None, unit_count=None):
    """Recommend a parallel worker count, with the reasoning that produced it.

    Returns (workers, explanation).
    """
    machine = machine or detect_machine()
    per_worker = MEMORY_PER_WORKER_GB.get(quality, MEMORY_PER_WORKER_GB["balanced"])

    cpu_cap = max(1, machine["logical_cpus"] - RESERVED_CPUS)
    memory_cap = max(1, int(machine["memory_gb"] // per_worker))
    workers = min(cpu_cap, memory_cap, MAX_WORKERS)

    binding = "CPU"
    if memory_cap < cpu_cap:
        binding = "memory"
    elif workers == MAX_WORKERS:
        binding = "hard cap"

    if unit_count:
        workers = min(workers, unit_count)

    explanation = (
        f"{machine['logical_cpus']} logical CPUs, {machine['memory_gb']} GB RAM; "
        f"CPU ceiling {cpu_cap} (reserving {RESERVED_CPUS}), "
        f"memory ceiling {memory_cap} (~{per_worker} GB/worker at --quality {quality}); "
        f"{binding}-bound"
    )
    if unit_count:
        explanation += f"; capped at {unit_count} work unit(s)"
    return workers, explanation


def worker_env():
    """Environment for a worker process: one OCR thread each, no oversubscription."""
    env = dict(os.environ)
    env.update(SINGLE_THREAD_ENV)
    return env
