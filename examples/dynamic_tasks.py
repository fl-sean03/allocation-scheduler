#!/usr/bin/env python3
"""
Dynamic Task Generation Example

Demonstrates adding tasks based on results using callbacks.
This is useful for adaptive workflows, iterative refinement, etc.

Usage:
    python examples/dynamic_tasks.py

This example runs the scheduler directly (no separate tasks.json step).
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from pilot import Pilot, Task, TaskResult


# Track state across callbacks
completed_values = []
MAX_TASKS = 20


def create_task(value: float, iteration: int = 0) -> Task:
    """Create a task that outputs a computed value."""
    task_id = f"iter{iteration}_val{value:.2f}".replace(".", "p")

    command = f"""
echo "Computing for value={value}"

# Simulate computation (replace with real work)
sleep 1

# Output a "result" based on input
# Peak near value=5.0, with some noise
result=$(python3 -c "
import math
import random
x = {value}
y = math.exp(-((x - 5) ** 2) / 2)  # Gaussian peak at 5
noise = random.uniform(-0.1, 0.1)
print(f'{{y + noise:.4f}}')
")

echo "RESULT: $result"
"""

    return Task(
        id=task_id,
        command=command,
        cores=1,
        timeout=60,
        tags={"value": value, "iteration": iteration},
    )


def parse_result(result: TaskResult) -> Optional[float]:
    """Extract result from task output."""
    try:
        stdout = Path(result.stdout_file).read_text()
        for line in stdout.split('\n'):
            if line.startswith('RESULT:'):
                return float(line.split(':')[1].strip())
    except Exception:
        pass
    return None


def on_task_complete(task: Task, result: TaskResult, pilot: Pilot) -> Optional[List[Task]]:
    """
    Adaptive callback - explore near high-value results.

    If we find an interesting region, sample more densely around it.
    """
    if not result.success:
        return None

    value = task.tags.get("value")
    iteration = task.tags.get("iteration", 0)
    output = parse_result(result)

    if output is None:
        return None

    completed_values.append({"value": value, "output": output})
    print(f"  [Callback] value={value:.2f} → output={output:.4f}")

    # Check limits
    total = len(pilot.completed) + len(pilot.failed) + pilot.pending.qsize()
    if total >= MAX_TASKS:
        print(f"  [Callback] Reached max tasks ({MAX_TASKS})")
        return None

    # Adaptive logic: if output is high, explore nearby
    if output > 0.5 and iteration < 3:
        new_tasks = []
        for delta in [-0.5, 0.5]:
            new_value = value + delta
            if 0 <= new_value <= 10:
                # Check if already explored
                if not any(abs(c["value"] - new_value) < 0.1 for c in completed_values):
                    new_tasks.append(create_task(new_value, iteration + 1))
                    print(f"  [Callback] → Adding task at value={new_value:.2f}")

        return new_tasks if new_tasks else None

    return None


def main():
    print("Dynamic Task Generation Example")
    print("=" * 50)
    print("Initial coarse sweep, then refine near high values")
    print()

    # Create initial tasks (coarse grid)
    initial_tasks = [create_task(v, iteration=0) for v in range(0, 11, 2)]
    print(f"Initial tasks: {len(initial_tasks)} (values: 0, 2, 4, 6, 8, 10)")

    # Setup pilot
    pilot = Pilot(
        total_cores=4,
        workdir="./dynamic_runs",
        db_path="./dynamic_state.db",
    )

    # Register callback
    pilot.on_complete(on_task_complete)

    # Add initial tasks
    pilot.add_tasks(initial_tasks)

    # Run
    result = pilot.run(max_workers=4)

    # Summary
    print("\n" + "=" * 50)
    print("Final Results")
    print("=" * 50)

    sorted_results = sorted(completed_values, key=lambda x: x["output"], reverse=True)
    print("\nTop 5 values (sorted by output):")
    for r in sorted_results[:5]:
        print(f"  value={r['value']:.2f} → output={r['output']:.4f}")

    print(f"\nTotal tasks run: {result['completed'] + result['failed']}")
    print(f"Peak found near: {sorted_results[0]['value']:.2f}")


if __name__ == "__main__":
    main()
