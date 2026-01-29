#!/bin/bash
#SBATCH --job-name=pilot_prod
#SBATCH --partition=amilan128c
#SBATCH --nodes=1
#SBATCH --ntasks=64
#SBATCH --time=24:00:00
#SBATCH --output=pilot_%j.out
#SBATCH --error=pilot_%j.err
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=your@email.com

# ==============================================================================
# Allocation Scheduler - Production on amilan128c (128 cores, 24 hours)
#
# Using amilan128c: All 128 cores on ONE node (no inter-node overhead)
# - Only 16 nodes available → longer queue times (hours to days)
# - But perfect for allocation scheduler: all tasks share same node
#
# Alternative: Use amilan with --nodes=2 --ntasks=64 for shorter queue
#
# Run after validating on atesting!
# ==============================================================================

echo "============================================================"
echo "PILOT JOB STARTING (PRODUCTION)"
echo "============================================================"
echo "Job ID:      $SLURM_JOB_ID"
echo "Partition:   $SLURM_JOB_PARTITION"
echo "Nodes:       $SLURM_NNODES"
echo "Cores:       $SLURM_NTASKS"
echo "Nodelist:    $SLURM_NODELIST"
echo "Start:       $(date)"
echo "============================================================"

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------

# Conda environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lammps_env

echo ""
echo "Environment:"
echo "  Python:    $(which python3)"
echo "  LAMMPS:    $(which lmp)"
echo "  mpirun:    $(which mpirun)"
echo "  Conda env: $CONDA_DEFAULT_ENV"
echo ""

# -----------------------------------------------------------------------------
# Run pilot
# -----------------------------------------------------------------------------

cd $SLURM_SUBMIT_DIR

# Use existing tasks or generate new ones
if [ -f "tasks.json" ]; then
    echo "Using existing tasks.json"
else
    echo "Generating tasks..."
    python3 examples/lammps_active_learning.py
fi

# Run pilot scheduler
# max-workers limits concurrent tasks to avoid oversubscription
python3 pilot.py \
    --cores $SLURM_NTASKS \
    --tasks tasks.json \
    --workdir ./runs_$SLURM_JOB_ID \
    --db state_$SLURM_JOB_ID.db \
    --max-workers 64

EXIT_CODE=$?

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------

echo ""
echo "============================================================"
echo "PILOT JOB FINISHED"
echo "============================================================"
echo "Exit code: $EXIT_CODE"
echo "End:       $(date)"
echo ""
echo "Results summary:"
cat ./runs_$SLURM_JOB_ID/summary.json 2>/dev/null
echo "============================================================"

exit $EXIT_CODE
