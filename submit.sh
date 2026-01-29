#!/bin/bash
#SBATCH --job-name=pilot
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=4:00:00
#SBATCH --output=pilot_%j.out
#SBATCH --error=pilot_%j.err

# ==============================================================================
# Allocation Scheduler - Generic Submit Script
#
# Usage:
#   1. Generate tasks.json first:
#      python examples/simple_tasks.py          # Basic test
#      python examples/parameter_sweep.py       # Parameter sweep
#      python examples/lammps_active_learning.py  # LAMMPS (requires conda env)
#
#   2. Edit this script for your cluster:
#      - Set --partition
#      - Set --qos (if required)
#      - Set --ntasks (total cores)
#      - Add conda/module setup if needed
#
#   3. Submit:
#      sbatch submit.sh
# ==============================================================================

echo "============================================================"
echo "ALLOCATION SCHEDULER"
echo "============================================================"
echo "Job ID:      $SLURM_JOB_ID"
echo "Partition:   $SLURM_JOB_PARTITION"
echo "Nodes:       $SLURM_NNODES"
echo "Cores:       $SLURM_NTASKS"
echo "Nodelist:    $SLURM_NODELIST"
echo "Start:       $(date)"
echo "============================================================"

cd $SLURM_SUBMIT_DIR

# -----------------------------------------------------------------------------
# Environment setup (uncomment/edit as needed)
# -----------------------------------------------------------------------------

# For conda environments (e.g., LAMMPS):
# source /path/to/miniconda3/etc/profile.d/conda.sh
# conda activate lammps_env

# For module-based systems:
# module load python/3.9

# -----------------------------------------------------------------------------
# Check for tasks.json
# -----------------------------------------------------------------------------

if [ ! -f "tasks.json" ]; then
    echo "ERROR: tasks.json not found!"
    echo ""
    echo "Generate tasks first using one of:"
    echo "  python examples/simple_tasks.py"
    echo "  python examples/parameter_sweep.py"
    echo "  python examples/lammps_active_learning.py"
    echo ""
    echo "Or create tasks.json manually. See README.md for format."
    exit 1
fi

echo "Tasks file: tasks.json"
echo "Task count: $(grep -c '"id"' tasks.json)"
echo ""

# -----------------------------------------------------------------------------
# Run scheduler
# -----------------------------------------------------------------------------

python3 pilot.py \
    --cores $SLURM_NTASKS \
    --tasks tasks.json \
    --workdir ./runs_$SLURM_JOB_ID \
    --db state_$SLURM_JOB_ID.db \
    --max-workers $SLURM_NTASKS

EXIT_CODE=$?

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

echo ""
echo "============================================================"
echo "FINISHED"
echo "============================================================"
echo "Exit code: $EXIT_CODE"
echo "End:       $(date)"
echo ""
cat ./runs_$SLURM_JOB_ID/summary.json 2>/dev/null
echo "============================================================"

exit $EXIT_CODE
