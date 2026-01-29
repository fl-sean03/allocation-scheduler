# Deployment Guide

Complete step-by-step instructions for deploying the Allocation Scheduler on your HPC cluster.

---

## Step 1: Configure for Your Cluster (Local Machine)

Before transferring files, edit `submit.sh` to match your cluster's configuration.

### 1.1 Open submit.sh and update SLURM directives

```bash
#SBATCH --partition=YOUR_PARTITION   # e.g., compute, batch, normal
#SBATCH --qos=YOUR_QOS               # Add this line if your cluster requires QoS
#SBATCH --nodes=1
#SBATCH --ntasks=16                  # Total cores you want
#SBATCH --time=4:00:00               # Wall time (HH:MM:SS)
```

**Common partition names by cluster:**
- TACC (Stampede, Frontera): `normal`, `development`
- NERSC (Perlmutter): `regular`, `debug`
- CU Boulder (Alpine): `amilan`, `atesting`
- Generic PBS/Torque: May need different script format

### 1.2 Add environment setup (if needed)

If your tasks require specific software (Python packages, LAMMPS, etc.), uncomment and edit the environment section:

```bash
# For conda environments:
source /path/to/miniconda3/etc/profile.d/conda.sh
conda activate your_env

# For module systems:
module load python/3.9
module load openmpi/4.1
```

### 1.3 Save your changes

---

## Step 2: Transfer Files to Cluster

Choose your preferred transfer method:

### Option A: Command Line (scp/rsync)

```bash
# Using scp (simple)
scp -r allocation-scheduler/ username@cluster.edu:/scratch/username/

# Using rsync (better for updates)
rsync -avz allocation-scheduler/ username@cluster.edu:/scratch/username/allocation-scheduler/
```

### Option B: Globus

1. Log in to [Globus](https://app.globus.org/)
2. Set source: Your local machine (Globus Connect Personal)
3. Set destination: Your cluster's Globus endpoint
4. Navigate to the `allocation-scheduler/` folder
5. Click "Start" to transfer

### Option C: GUI Tools (WinSCP, FileZilla, Cyberduck)

1. Connect to your cluster via SFTP
   - Host: `cluster.edu`
   - Username: your username
   - Port: 22
2. Navigate to your scratch/work directory
3. Drag and drop the `allocation-scheduler/` folder

### Option D: Git Clone (if you pushed to a repo)

```bash
# SSH to cluster first, then:
cd /scratch/$USER
git clone https://github.com/yourusername/allocation-scheduler.git
```

---

## Step 3: Generate Tasks (On Cluster)

SSH into your cluster and navigate to the project directory:

```bash
ssh username@cluster.edu
cd /scratch/username/allocation-scheduler
```

### 3.1 Choose a task generator

**Option A: Simple test tasks (no dependencies)**
```bash
python examples/simple_tasks.py
```

**Option B: Parameter sweep**
```bash
python examples/parameter_sweep.py
```

**Option C: LAMMPS tasks (requires LAMMPS installed)**
```bash
# Activate your LAMMPS environment first
conda activate lammps_env  # or load modules

python examples/lammps_adaptive_sweep.py
```

**Option D: Create tasks.json manually**
```bash
cat > tasks.json << 'EOF'
[
  {"id": "run_1", "command": "./my_program --input file1.dat", "cores": 2},
  {"id": "run_2", "command": "./my_program --input file2.dat", "cores": 2},
  {"id": "run_3", "command": "./my_program --input file3.dat", "cores": 2}
]
EOF
```

### 3.2 Verify tasks.json was created

```bash
cat tasks.json
# Should show your task definitions
```

---

## Step 4: Submit the Job

```bash
sbatch submit.sh
```

**Expected output:**
```
Submitted batch job 12345678
```

### 4.1 Monitor the job

```bash
# Check queue status
squeue -u $USER

# Watch output in real-time
tail -f pilot_*.out

# Or check stderr for scheduler logs
tail -f pilot_*.err
```

### 4.2 Expected scheduler output

```
============================================================
ALLOCATION SCHEDULER
============================================================
Job ID:      12345678
Partition:   compute
Cores:       16
Start:       Mon Jan 28 10:00:00 MST 2026
============================================================
Tasks file: tasks.json
Task count: 10

10:00:01 [INFO] ▶ run_1 (2c) [14/16 free]
10:00:01 [INFO] ▶ run_2 (2c) [12/16 free]
10:00:01 [INFO] ▶ run_3 (2c) [10/16 free]
...
10:00:15 [INFO] ✓ run_1 (14.2s)
10:00:15 [INFO] ▶ run_4 (2c) [10/16 free]
...
============================================================
FINISHED
============================================================
Completed: 10
Failed: 0
Wall time: 45.3s
```

---

## Step 5: Check Results

After the job completes:

```bash
# View summary
cat runs_12345678/summary.json

# List task outputs
ls runs_12345678/

# Check specific task output
cat runs_12345678/run_1/stdout.txt
cat runs_12345678/run_1/stderr.txt
```

---

## Troubleshooting

### "tasks.json not found"

You need to generate tasks before submitting:
```bash
python examples/simple_tasks.py
```

### Job stuck in queue

Check queue status and limits:
```bash
squeue -u $USER
sacctmgr show qos   # Check QoS limits
```

### Tasks failing

Check individual task stderr:
```bash
cat runs_*/task_name/stderr.txt
```

### "python: command not found"

Add Python to your submit.sh:
```bash
module load python/3.9
# or
source /path/to/conda/etc/profile.d/conda.sh
conda activate base
```

### Resume after timeout

If your job times out, resume from where it left off:
```bash
# Edit submit.sh to add --resume flag and use the existing database
python3 pilot.py --cores $SLURM_NTASKS --db state_OLDJOBID.db --resume
```

---

## LAMMPS-Specific Setup

### Install LAMMPS via Conda

```bash
# On your cluster
conda create -n lammps_env -c conda-forge lammps -y
conda activate lammps_env

# Verify
lmp -h | head -3
which mpirun
```

### Find your conda path

```bash
conda info --base
# Example: /home/user/miniconda3
```

### Update submit.sh

Uncomment and edit the conda lines:
```bash
source /home/user/miniconda3/etc/profile.d/conda.sh
conda activate lammps_env
```

### Generate LAMMPS tasks

```bash
conda activate lammps_env
python examples/lammps_adaptive_sweep.py
sbatch submit.sh
```

---

## Quick Reference

| Step | Command |
|------|---------|
| Edit config | `nano submit.sh` |
| Transfer files | `scp -r allocation-scheduler/ user@cluster:/scratch/user/` |
| Generate tasks | `python examples/simple_tasks.py` |
| Submit job | `sbatch submit.sh` |
| Check status | `squeue -u $USER` |
| View output | `tail -f pilot_*.out` |
| Check results | `cat runs_*/summary.json` |
