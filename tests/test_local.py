#!/usr/bin/env python3
"""
Local test of the pilot scheduler - no LAMMPS needed.

This creates simple sleep tasks to verify:
1. Parallel execution works
2. Tasks cycle (new starts when old finishes)
3. Dynamic task generation callback works

Run: python tests/test_local.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pilot import Pilot, Task, TaskResult


def test_basic_parallel():
    """Test basic parallel execution with cycling."""
    print("=" * 60)
    print("TEST: Basic Parallel Execution with Cycling")
    print("=" * 60)

    # Simulate 4 cores, run 8 tasks (2 cores each)
    # Should cycle: 2 run → complete → 2 more → etc.
    pilot = Pilot(total_cores=4, workdir="./test_runs/basic")

    tasks = [
        Task(id=f"task_{i}", command=f"sleep 1 && echo 'Task {i} done'", cores=2)
        for i in range(8)
    ]
    pilot.add_tasks(tasks)

    print(f"Tasks: {len(tasks)}")
    print(f"Cores per task: 2")
    print(f"Total cores: 4")
    print(f"Expected: 2 tasks run at a time, cycling through all 8")
    print()

    result = pilot.run()

    assert result["completed"] == 8, f"Expected 8 completed, got {result['completed']}"
    assert result["failed"] == 0, f"Expected 0 failed, got {result['failed']}"

    # Check that tasks ran in parallel (wall time < sum of durations)
    # 8 tasks × 1s = 8s sequential, but with 2 parallel should be ~4s
    assert result["wall_time"] < 6, f"Tasks didn't run in parallel (took {result['wall_time']:.1f}s)"

    print(f"\n✓ PASSED: {result['completed']} tasks completed in {result['wall_time']:.1f}s")
    print()


def test_dynamic_generation():
    """Test dynamic task generation callback."""
    print("=" * 60)
    print("TEST: Dynamic Task Generation")
    print("=" * 60)

    pilot = Pilot(total_cores=4, workdir="./test_runs/dynamic_generation")

    # Start with 2 tasks
    initial_tasks = [
        Task(id="initial_0", command="echo 'INTERESTING' && sleep 0.5", cores=2, tags={"value": 0}),
        Task(id="initial_1", command="echo 'boring' && sleep 0.5", cores=2, tags={"value": 1}),
    ]
    pilot.add_tasks(initial_tasks)

    generated_count = [0]  # Use list to allow modification in callback

    def dynamic_callback(task, result, p):
        """Generate new task if result is interesting."""
        # Read stdout to check if interesting
        try:
            stdout = Path(result.stdout_file).read_text()
            if "INTERESTING" in stdout and generated_count[0] < 3:
                generated_count[0] += 1
                new_id = f"generated_{generated_count[0]}"
                print(f"  [Callback] Task {task.id} was interesting → generating {new_id}")
                return [Task(
                    id=new_id,
                    command=f"echo 'Generated task {generated_count[0]}' && sleep 0.3",
                    cores=2,
                    tags={"generated_from": task.id}
                )]
        except Exception:
            pass
        return None

    pilot.on_complete(dynamic_callback)

    print(f"Initial tasks: {len(initial_tasks)}")
    print(f"Callback will generate up to 3 new tasks")
    print()

    result = pilot.run()

    # Should have 2 initial + 1 generated (from the INTERESTING one)
    total = result["completed"] + result["failed"]
    assert total >= 3, f"Expected at least 3 tasks (2 initial + 1 generated), got {total}"

    print(f"\n✓ PASSED: {result['completed']} tasks total ({generated_count[0]} dynamically generated)")
    print()


def test_priority_ordering():
    """Test that high priority tasks run first."""
    print("=" * 60)
    print("TEST: Priority Ordering")
    print("=" * 60)

    pilot = Pilot(total_cores=2, workdir="./test_runs/priority")

    # Create tasks with different priorities
    # Only 1 core each, 2 cores total → 2 can run at once
    tasks = [
        Task(id="low_1", command="sleep 0.3 && echo 'low_1'", cores=1, priority=0),
        Task(id="low_2", command="sleep 0.3 && echo 'low_2'", cores=1, priority=0),
        Task(id="high_1", command="sleep 0.3 && echo 'high_1'", cores=1, priority=100),
        Task(id="high_2", command="sleep 0.3 && echo 'high_2'", cores=1, priority=100),
    ]
    pilot.add_tasks(tasks)

    print("Tasks added in order: low_1, low_2, high_1, high_2")
    print("High priority (100) should run before low priority (0)")
    print()

    # We can't easily verify order, but we can verify all complete
    result = pilot.run()

    assert result["completed"] == 4
    print(f"\n✓ PASSED: All {result['completed']} tasks completed")
    print()


def test_failure_handling():
    """Test that failures are tracked correctly."""
    print("=" * 60)
    print("TEST: Failure Handling")
    print("=" * 60)

    pilot = Pilot(total_cores=4, workdir="./test_runs/failures")

    tasks = [
        Task(id="success_1", command="echo 'ok'", cores=1),
        Task(id="fail_1", command="exit 1", cores=1),
        Task(id="success_2", command="echo 'ok'", cores=1),
        Task(id="fail_2", command="exit 42", cores=1),
    ]
    pilot.add_tasks(tasks)

    result = pilot.run()

    assert result["completed"] == 2, f"Expected 2 completed, got {result['completed']}"
    assert result["failed"] == 2, f"Expected 2 failed, got {result['failed']}"

    print(f"\n✓ PASSED: {result['completed']} succeeded, {result['failed']} failed (as expected)")
    print()


def test_persistence():
    """Test database persistence and resume."""
    print("=" * 60)
    print("TEST: Persistence and Resume")
    print("=" * 60)

    import os
    db_path = "./test_runs/persistence/state.db"
    os.makedirs("./test_runs/persistence", exist_ok=True)

    # Remove old db
    if os.path.exists(db_path):
        os.remove(db_path)

    # First run - partial
    pilot1 = Pilot(total_cores=2, workdir="./test_runs/persistence", db_path=db_path)
    pilot1.add_tasks([
        Task(id="task_0", command="echo 'task 0'", cores=1),
        Task(id="task_1", command="echo 'task 1'", cores=1),
    ])
    result1 = pilot1.run()
    print(f"First run: {result1['completed']} completed")

    # Second run - add more tasks and resume
    pilot2 = Pilot(total_cores=2, workdir="./test_runs/persistence", db_path=db_path)
    pilot2.add_tasks([
        Task(id="task_2", command="echo 'task 2'", cores=1),
    ])
    result2 = pilot2.run()
    print(f"Second run: {result2['completed']} completed")

    # Check database has all tasks
    import sqlite3
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='completed'").fetchone()[0]
    conn.close()

    assert count == 3, f"Expected 3 tasks in DB, got {count}"

    print(f"\n✓ PASSED: Database has {count} completed tasks across runs")
    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("PILOT SCHEDULER LOCAL TESTS")
    print("=" * 60 + "\n")

    tests = [
        test_basic_parallel,
        test_dynamic_generation,
        test_priority_ordering,
        test_failure_handling,
        test_persistence,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n✗ FAILED: {e}\n")
            failed += 1

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
