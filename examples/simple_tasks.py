#!/usr/bin/env python3
"""
Simple Tasks Example

Demonstrates basic task generation with no external dependencies.
Tasks just sleep and print - useful for testing the scheduler.

Usage:
    python examples/simple_tasks.py
    python pilot.py --cores 4 --tasks tasks.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pilot import Task


def generate_tasks(count: int = 10, cores_per_task: int = 1) -> list:
    """Generate simple test tasks."""
    tasks = []

    for i in range(count):
        # Simple task: sleep random time, print some output
        task = Task(
            id=f"task_{i:03d}",
            command=f"""
echo "Task {i} starting"
echo "Hostname: $(hostname)"
echo "PID: $$"
sleep $(( (RANDOM % 3) + 1 ))
echo "Task {i} completed"
""",
            cores=cores_per_task,
            timeout=60,
            priority=i,  # Higher number = higher priority
            tags={"index": i},
        )
        tasks.append(task)

    return tasks


def main():
    print("Simple Tasks Generator")
    print("=" * 40)

    tasks = generate_tasks(count=10, cores_per_task=1)
    print(f"Generated {len(tasks)} tasks")

    # Write to JSON
    output = Path(__file__).parent.parent / "tasks.json"
    with open(output, 'w') as f:
        json.dump([t.to_dict() for t in tasks], f, indent=2)

    print(f"Wrote: {output}")
    print("\nTo run:")
    print("  python pilot.py --cores 4 --tasks tasks.json")


if __name__ == "__main__":
    main()
