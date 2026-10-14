"""
Worker pool for concurrent document processing using multiprocessing.
"""
import asyncio
import logging
import multiprocessing as mp
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WorkerPool:
    """
    Manages a pool of worker processes for document processing.
    """
    
    def __init__(self, max_workers: Optional[int] = None):
        """
        Initialize worker pool.
        
        Args:
            max_workers: Number of worker processes. If None, auto-detect based on CPU cores.
        """
        if max_workers is None:
            # Auto-detect: min(cpu_count, 8)
            cpu_count = mp.cpu_count()
            max_workers = min(max(cpu_count, 2), 8)
        
        self.max_workers = max_workers
        self.executor: Optional[ProcessPoolExecutor] = None
        
        logger.info(f"Worker pool configured with {self.max_workers} workers")
    
    def start(self):
        """Start the worker pool."""
        if self.executor is not None:
            logger.warning("Worker pool already started")
            return

        project_root = str(Path(__file__).resolve().parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        self.executor = ProcessPoolExecutor(max_workers=self.max_workers)
        logger.info(f"Worker pool started with {self.max_workers} workers")
    
    def stop(self):
        """Stop the worker pool and wait for all tasks to complete."""
        if self.executor is None:
            return
        
        logger.info("Shutting down worker pool...")
        self.executor.shutdown(wait=True)
        self.executor = None
        logger.info("Worker pool shut down")
    
    async def submit(self, func, *args, **kwargs):
        """
        Submit a task to the worker pool.
        
        Args:
            func: Function to execute in worker process
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func execution
        """
        if self.executor is None:
            raise RuntimeError("Worker pool not started")
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self.executor,
            func,
            *args,
        )
        return result
    
    def get_stats(self) -> dict:
        """Get worker pool statistics."""
        return {
            "max_workers": self.max_workers,
            "active": self.executor is not None,
        }


# Global worker pool instance
_worker_pool: Optional[WorkerPool] = None


def get_worker_pool() -> WorkerPool:
    """Get the global worker pool instance."""
    global _worker_pool
    if _worker_pool is None:
        max_workers_str = os.getenv("WORKER_POOL_SIZE", "auto")
        if max_workers_str and max_workers_str.lower() != "auto":
            try:
                max_workers = int(max_workers_str)
            except ValueError:
                logger.warning(f"Invalid WORKER_POOL_SIZE: {max_workers_str}. Using auto-detect.")
                max_workers = None
        else:
            max_workers = None  # Auto-detect
        _worker_pool = WorkerPool(max_workers=max_workers)
    return _worker_pool
