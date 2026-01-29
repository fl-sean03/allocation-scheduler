#!/usr/bin/env python3
"""
LAMMPS Adaptive Sweep Example

Demonstrates:
1. Initial temperature sweep (exploration)
2. Dynamic task generation based on results (adaptive refinement)
3. Parallel execution on HPC

Usage:
    python lammps_adaptive_sweep.py  # Generates tasks.json and input template
    python pilot.py --cores 8 --tasks tasks.json --db state.db
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from pilot import Task, TaskResult, Pilot


# =============================================================================
# Configuration
# =============================================================================

# Temperature range to explore (Kelvin)
T_MIN = 80.0
T_MAX = 120.0
T_STEP = 10.0  # Initial spacing

# Refinement settings
REFINE_THRESHOLD = 0.8  # Refine if diffusion is "interesting" (normalized)
REFINE_DELTA = 2.5      # Temperature delta for refinement points
MAX_TASKS = 20          # Stop after this many total tasks

# Resource settings
CORES_PER_TASK = 2
TASK_TIMEOUT = 300      # 5 minutes per simulation


# =============================================================================
# LAMMPS Input Generation
# =============================================================================

LAMMPS_INPUT_TEMPLATE = """# Liquid Argon MD - Temperature {temperature}K
# For allocation scheduler adaptive sweep demo
# Source: Rahman, Phys. Rev. 136, A405 (1964)

units           real
atom_style      atomic
boundary        p p p

# Create FCC argon lattice (will melt to liquid)
lattice         fcc 5.26
region          box block 0 4 0 4 0 4
create_box      1 box
create_atoms    1 box
mass            1 39.948

# LJ potential - Rahman 1964 parameters
# epsilon/kB = 119.8 K = 0.238 kcal/mol, sigma = 3.405 A
pair_style      lj/cut 10.0
pair_coeff      1 1 0.238 3.405

# Initialize velocities
velocity        all create {temperature} {seed} dist gaussian

# Equilibration (short for demo)
fix             1 all nvt temp {temperature} {temperature} 100.0
timestep        2.0
thermo          100
thermo_style    custom step temp pe ke etotal press

run             1000

# Production with MSD
reset_timestep  0
compute         msd all msd
fix             msd_out all ave/time 10 10 100 c_msd[4] file msd.dat

run             2000

# Report final MSD for parsing
variable        final_msd equal c_msd[4]
print           "FINAL_MSD: ${{final_msd}}"
print           "TEMPERATURE: {temperature}"
print           "SIMULATION_COMPLETE"
"""


def create_lammps_input(temperature: float, seed: int = 12345) -> str:
    """Generate LAMMPS input file content."""
    return LAMMPS_INPUT_TEMPLATE.format(
        temperature=temperature,
        seed=seed + int(temperature * 100),
    )


# =============================================================================
# Task Generation
# =============================================================================

def create_task(temperature: float, phase: str = "exploration") -> Task:
    """Create a LAMMPS task for a given temperature."""
    task_id = f"{phase}_T{temperature:.1f}".replace(".", "p")

    # The command will create input file and run LAMMPS
    # Note: Input file is created by the pre-run script
    command = f"""
# Create input file
cat > input.lmp << 'LAMMPS_EOF'
{create_lammps_input(temperature)}
LAMMPS_EOF

# Run LAMMPS (mpirun from conda env)
mpirun -np {CORES_PER_TASK} lmp -in input.lmp -log log.lammps
"""

    return Task(
        id=task_id,
        command=command,
        cores=CORES_PER_TASK,
        timeout=TASK_TIMEOUT,
        priority=10 if phase == "refinement" else 0,
        tags={
            "temperature": temperature,
            "phase": phase,
        },
    )


def generate_initial_tasks() -> List[Task]:
    """Generate initial exploration tasks."""
    tasks = []
    T = T_MIN
    while T <= T_MAX:
        tasks.append(create_task(T, "exploration"))
        T += T_STEP
    return tasks


# =============================================================================
# Adaptive Refinement Callback
# =============================================================================

# Track what we've done
explored_temperatures = set()
results_history = []


def parse_msd_from_output(result: TaskResult) -> Optional[float]:
    """Extract final MSD from LAMMPS output."""
    try:
        stdout_path = Path(result.stdout_file)
        if not stdout_path.exists():
            return None

        content = stdout_path.read_text()
        for line in content.split('\n'):
            if 'FINAL_MSD:' in line:
                return float(line.split(':')[1].strip())
    except Exception:
        pass
    return None


def on_task_complete(task: Task, result: TaskResult, pilot: Pilot) -> Optional[List[Task]]:
    """
    Adaptive refinement callback - decide whether to explore nearby temperatures.

    This is called after each task completes.
    """
    if not result.success:
        return None

    temperature = task.tags.get("temperature")
    if temperature is None:
        return None

    explored_temperatures.add(temperature)

    # Parse MSD
    msd = parse_msd_from_output(result)
    if msd is None:
        print(f"  [Adaptive] Could not parse MSD for T={temperature}")
        return None

    results_history.append({
        "temperature": temperature,
        "msd": msd,
        "task_id": task.id,
    })

    print(f"  [Adaptive] T={temperature}K, MSD={msd:.2f}")

    # Check task limit
    total_done = len(pilot.completed) + len(pilot.failed)
    total_pending = pilot.pending.qsize() + len(pilot.running)
    if total_done + total_pending >= MAX_TASKS:
        print(f"  [Adaptive] Reached max tasks ({MAX_TASKS})")
        return None

    # Adaptive refinement: explore around interesting temperatures
    # "Interesting" = high MSD (high diffusion region)
    if len(results_history) < 3:
        return None  # Need more data

    msds = [r["msd"] for r in results_history]
    max_msd = max(msds)
    normalized = msd / max_msd if max_msd > 0 else 0

    if normalized > REFINE_THRESHOLD:
        # This is an interesting region - explore nearby
        new_tasks = []
        for delta in [-REFINE_DELTA, REFINE_DELTA]:
            new_T = temperature + delta
            if T_MIN <= new_T <= T_MAX and new_T not in explored_temperatures:
                explored_temperatures.add(new_T)
                new_tasks.append(create_task(new_T, "refinement"))
                print(f"  [Adaptive] → Refining at T={new_T}K")

        return new_tasks if new_tasks else None

    return None


# =============================================================================
# Main
# =============================================================================

def main():
    """Generate initial tasks and write to JSON."""
    print("LAMMPS Adaptive Sweep Task Generator")
    print("=" * 50)

    # Generate initial tasks
    tasks = generate_initial_tasks()
    print(f"Generated {len(tasks)} initial exploration tasks")
    print(f"Temperature range: {T_MIN}K to {T_MAX}K")
    print(f"Step size: {T_STEP}K")

    # Write tasks.json
    tasks_json = [t.to_dict() for t in tasks]
    output_path = Path(__file__).parent.parent / "tasks.json"
    with open(output_path, 'w') as f:
        json.dump(tasks_json, f, indent=2)
    print(f"\nWrote: {output_path}")

    # Write callback module
    callback_path = Path(__file__).parent.parent / "adaptive_callback.py"
    callback_code = '''"""Adaptive refinement callback - import into pilot."""
from examples.lammps_adaptive_sweep import on_task_complete
'''
    with open(callback_path, 'w') as f:
        f.write(callback_code)
    print(f"Wrote: {callback_path}")

    print("\nTo run:")
    print("  python pilot.py --cores 8 --tasks tasks.json --db state.db")

    # For demo: initialize explored set from tasks
    for t in tasks:
        explored_temperatures.add(t.tags["temperature"])


if __name__ == "__main__":
    main()
