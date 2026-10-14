"""
Task management endpoints for async document processing.
"""
import logging
from fastapi import APIRouter, HTTPException
from typing import List

from models.task_schemas import (
    TaskStatusResponse,
    TaskResultResponse,
    BatchStatusRequest,
    BatchStatusResponse,
    TaskStatus,
)
from models.schemas import DocumentResponse
from services.task_queue import get_task_queue
from services.cache_manager import get_cache_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a processing task.
    
    Returns task metadata including status, progress, and estimated time remaining.
    """
    task_queue = get_task_queue()
    task_info = await task_queue.get_task(task_id)
    
    if not task_info:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    return TaskStatusResponse(
        task_id=task_info.task_id,
        filename=task_info.filename,
        status=task_info.status,
        progress=task_info.progress,
        created_at=task_info.created_at,
        started_at=task_info.started_at,
        completed_at=task_info.completed_at,
        error_message=task_info.error_message,
        estimated_time_remaining=task_info.estimated_time_remaining,
    )


@router.post("/status/batch", response_model=BatchStatusResponse)
async def get_batch_status(request: BatchStatusRequest):
    """
    Get the status of multiple tasks in a single request.
    
    Useful for checking progress of batch uploads.
    """
    task_queue = get_task_queue()
    results = []
    
    for task_id in request.task_ids:
        task_info = await task_queue.get_task(task_id)
        if task_info:
            results.append(
                TaskStatusResponse(
                    task_id=task_info.task_id,
                    filename=task_info.filename,
                    status=task_info.status,
                    progress=task_info.progress,
                    created_at=task_info.created_at,
                    started_at=task_info.started_at,
                    completed_at=task_info.completed_at,
                    error_message=task_info.error_message,
                    estimated_time_remaining=task_info.estimated_time_remaining,
                )
            )
    
    return BatchStatusResponse(tasks=results)


@router.get("/result/{task_id}", response_model=TaskResultResponse)
async def get_task_result(task_id: str):
    """
    Get the result of a completed task.
    
    Returns the extracted document data if the task completed successfully.
    """
    task_queue = get_task_queue()
    task_info = await task_queue.get_task(task_id)
    
    if not task_info:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    if task_info.status == TaskStatus.PENDING:
        raise HTTPException(
            status_code=202,
            detail=f"Task {task_id} is still pending. Check status endpoint for progress."
        )
    
    if task_info.status == TaskStatus.PROCESSING:
        raise HTTPException(
            status_code=202,
            detail=f"Task {task_id} is still processing. Check status endpoint for progress."
        )
    
    if task_info.status == TaskStatus.FAILED:
        return TaskResultResponse(
            task_id=task_info.task_id,
            filename=task_info.filename,
            status=task_info.status,
            error_message=task_info.error_message,
        )
    
    # Task completed - get result from cache
    cache_manager = get_cache_manager()
    result = cache_manager.get(task_info.file_hash)
    
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Result for task {task_id} not found in cache"
        )
    
    # Cache stores flat dict from process_document - filter out metadata fields
    metadata_keys = {
        "_metadata", "_cache_version", "task_id", "file_path", 
        "classification", "processing_summary", "json_output_file", "download_url",
        "success", "filename", "error", "message", "file_hash"
    }
    
    # Also filter out computed fields that shouldn't be in input data
    computed_fields = {"needs_review"}
    
    extracted_data = {
        k: v for k, v in result.items()
        if k not in metadata_keys and k not in computed_fields
    }
    
    # Reconstruct typed document from cached data
    from models.schemas import create_document
    
    document_type = extracted_data.get("document_type", "unknown")
    typed_document = create_document(
        document_type=document_type,
        data=extracted_data,
        request_id=task_id
    )
    
    return TaskResultResponse(
        task_id=task_info.task_id,
        filename=task_info.filename,
        status=task_info.status,
        extracted_data=typed_document,
        json_output_file=result.get("json_output_file"),
        download_url=result.get("download_url"),
    )


@router.get("/list")
async def list_tasks(status: str = None, limit: int = 100):
    """
    List all tasks, optionally filtered by status.
    
    Query parameters:
    - status: Filter by task status (pending, processing, completed, failed)
    - limit: Maximum number of tasks to return (default 100)
    """
    task_queue = get_task_queue()
    all_tasks = await task_queue.get_all_tasks()
    
    # Filter by status if provided
    if status:
        try:
            status_enum = TaskStatus(status.lower())
            all_tasks = [t for t in all_tasks if t.status == status_enum]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Must be one of: pending, processing, completed, failed"
            )
    
    # Apply limit
    all_tasks = all_tasks[:limit]
    
    return {
        "total": len(all_tasks),
        "tasks": [
            {
                "task_id": t.task_id,
                "filename": t.filename,
                "status": t.status.value,
                "progress": t.progress,
                "created_at": t.created_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in all_tasks
        ]
    }
