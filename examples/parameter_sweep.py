#!/usr/bin/env python3
"""
Parameter Sweep Example

Demonstrates a common HPC pattern: running the same program
with different parameter combinations.

Usage:
    python examples/parameter_sweep.py
    python pilot.py --cores 8 --tasks tasks.json
"""

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pilot import Task


# Example: Sweep over multiple parameters
PARAMS = {
    "alpha": [0.1, 0.5, 1.0],
    "beta": [10, 50, 100],
    "seed": [42, 123, 456],
}


def generate_sweep_tasks(
    command_template: str,
    params: dict,
    cores_per_task: int = 1,
) -> list:
    """
    Generate tasks for all parameter combinations.

    Args:
        command_template: Command with {param} placeholders
        params: Dict of param_name -> list of values
        cores_per_task: Cores each task needs

    Returns:
        List of Task objects
    """
    tasks = []

    # Generate all combinations
    keys = list(params.keys())
    values = list(params.values())

    for combo in itertools.product(*values):
        param_dict = dict(zip(keys, combo))

        # Create task ID from parameters
        task_id = "_".join(f"{k}{v}" for k, v in param_dict.items())
        task_id = task_id.replace(".", "p")  # Sanitize

        # Format command
        command = command_template.format(**param_dict)

        task = Task(
            id=task_id,
            command=command,
            cores=cores_per_task,
            timeout=300,
            tags=param_dict,
        )
        tasks.append(task)

    return tasks


def main():
    print("Parameter Sweep Generator")
    print("=" * 40)

    # Example command - replace with your actual program
    # This demo just echoes parameters and does fake "work"
    command_template = """
echo "Running with alpha={alpha}, beta={beta}, seed={seed}"
echo "alpha={alpha}" > result.txt
echo "beta={beta}" >> result.txt
echo "seed={seed}" >> result.txt

# Simulate work
sleep 2

# Fake output
result=$(echo "scale=4; {alpha} * {beta} / 100" | bc)
echo "result=$result" >> result.txt
echo "Completed: result=$result"
"""

    tasks = generate_sweep_tasks(
        command_template=command_template,
        params=PARAMS,
        cores_per_task=1,
    )

    print(f"Parameters: {PARAMS}")
    print(f"Total combinations: {len(tasks)}")

    # Write to JSON
    output = Path(__file__).parent.parent / "tasks.json"
    with open(output, 'w') as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)

    print(f"Wrote: {output}")
    print("\nTo run:")
    print("  python pilot.py --cores 4 --tasks tasks.json")


if __name__ == "__main__":
    main()
