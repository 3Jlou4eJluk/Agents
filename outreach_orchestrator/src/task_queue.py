"""
Task Queue with SQLite persistence for resume capability.
"""

import aiosqlite
import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any


class TaskQueue:
    """
    SQLite-based task queue for managing lead processing.
    Provides persistence and resume capability.
    """

    def __init__(self, db_path: str = "data/progress.db"):
        """
        Initialize task queue.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self, clean: bool = False):
        """
        Create database schema if it doesn't exist.

        Args:
            clean: If True, drop all existing data and start fresh
        """
        async with aiosqlite.connect(self.db_path) as db:
            if clean:
                # Drop existing table to start fresh
                await db.execute("DROP TABLE IF EXISTS tasks")
                await db.commit()

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    linkedin_url TEXT,
                    lead_data TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    stage1_result TEXT,
                    stage2_result TEXT,
                    error TEXT,
                    worker_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_email ON tasks(email)
            """)
            await db.commit()

    async def clear_all(self):
        """Clear all tasks from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM tasks")
            await db.commit()

    async def load_from_csv(self, csv_path: str) -> int:
        """
        Load leads from CSV file into task queue.
        Skips leads without email addresses.

        Args:
            csv_path: Path to CSV file with leads

        Returns:
            Number of new tasks added
        """
        added_count = 0
        skipped_no_email = 0
        skipped_exists = 0

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            async with aiosqlite.connect(self.db_path) as db:
                for row in reader:
                    email = row.get('Email') or row.get('email')
                    linkedin_url = row.get('linkedIn') or row.get('linkedin_url') or row.get('LinkedIn')

                    # Skip if no email
                    if not email or email.strip() == '':
                        skipped_no_email += 1
                        continue

                    # Clean email
                    email = email.strip()

                    # Check if task already exists
                    cursor = await db.execute(
                        "SELECT id FROM tasks WHERE email = ?",
                        (email,)
                    )
                    exists = await cursor.fetchone()

                    if exists:
                        skipped_exists += 1
                        continue

                    # Add new task
                    await db.execute("""
                        INSERT INTO tasks (email, linkedin_url, lead_data, status)
                        VALUES (?, ?, ?, 'pending')
                    """, (
                        email,
                        linkedin_url,
                        json.dumps(row)
                    ))
                    added_count += 1

                await db.commit()

        # Print summary
        if skipped_no_email > 0:
            print(f"  ⊘ Skipped {skipped_no_email} leads (no email)")
        if skipped_exists > 0:
            print(f"  ⊘ Skipped {skipped_exists} leads (already in queue)")

        return added_count

    async def get_next_task(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Get next pending task and mark as processing.

        Args:
            worker_id: Unique identifier for the worker

        Returns:
            Task dictionary or None if no tasks available
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Atomically get and update next pending task
            await db.execute("BEGIN IMMEDIATE")

            try:
                cursor = await db.execute("""
                    SELECT id, email, linkedin_url, lead_data
                    FROM tasks
                    WHERE status = 'pending'
                    ORDER BY id
                    LIMIT 1
                """)
                row = await cursor.fetchone()

                if not row:
                    await db.rollback()
                    return None

                task_id, email, linkedin_url, lead_data = row

                # Mark as processing
                await db.execute("""
                    UPDATE tasks
                    SET status = 'processing',
                        worker_id = ?,
                        started_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (worker_id, task_id))

                await db.commit()

                return {
                    'id': task_id,
                    'email': email,
                    'linkedin_url': linkedin_url,
                    'lead_data': json.loads(lead_data)
                }

            except Exception as e:
                await db.rollback()
                raise e

    async def update_task(
        self,
        task_id: int,
        status: str,
        stage1_result: Optional[Dict] = None,
        stage2_result: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """
        Update task with results.

        Args:
            task_id: Task ID
            status: New status (completed/failed)
            stage1_result: Stage 1 classification result
            stage2_result: Stage 2 letter generation result
            error: Error message if failed
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tasks
                SET status = ?,
                    stage1_result = ?,
                    stage2_result = ?,
                    error = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                status,
                json.dumps(stage1_result) if stage1_result else None,
                json.dumps(stage2_result) if stage2_result else None,
                error,
                task_id
            ))
            await db.commit()

    async def get_stats(self) -> Dict[str, int]:
        """Get current task statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT status, COUNT(*) as count
                FROM tasks
                GROUP BY status
            """)
            rows = await cursor.fetchall()

            stats = {
                'total': 0,
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0
            }

            for status, count in rows:
                stats[status] = count
                stats['total'] += count

            return stats

    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all processed tasks (completed or failed) for export. Excludes pending/processing."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT
                    email,
                    linkedin_url,
                    lead_data,
                    status,
                    stage1_result,
                    stage2_result,
                    error,
                    completed_at
                FROM tasks
                WHERE status IN ('completed', 'failed')
                ORDER BY
                    CASE status
                        WHEN 'completed' THEN 1
                        WHEN 'failed' THEN 2
                    END,
                    id
            """)
            rows = await cursor.fetchall()

            tasks = []
            for row in rows:
                email, linkedin_url, lead_data, status, stage1, stage2, error, completed_at = row

                tasks.append({
                    'email': email,
                    'linkedin_url': linkedin_url,
                    'lead_data': json.loads(lead_data) if lead_data else {},
                    'status': status,
                    'stage1_result': json.loads(stage1) if stage1 else None,
                    'stage2_result': json.loads(stage2) if stage2 else None,
                    'error': error,
                    'completed_at': completed_at
                })

            return tasks

    async def reset_processing_tasks(self):
        """
        Reset tasks stuck in 'processing' state.
        Useful when restarting after a crash.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE tasks
                SET status = 'pending',
                    worker_id = NULL,
                    started_at = NULL
                WHERE status = 'processing'
            """)
            await db.commit()
            return cursor.rowcount
