# Allocation Scheduler

A lightweight pilot job scheduler for running many tasks within a single HPC allocation.

## Why Use This?

**Traditional HPC workflow:**
```
Job 1 → Queue (2h) → Run (5min) → Done
Job 2 → Queue (2h) → Run (5min) → Done
...
100 jobs × 2h queue = 200 hours waiting
```

**With Allocation Scheduler:**
```
One big job → Queue (2h) → Run 100+ tasks internally → Done
Total time: ~2h queue + actual compute time
```

## What is a Task?

A **Task** is what would traditionally be a separate `sbatch` submission.

**Traditional SLURM** (each run is a separate job):
```bash
sbatch run_T80.sh   →  Queue  →  Run simulation at T=80K
sbatch run_T90.sh   →  Queue  →  Run simulation at T=90K
sbatch run_T100.sh  →  Queue  →  Run simulation at T=100K
# Each waits in queue independently
```

**Allocation Scheduler** (runs are tasks inside one job):
```bash
sbatch submit.sh    →  Queue  →  ┌─────────────────────────┐
                                 │  Your Allocation        │
                                 │  ├── Task: T=80K        │
                                 │  ├── Task: T=90K        │
                                 │  └── Task: T=100K       │
                                 └─────────────────────────┘
# One queue wait, tasks run inside
```

**Mapping traditional jobs to tasks:**

| Traditional SLURM | Allocation Scheduler Task |
|-------------------|---------------------------|
| `sbatch run_T80.sh` (runs `mpirun -np 2 lmp -in T80.in`) | `{"id": "T80", "command": "mpirun -np 2 lmp -in T80.in", "cores": 2}` |
| `sbatch run_T90.sh` (runs `mpirun -np 2 lmp -in T90.in`) | `{"id": "T90", "command": "mpirun -np 2 lmp -in T90.in", "cores": 2}` |

The scheduler handles starting tasks, tracking completion, and cycling new tasks as cores free up—the same job management SLURM does across separate submissions, but now inside one allocation.

## Features

- **Zero dependencies** - Python standard library only
- **Crash recovery** - SQLite-backed state persistence
- **Dynamic tasks** - Add new tasks based on results (callbacks)
- **Priority scheduling** - Control execution order
- **Automatic retries** - Configurable retry on failure
- **Multi-level parallelism** - Run concurrent tasks, each with MPI/threads

## Quick Start

See [DEPLOY.md](DEPLOY.md) for detailed step-by-step instructions.

**Summary:**
1. Edit `submit.sh` for your cluster (partition, cores, time)
2. Transfer files to your HPC cluster
3. Generate `tasks.json` on the cluster
4. Run `sbatch submit.sh`

## File Overview

```
allocation-scheduler/
├── pilot.py              # Core scheduler (this is the engine)
├── submit.sh             # SLURM submit script (edit for your cluster)
├── examples/
│   ├── simple_tasks.py         # Basic demo tasks
│   ├── parameter_sweep.py      # Parameter sweep pattern
│   ├── dynamic_tasks.py        # Adaptive/callback example
│   └── lammps_active_learning.py  # LAMMPS MD example
└── tests/
    └── test_local.py           # Local validation
```

## Task Format

Tasks are defined in `tasks.json`:

```json
[
  {
    "id": "task_001",
    "command": "python process.py --input data1.csv",
    "cores": 1
  },
  {
    "id": "task_002",
    "command": "mpirun -np 4 ./solver input.dat",
    "cores": 4,
    "timeout": 3600,
    "priority": 10
  }
]
```

**Task fields:**
| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique task identifier |
| `command` | Yes | Shell command to execute |
| `cores` | No | Cores needed (default: 1) |
| `timeout` | No | Timeout in seconds |
| `priority` | No | Higher = runs first (default: 0) |
| `max_retries` | No | Retry count on failure (default: 0) |

## Advanced: Customizing pilot.py

The `submit.sh` script calls `pilot.py` internally. If you need to customize behavior, edit the `python pilot.py ...` line in `submit.sh`:

```bash
python pilot.py --cores $SLURM_NTASKS --tasks tasks.json [OPTIONS]

Options:
  --cores N          Total cores available
  --tasks FILE       Path to tasks.json
  --workdir DIR      Output directory (default: ./pilot_runs)
  --db FILE          SQLite database for crash recovery
  --resume           Resume from existing database
  --max-workers N    Max concurrent tasks (default: cores)
```

**Local testing** (before submitting to cluster):
```bash
python examples/simple_tasks.py
python pilot.py --cores 4 --tasks tasks.json
```

## LAMMPS Setup

For the LAMMPS example, install via conda:

```bash
conda create -n lammps_env -c conda-forge lammps -y
conda activate lammps_env
```

Then uncomment the conda lines in `submit.sh` and update the path.

See [DEPLOY.md](DEPLOY.md) for complete LAMMPS instructions.

## How It Works

```
┌─────────────────────────────────────────────┐
│         SLURM Allocation (N cores)          │
├─────────────────────────────────────────────┤
│                                             │
│   pilot.py reads tasks.json                 │
│        ↓                                    │
│   Runs tasks concurrently (up to N cores)   │
│        ↓                                    │
│   As tasks finish, new ones start           │
│        ↓                                    │
│   Results saved to workdir/                 │
│                                             │
└─────────────────────────────────────────────┘
```

## Comparison

| Tool | Dependencies | Setup Time | Best For |
|------|--------------|------------|----------|
| **This** | None | Minutes | Quick experiments, full control |
| GNU Parallel | Shell | Minutes | Simple task lists |
| Parsl | pip install | Hours | Complex DAGs |
| FireWorks | MongoDB | Days | Production campaigns |

## Validated

Tested on CU Boulder Alpine HPC:
```
Completed: 5 | Failed: 0 | Wall: 12.7s | CPU: 41.7s (3.3x speedup)
```
