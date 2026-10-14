"""
In-process task queue with file-based persistence.
Manages document processing tasks and their lifecycle.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

from models.task_schemas import TaskStatus, TaskInfo

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Simple in-process task queue with file persistence.
    Thread-safe for concurrent access.
    """
    
    def __init__(self, queue_dir: str = "queue"):
        """
        Initialize task queue.
        
        Args:
            queue_dir: Directory for task state persistence
        """
        self.queue_dir = Path(queue_dir)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory task storage: {task_id: TaskInfo}
        self._tasks: Dict[str, TaskInfo] = {}
        
        # Lock for thread-safe access
        self._lock = asyncio.Lock()
        
        # Load existing tasks from disk
        self._load_from_disk()
    
    def _load_from_disk(self):
        """Load task state from disk on startup."""
        task_files = list(self.queue_dir.glob("*.json"))
        
        if not task_files:
            logger.info("No existing tasks found. Starting fresh.")
            return
        
        loaded = 0
        for task_file in task_files:
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    task_data = json.load(f)
                
                task_info = TaskInfo(**task_data)
                self._tasks[task_info.task_id] = task_info
                loaded += 1
                
            except Exception as exc:
                logger.error(f"Failed to load task from {task_file}: {exc}")
        
        logger.info(f"Loaded {loaded} tasks from disk.")
    
    def _save_task(self, task_info: TaskInfo):
        """Save task state to disk."""
        try:
            task_file = self.queue_dir / f"{task_info.task_id}.json"
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task_info.model_dump(mode="json"), f, indent=2, default=str)
        except Exception as exc:
            logger.error(f"Failed to save task {task_info.task_id}: {exc}")
    
    def _delete_task_file(self, task_id: str):
        """Delete task file from disk."""
        try:
            task_file = self.queue_dir / f"{task_id}.json"
            if task_file.exists():
                task_file.unlink()
        except Exception as exc:
            logger.warning(f"Failed to delete task file {task_id}: {exc}")
    
    async def create_task(
        self,
        filename: str,
        file_hash: str,
    ) -> str:
        """
        Create a new task and return its ID.
        
        Args:
            filename: Original filename
            file_hash: SHA256 hash of the file
            
        Returns:
            task_id: Unique task identifier
        """
        task_id = str(uuid.uuid4())
        
        task_info = TaskInfo(
            task_id=task_id,
            filename=filename,
            file_hash=file_hash,
            status=TaskStatus.PENDING,
            progress=0.0,
            created_at=datetime.now(),
        )
        
        async with self._lock:
            self._tasks[task_id] = task_info
            self._save_task(task_info)
        
        logger.info(f"Created task {task_id} for file {filename}")
        return task_id
    
    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task info by ID."""
        async with self._lock:
            return self._tasks.get(task_id)
    
    async def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
        estimated_time_remaining: Optional[float] = None,
    ):
        """Update task status and metadata."""
        async with self._lock:
            task_info = self._tasks.get(task_id)
            if not task_info:
                logger.warning(f"Task {task_id} not found for update")
                return
            
            if status:
                task_info.status = status
                
                if status == TaskStatus.PROCESSING and not task_info.started_at:
                    task_info.started_at = datetime.now()
                
                if status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                    task_info.completed_at = datetime.now()
            
            if progress is not None:
                task_info.progress = progress
            
            if error_message is not None:
                task_info.error_message = error_message
            
            if estimated_time_remaining is not None:
                task_info.estimated_time_remaining = estimated_time_remaining
            
            self._save_task(task_info)
        
        logger.debug(f"Updated task {task_id}: status={status}, progress={progress}")
    
    async def get_pending_tasks(self) -> List[TaskInfo]:
        """Get all tasks with PENDING status."""
        async with self._lock:
            return [
                task for task in self._tasks.values()
                if task.status == TaskStatus.PENDING
            ]
    
    async def get_all_tasks(self) -> List[TaskInfo]:
        """Get all tasks."""
        async with self._lock:
            return list(self._tasks.values())
    
    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """
        Remove completed/failed tasks older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours for completed tasks
        """
        now = datetime.now()
        to_delete = []
        
        async with self._lock:
            for task_id, task_info in self._tasks.items():
                if task_info.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                    if task_info.completed_at:
                        age_hours = (now - task_info.completed_at).total_seconds() / 3600
                        if age_hours > max_age_hours:
                            to_delete.append(task_id)
            
            for task_id in to_delete:
                del self._tasks[task_id]
                self._delete_task_file(task_id)
        
        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} old tasks")
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        pending = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PENDING)
        processing = sum(1 for t in self._tasks.values() if t.status == TaskStatus.PROCESSING)
        completed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks.values() if t.status == TaskStatus.FAILED)
        
        return {
            "total_tasks": len(self._tasks),
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
        }


# Global task queue instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """Get the global task queue instance."""
    global _task_queue
    if _task_queue is None:
        queue_dir = os.getenv("TASK_QUEUE_DIR", "queue")
        _task_queue = TaskQueue(queue_dir=queue_dir)
    return _task_queue
