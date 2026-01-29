#!/bin/bash
#SBATCH --job-name=pilot_test
#SBATCH --partition=atesting
#SBATCH --qos=testing
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=01:00:00
#SBATCH --output=pilot_%j.out
#SBATCH --error=pilot_%j.err

echo "============================================================"
echo "PILOT JOB STARTING"
echo "============================================================"
echo "Job ID:      $SLURM_JOB_ID"
echo "Partition:   $SLURM_JOB_PARTITION"
echo "Cores:       $SLURM_NTASKS"
echo "Node:        $SLURM_NODELIST"
echo "Start:       $(date)"
echo "============================================================"

# Environment - use conda lammps_env
source /projects/sefl7948/new-software/miniconda3/etc/profile.d/conda.sh
conda activate lammps_env

echo ""
echo "Environment:"
echo "  Python: $(which python3)"
echo "  LAMMPS: $(which lmp)"
echo "  mpirun: $(which mpirun)"
echo ""

cd $SLURM_SUBMIT_DIR

# Generate initial tasks
python3 examples/lammps_adaptive_sweep.py

# Run pilot scheduler
python3 pilot.py \
    --cores $SLURM_NTASKS \
    --tasks tasks.json \
    --workdir ./runs_$SLURM_JOB_ID \
    --db state_$SLURM_JOB_ID.db \
    --max-workers 4

EXIT_CODE=$?

echo ""
echo "============================================================"
echo "PILOT JOB FINISHED"
echo "============================================================"
echo "Exit code: $EXIT_CODE"
echo "End:       $(date)"
ls -la ./runs_$SLURM_JOB_ID/ 2>/dev/null | head -15
echo "============================================================"

exit $EXIT_CODE
