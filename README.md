# Allocation Scheduler

A lightweight pilot job scheduler for running many tasks within a single HPC allocation.

## The Problem

Traditional HPC workflow:
```
Job 1 → Queue (2h) → Run (5min) → Done
Job 2 → Queue (2h) → Run (5min) → Done
...
100 jobs × 2h queue = 200 hours waiting
```

Allocation Scheduler workflow:
```
BIG JOB → Queue (2h) → [Your allocation for 24h]
                            ↓
                    Run 100+ tasks internally
                    YOU control the scheduling
```

## Features

- **Zero external dependencies** - Only Python standard library
- **Persistent state** - SQLite-backed, survives crashes
- **Dynamic task generation** - Add tasks on-the-fly via callbacks
- **Priority scheduling** - Control what runs first
- **Retry logic** - Automatic retries on failure
- **Multi-level parallelism** - Concurrent tasks, each with internal parallelism (MPI, threads, etc.)

## Quick Start

### 1. Define Tasks (tasks.json)

```json
[
  {"id": "task_1", "command": "python process.py --input data1.csv", "cores": 1},
  {"id": "task_2", "command": "python process.py --input data2.csv", "cores": 1},
  {"id": "task_3", "command": "./my_binary --threads 4", "cores": 4}
]
```

### 2. Run Locally

```bash
python pilot.py --cores 8 --tasks tasks.json
```

### 3. Run on SLURM

```bash
sbatch submit.sh
```

## Examples

| Example | Description |
|---------|-------------|
| `examples/simple_tasks.py` | Basic task generation (no dependencies) |
| `examples/parameter_sweep.py` | Parameter sweep pattern |
| `examples/dynamic_tasks.py` | Adding tasks based on results (callbacks) |
| `examples/lammps_active_learning.py` | Real-world: LAMMPS MD with active learning |

### Run a Simple Example

```bash
# Generate tasks
python examples/simple_tasks.py

# Run scheduler
python pilot.py --cores 4 --tasks tasks.json --workdir ./runs
```

## Task Definition

```python
from pilot import Task

task = Task(
    id="my_task",           # Unique identifier
    command="./run.sh",     # Shell command to execute
    cores=2,                # Cores this task needs
    timeout=3600,           # Timeout in seconds (optional)
    priority=10,            # Higher = runs first (optional)
    max_retries=2,          # Retry on failure (optional)
    env={"VAR": "value"},   # Environment variables (optional)
    tags={"param": 42},     # Metadata for callbacks (optional)
)
```

## Dynamic Task Generation

Add tasks based on results using callbacks:

```python
from pilot import Pilot, Task, TaskResult

def on_complete(task: Task, result: TaskResult, pilot: Pilot):
    """Called after each task completes."""
    if result.success and should_explore_further(result):
        return [Task(id="followup", command="...")]
    return None

pilot = Pilot(total_cores=8)
pilot.on_complete(on_complete)
pilot.load_json("tasks.json")
pilot.run()
```

## CLI Options

```
python pilot.py --cores 8 --tasks tasks.json [OPTIONS]

Required:
  --cores N          Total cores in allocation
  --tasks FILE       JSON file with task definitions

Optional:
  --workdir DIR      Output directory (default: ./pilot_runs)
  --db FILE          SQLite database for persistence/resume
  --resume           Resume from database after crash
  --max-workers N    Max concurrent tasks (default: cores)
```

## Architecture

```
┌─────────────────────────────────────────────┐
│         SLURM Allocation (N cores)          │
├─────────────────────────────────────────────┤
│                                             │
│   ┌─────────────────────────────────────┐   │
│   │       pilot.py (scheduler)          │   │
│   │                                     │   │
│   │  Queue ──► Workers ──► Results      │   │
│   │    │           │          │         │   │
│   │    └─── Callbacks ◄───────┘         │   │
│   │       (dynamic generation)          │   │
│   └─────────────────────────────────────┘   │
│                                             │
│   Worker 1: python process.py --id 1        │
│   Worker 2: ./simulate --threads 4          │
│   Worker 3: mpirun -np 2 solver input.dat   │
│   (cycling as tasks complete)               │
│                                             │
└─────────────────────────────────────────────┘
```

## Use Cases

- **Parameter sweeps** - Vary any parameter across runs
- **Ensemble runs** - Multiple random seeds / initial conditions
- **Adaptive workflows** - Results → decide next run → execute
- **High-throughput screening** - Process 1000s of inputs
- **Any embarrassingly parallel workload**

## Crash Recovery

```bash
# Start with persistence
python pilot.py --cores 8 --tasks tasks.json --db state.db

# After crash/timeout, resume
python pilot.py --cores 8 --db state.db --resume
```

## SLURM Integration

Basic submit script:

```bash
#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=4:00:00

python pilot.py --cores $SLURM_NTASKS --tasks tasks.json --db state.db
```

## Comparison with Other Tools

| Tool | Dependencies | Setup | Best For |
|------|--------------|-------|----------|
| **This** | None (stdlib) | Minutes | Quick experiments, full control |
| GNU Parallel | Shell | Minutes | Simple task lists |
| Parsl | `pip install` | Hours | Large scale, complex DAGs |
| FireWorks | MongoDB | Days | Production campaigns |
| RADICAL-Pilot | pip + config | Hours | True pilot jobs at scale |

## Files

| File | Purpose |
|------|---------|
| `pilot.py` | Core scheduler (~200 lines, stdlib only) |
| `examples/` | Task generators for various patterns |
| `submit_*.sh` | SLURM scripts for different partitions |
| `tests/` | Local validation tests |

## LAMMPS Example

The `examples/lammps_active_learning.py` demonstrates running parallel LAMMPS simulations with active learning (dynamic task generation based on results).

### Prerequisites

LAMMPS with MPI support. Recommended: install via conda:

```bash
# Create environment
conda create -n lammps_env -c conda-forge lammps -y

# Verify installation
conda activate lammps_env
lmp -h | head -3
which mpirun
```

### Running the LAMMPS Example

```bash
# Generate temperature sweep tasks
python examples/lammps_active_learning.py

# Run with allocation scheduler (8 cores, 4 concurrent 2-core tasks)
python pilot.py --cores 8 --tasks tasks.json --max-workers 4
```

### SLURM Submit Script for LAMMPS

```bash
#!/bin/bash
#SBATCH --partition=your_partition
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=1:00:00

# Activate conda environment
source /path/to/miniconda3/etc/profile.d/conda.sh
conda activate lammps_env

# Generate and run tasks
python examples/lammps_active_learning.py
python pilot.py --cores $SLURM_NTASKS --tasks tasks.json --max-workers 4
```

### Task Structure

Each LAMMPS task runs with MPI parallelism:

```python
Task(
    id="sim_T100",
    command="mpirun -np 2 lmp -in input.lmp",
    cores=2,  # Reserve 2 cores for this task
)
```

The scheduler runs multiple such tasks concurrently, cycling new tasks as others complete.

## Validated

Tested on CU Boulder Alpine HPC (atesting & amilan partitions):

```
▶ T80 (2c)  ▶ T100 (2c)  ▶ T120 (2c)  ▶ T90 (2c)
✓ T120 (8.3s) → ▶ T110 (2c)
✓ T80, T90, T100, T110 complete

Completed: 5 | Failed: 0 | Wall time: 12.7s | CPU time: 41.7s (3.3x speedup)
```
