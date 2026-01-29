#!/usr/bin/env python3
"""
pilot.py - Lightweight pilot job scheduler for HPC

Run many small tasks within a single SLURM allocation.
No external dependencies - just Python stdlib.

Usage:
    python pilot.py --cores 8 --tasks tasks.json
    python pilot.py --cores 8 --tasks tasks.json --db state.db  # persistent
    python pilot.py --cores 8 --db state.db --resume            # resume after crash
"""

import argparse
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from queue import PriorityQueue
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class Task:
    """A computational task."""
    id: str
    command: str
    cores: int = 1
    timeout: Optional[int] = None  # seconds
    priority: int = 0              # higher = runs first
    workdir: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    tags: Dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    retries: int = 0

    def __lt__(self, other):
        return self.priority > other.priority

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Task':
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskResult:
    """Result of task execution."""
    task_id: str
    success: bool
    returncode: int
    duration: float
    stdout_file: str
    stderr_file: str

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# Task Execution (runs in worker process)
# =============================================================================

def execute_task(task_dict: dict, workdir_base: str) -> dict:
    """Execute a single task. Called in worker process."""
    task = Task.from_dict(task_dict)

    # Setup directory
    task_dir = Path(workdir_base) / task.id
    task_dir.mkdir(parents=True, exist_ok=True)
    workdir = task.workdir or str(task_dir)

    # Environment
    env = os.environ.copy()
    env.update(task.env)
    env["PILOT_TASK_ID"] = task.id
    env["PILOT_TASK_DIR"] = str(task_dir)

    stdout_file = task_dir / "stdout.txt"
    stderr_file = task_dir / "stderr.txt"

    start = time.time()

    try:
        with open(stdout_file, 'w') as out, open(stderr_file, 'w') as err:
            proc = subprocess.run(
                task.command,
                shell=True,
                cwd=workdir,
                env=env,
                stdout=out,
                stderr=err,
                timeout=task.timeout,
            )

        duration = time.time() - start

        return TaskResult(
            task_id=task.id,
            success=(proc.returncode == 0),
            returncode=proc.returncode,
            duration=duration,
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
        ).to_dict()

    except subprocess.TimeoutExpired:
        duration = time.time() - start
        with open(stderr_file, 'a') as err:
            err.write(f"\n[PILOT] Task timed out after {task.timeout}s\n")
        return TaskResult(
            task_id=task.id,
            success=False,
            returncode=-1,
            duration=duration,
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
        ).to_dict()

    except Exception as e:
        duration = time.time() - start
        with open(stderr_file, 'a') as err:
            err.write(f"\n[PILOT] Exception: {e}\n")
        return TaskResult(
            task_id=task.id,
            success=False,
            returncode=-1,
            duration=duration,
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
        ).to_dict()


# =============================================================================
# Pilot Scheduler
# =============================================================================

class Pilot:
    """
    Pilot job scheduler - manages tasks within a SLURM allocation.
    """

    def __init__(
        self,
        total_cores: int,
        workdir: str = "./pilot_runs",
        db_path: Optional[str] = None,
    ):
        self.total_cores = total_cores
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

        # Resource tracking
        self.cores_free = total_cores
        self.lock = Lock()

        # Task state
        self.pending: PriorityQueue = PriorityQueue()
        self.running: Dict[str, Task] = {}
        self.completed: Dict[str, TaskResult] = {}
        self.failed: Dict[str, TaskResult] = {}

        # Callbacks
        self.on_complete_callbacks: List[Callable] = []

        # Shutdown
        self._shutdown = False
        signal.signal(signal.SIGTERM, lambda s, f: setattr(self, '_shutdown', True))
        signal.signal(signal.SIGINT, lambda s, f: setattr(self, '_shutdown', True))

        # Logging (must be before db init)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        self.log = logging.getLogger("Pilot")

        # Persistence (after logging)
        self.db: Optional[sqlite3.Connection] = None
        if db_path:
            self._init_db(db_path)

    def _init_db(self, path: str):
        """Initialize SQLite database."""
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                task_json TEXT,
                status TEXT,
                result_json TEXT,
                created_at REAL,
                finished_at REAL
            )
        ''')
        self.db.commit()
        self.log.info(f"Database: {path}")

    # -------------------------------------------------------------------------
    # Task Management
    # -------------------------------------------------------------------------

    def add_task(self, task: Task):
        """Add a task to the queue."""
        self.pending.put(task)
        if self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO tasks (id, task_json, status, created_at) VALUES (?, ?, ?, ?)",
                (task.id, json.dumps(task.to_dict()), "pending", time.time())
            )
            self.db.commit()

    def add_tasks(self, tasks: List[Task]):
        """Add multiple tasks."""
        for t in tasks:
            self.add_task(t)
        self.log.info(f"Added {len(tasks)} tasks")

    def load_json(self, path: str) -> int:
        """Load tasks from JSON file."""
        with open(path) as f:
            data = json.load(f)
        tasks = [Task.from_dict(d) for d in data]
        self.add_tasks(tasks)
        return len(tasks)

    def resume(self) -> Tuple[int, int]:
        """Resume from database."""
        if not self.db:
            raise ValueError("No database")

        cursor = self.db.execute("SELECT id, task_json, status, result_json FROM tasks")
        pending, done = 0, 0

        for row in cursor:
            tid, task_json, status, result_json = row
            task = Task.from_dict(json.loads(task_json))

            if status in ("pending", "running"):
                self.pending.put(task)
                pending += 1
            elif status == "completed":
                self.completed[tid] = TaskResult(**json.loads(result_json))
                done += 1
            elif status == "failed":
                self.failed[tid] = TaskResult(**json.loads(result_json))

        self.log.info(f"Resumed: {pending} pending, {done} done")
        return pending, done

    def on_complete(self, callback: Callable):
        """Register callback for task completion.

        Callback signature: (task: Task, result: TaskResult, pilot: Pilot) -> Optional[List[Task]]
        """
        self.on_complete_callbacks.append(callback)

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    def _can_run(self, task: Task) -> bool:
        """Check if task can run."""
        return task.cores <= self.cores_free

    def run(self, max_workers: Optional[int] = None) -> Dict[str, Any]:
        """
        Main loop - run until all tasks complete.

        Returns summary dict.
        """
        max_workers = max_workers or self.total_cores

        self.log.info("=" * 60)
        self.log.info("PILOT STARTING")
        self.log.info(f"  Cores: {self.total_cores}")
        self.log.info(f"  Workers: {max_workers}")
        self.log.info(f"  Pending: {self.pending.qsize()}")
        self.log.info("=" * 60)

        start_time = time.time()

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {}

            while not self._shutdown:
                # Start tasks
                requeue = []
                while not self.pending.empty() and self.cores_free > 0:
                    task = self.pending.get()

                    if self._can_run(task):
                        with self.lock:
                            self.cores_free -= task.cores
                            self.running[task.id] = task

                        self.log.info(f"▶ {task.id} ({task.cores}c) [{self.cores_free}/{self.total_cores} free]")

                        future = executor.submit(
                            execute_task,
                            task.to_dict(),
                            str(self.workdir)
                        )
                        futures[future] = task

                        if self.db:
                            self.db.execute(
                                "UPDATE tasks SET status=? WHERE id=?",
                                ("running", task.id)
                            )
                            self.db.commit()
                    else:
                        requeue.append(task)

                for t in requeue:
                    self.pending.put(t)

                # Check if done
                if not futures:
                    if self.pending.empty():
                        break
                    time.sleep(0.5)
                    continue

                # Wait for completions
                try:
                    for future in as_completed(futures, timeout=1.0):
                        task = futures.pop(future)
                        result_dict = future.result()
                        result = TaskResult(**result_dict)

                        with self.lock:
                            self.cores_free += task.cores
                            del self.running[task.id]

                        # Handle result
                        if result.success:
                            self.completed[task.id] = result
                            status = "completed"
                            self.log.info(f"✓ {task.id} ({result.duration:.1f}s)")
                        else:
                            if task.retries < task.max_retries:
                                task.retries += 1
                                self.pending.put(task)
                                status = "pending"
                                self.log.warning(f"⟳ {task.id} retry {task.retries}/{task.max_retries}")
                            else:
                                self.failed[task.id] = result
                                status = "failed"
                                self.log.error(f"✗ {task.id} FAILED")

                        if self.db:
                            self.db.execute(
                                "UPDATE tasks SET status=?, result_json=?, finished_at=? WHERE id=?",
                                (status, json.dumps(result.to_dict()), time.time(), task.id)
                            )
                            self.db.commit()

                        # Callbacks (for adaptive workflows)
                        for cb in self.on_complete_callbacks:
                            try:
                                new_tasks = cb(task, result, self)
                                if new_tasks:
                                    self.add_tasks(new_tasks)
                                    self.log.info(f"  → Generated {len(new_tasks)} new tasks")
                            except Exception as e:
                                self.log.error(f"Callback error: {e}")

                        break  # Process one at a time

                except TimeoutError:
                    pass

        # Summary
        wall_time = time.time() - start_time

        self.log.info("=" * 60)
        self.log.info("PILOT FINISHED")
        self.log.info(f"  Completed: {len(self.completed)}")
        self.log.info(f"  Failed: {len(self.failed)}")
        self.log.info(f"  Wall time: {wall_time:.1f}s")
        if self.completed:
            cpu_time = sum(r.duration for r in self.completed.values())
            self.log.info(f"  CPU time: {cpu_time:.1f}s")
        self.log.info("=" * 60)

        return {
            "completed": len(self.completed),
            "failed": len(self.failed),
            "wall_time": wall_time,
        }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Pilot job scheduler")
    parser.add_argument("--cores", type=int, required=True, help="Total cores")
    parser.add_argument("--tasks", type=str, help="Tasks JSON file")
    parser.add_argument("--workdir", type=str, default="./pilot_runs")
    parser.add_argument("--db", type=str, help="SQLite database for persistence")
    parser.add_argument("--resume", action="store_true", help="Resume from database")
    parser.add_argument("--max-workers", type=int, help="Max concurrent tasks")

    args = parser.parse_args()

    if not args.tasks and not args.resume:
        parser.error("Need --tasks or --resume")

    pilot = Pilot(
        total_cores=args.cores,
        workdir=args.workdir,
        db_path=args.db,
    )

    if args.resume:
        pilot.resume()
    elif args.tasks:
        pilot.load_json(args.tasks)

    result = pilot.run(max_workers=args.max_workers)

    # Save summary
    summary_path = Path(args.workdir) / "summary.json"
    with open(summary_path, 'w') as f:
        json.dump(result, f, indent=2)

    sys.exit(1 if result["failed"] > 0 else 0)


if __name__ == "__main__":
    main()
