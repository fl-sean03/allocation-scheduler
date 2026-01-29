#!/bin/bash
#SBATCH --job-name=pilot
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=4:00:00
#SBATCH --output=pilot_%j.out
#SBATCH --error=pilot_%j.err

# ==============================================================================
# Generic Allocation Scheduler Submit Script
#
# Customize:
#   --partition    Your cluster's partition
#   --ntasks       Cores you want
#   --time         Wall time
#
# Usage:
#   sbatch submit.sh
# ==============================================================================

echo "============================================================"
echo "ALLOCATION SCHEDULER STARTING"
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
# Generate tasks (if not already present)
# Replace with your task generator
# -----------------------------------------------------------------------------

if [ ! -f "tasks.json" ]; then
    echo "Generating tasks..."
    python3 examples/simple_tasks.py
fi

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
echo "ALLOCATION SCHEDULER FINISHED"
echo "============================================================"
echo "Exit code: $EXIT_CODE"
echo "End:       $(date)"
echo ""
echo "Results:"
cat ./runs_$SLURM_JOB_ID/summary.json 2>/dev/null
echo "============================================================"

exit $EXIT_CODE
