# Deployment Guide

## Quick Start (Any SLURM Cluster)

### 1. Upload to Cluster

```bash
# From local machine
scp -r allocation-scheduler/ user@cluster:/scratch/$USER/
```

### 2. Test Locally on Login Node

```bash
ssh user@cluster
cd /scratch/$USER/allocation-scheduler

# Generate simple test tasks
python3 examples/simple_tasks.py

# Run with 2 cores (quick test)
python3 pilot.py --cores 2 --tasks tasks.json --workdir ./test_run
```

### 3. Submit to Queue

```bash
# Edit submit.sh for your cluster's partitions
nano submit.sh

# Submit
sbatch submit.sh

# Monitor
tail -f pilot_*.out
```

## Customization

### Your Own Task Generator

Create a Python script that generates `tasks.json`:

```python
from pilot import Task
import json

tasks = []
for i in range(100):
    tasks.append(Task(
        id=f"task_{i}",
        command=f"./my_program --input data_{i}.txt",
        cores=4,
        timeout=3600,
    ))

with open("tasks.json", "w") as f:
    json.dump([t.to_dict() for t in tasks], f)
```

### Multi-Core Tasks

For tasks using MPI or threads:

```python
Task(
    id="mpi_task",
    command="mpirun -np 4 ./solver input.dat",
    cores=4,  # Reserve 4 cores
)
```

### Different Partitions

Edit the SBATCH directives in `submit.sh`:

```bash
#SBATCH --partition=gpu      # GPU partition
#SBATCH --gres=gpu:1         # Request GPU
#SBATCH --ntasks=8
#SBATCH --time=24:00:00
```

### Conda/Module Environment

Add to submit script:

```bash
# Conda
source ~/miniconda3/etc/profile.d/conda.sh
conda activate myenv

# Or modules
module load python/3.9
module load openmpi/4.1
```

## Crash Recovery

If your job times out or crashes:

```bash
# Submit new job with --resume
sbatch submit_resume.sh
```

Where `submit_resume.sh` contains:
```bash
python3 pilot.py --cores $SLURM_NTASKS --db state_OLDJOBID.db --resume
```

## Troubleshooting

### Tasks Failing

Check task stderr:
```bash
cat runs_JOBID/task_001/stderr.txt
```

### No Output

Verify Python path:
```bash
which python3
python3 --version
```

### Database Locked

Previous job still running:
```bash
squeue -u $USER
scancel JOBID
```

## Examples

| Example | Command |
|---------|---------|
| Simple test | `python examples/simple_tasks.py` |
| Parameter sweep | `python examples/parameter_sweep.py` |
| Dynamic/adaptive | `python examples/dynamic_tasks.py` |
| LAMMPS | `python examples/lammps_active_learning.py` |

## LAMMPS Setup

The LAMMPS example requires LAMMPS with MPI support. The recommended approach is conda:

### 1. Install LAMMPS via Conda

```bash
# On your HPC cluster
conda create -n lammps_env -c conda-forge lammps -y
conda activate lammps_env

# Verify
lmp -h | head -3
mpirun --version
```

### 2. Find Your Conda Path

```bash
conda info --base
# Example output: /home/user/miniconda3
# Or: /projects/user/software/miniconda3
```

### 3. Update Submit Script

Edit `submit_atesting.sh` or create your own:

```bash
#!/bin/bash
#SBATCH --partition=your_partition
#SBATCH --qos=your_qos
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=1:00:00
#SBATCH --output=pilot_%j.out
#SBATCH --error=pilot_%j.err

# IMPORTANT: Update this path to your conda installation
source /path/to/miniconda3/etc/profile.d/conda.sh
conda activate lammps_env

cd $SLURM_SUBMIT_DIR

# Generate LAMMPS tasks
python3 examples/lammps_active_learning.py

# Run scheduler (8 cores total, max 4 concurrent tasks)
python3 pilot.py \
    --cores $SLURM_NTASKS \
    --tasks tasks.json \
    --workdir ./runs_$SLURM_JOB_ID \
    --db state_$SLURM_JOB_ID.db \
    --max-workers 4
```

### 4. Submit

```bash
sbatch submit_atesting.sh
tail -f pilot_*.err  # Scheduler output goes to stderr
```

### Expected Output

```
▶ exploration_T80p0 (2c) [6/8 free]
▶ exploration_T100p0 (2c) [4/8 free]
▶ exploration_T120p0 (2c) [2/8 free]
✓ exploration_T120p0 (8.3s)
▶ exploration_T110p0 (2c)
...
PILOT FINISHED
  Completed: 5
  Failed: 0
  Wall time: 12.7s
  CPU time: 41.7s
```
