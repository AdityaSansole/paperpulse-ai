import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from routes.upload import router as upload_router
from routes.tasks import router as tasks_router
from routes.batch import router as batch_router
from services.cache_manager import get_cache_manager
from services.task_queue import get_task_queue
from services.worker_pool import get_worker_pool
from services.worker import process_document_worker
from models.task_schemas import TaskStatus

# Configure logging once at application startup
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/app.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Background worker loop
async def background_worker_loop():
    """
    Background task that continuously processes pending tasks from the queue.
    Runs in the main event loop and submits work to the worker pool.
    """
    task_queue = get_task_queue()
    worker_pool = get_worker_pool()
    cache_manager = get_cache_manager()
    
    logger.info("Background worker loop started")
    
    while True:
        try:
            # Get pending tasks
            pending_tasks = await task_queue.get_pending_tasks()
            
            if not pending_tasks:
                # No pending tasks - sleep and check again
                await asyncio.sleep(1)
                continue
            
            # Process each pending task
            for task_info in pending_tasks:
                try:
                    # Mark as processing
                    await task_queue.update_task(
                        task_info.task_id,
                        status=TaskStatus.PROCESSING,
                        progress=10.0,
                    )
                    
                    # Construct file path
                    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
                    file_path = os.path.join(
                        upload_dir,
                        f"{task_info.file_hash}_{task_info.filename}"
                    )
                    
                    if not os.path.exists(file_path):
                        raise FileNotFoundError(f"File not found: {file_path}")
                    
                    # Submit to worker pool
                    logger.info(f"Submitting task {task_info.task_id} to worker pool")
                    result = await worker_pool.submit(
                        process_document_worker,
                        file_path,
                        task_info.filename,
                        task_info.file_hash,
                    )

                    if result.get("error"):
                        await task_queue.update_task(
                            task_info.task_id,
                            status=TaskStatus.FAILED,
                            error_message=result["error"],
                        )
                        logger.warning(f"Task {task_info.task_id} failed with extraction error: {result['error']}")
                        continue

                    # Store result in cache
                    cache_manager.put(task_info.file_hash, result)

                    # Mark as completed
                    await task_queue.update_task(
                        task_info.task_id,
                        status=TaskStatus.COMPLETED,
                        progress=100.0,
                    )

                    logger.info(f"Task {task_info.task_id} completed successfully")
                    
                except Exception as exc:
                    logger.error(f"Task {task_info.task_id} failed: {exc}", exc_info=True)
                    
                    # Mark as failed
                    await task_queue.update_task(
                        task_info.task_id,
                        status=TaskStatus.FAILED,
                        error_message=str(exc),
                    )
            
            # Small delay before next iteration
            await asyncio.sleep(0.5)
            
        except asyncio.CancelledError:
            logger.info("Background worker loop cancelled")
            break
        except Exception as exc:
            logger.error(f"Background worker loop error: {exc}", exc_info=True)
            await asyncio.sleep(5)  # Back off on error


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle: startup and shutdown.
    """
    # Startup
    logger.info("Application starting up...")
    
    # Log configuration values at system startup
    logger.info("=" * 80)
    logger.info("[CONFIGURATION] System Configuration Values:")
    logger.info("=" * 80)

    logger.info(f"[CONFIG] AI Provider: {os.getenv('AI_PROVIDER', 'gemini')}")
    logger.info(f"[CONFIG] OCR Engine: {os.getenv('OCR_ENGINE', 'tesseract')}")
    logger.info(f"[CONFIG] OCR Language: {os.getenv('OCR_LANG', 'eng+hin')}")
    logger.info(f"[CONFIG] OCR Preprocess: {os.getenv('OCR_PREPROCESS', 'adaptive')}")
    # System paths
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    output_dir = os.getenv("OUTPUT_DIR", "outputs")
    cache_dir = os.getenv("CACHE_DIR", "cache")
    logger.info(f"[CONFIG] Upload Directory: {upload_dir}")
    logger.info(f"[CONFIG] Output Directory: {output_dir}")
    logger.info(f"[CONFIG] Cache Directory: {cache_dir}")
    
    logger.info("=" * 80)
    
    # Initialize cache manager
    cache_manager = get_cache_manager()
    await cache_manager.start()
    logger.info("Cache manager started")
    
    # Initialize worker pool
    worker_pool = get_worker_pool()
    worker_pool.start()
    logger.info(f"Worker pool started with {worker_pool.max_workers} workers")
    
    # Start background worker loop
    worker_task = asyncio.create_task(background_worker_loop())
    logger.info("Background worker loop started")
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Application shutting down...")
    
    # Cancel background worker loop
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    
    # Stop worker pool
    worker_pool.stop()
    logger.info("Worker pool stopped")
    
    # Stop cache manager
    await cache_manager.stop()
    logger.info("Cache manager stopped")
    
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Document Intelligence System",
    version="3.0.0",
    description="AI-powered document processing with concurrent processing, caching, and hybrid extraction.",
    lifespan=lifespan,
    debug=os.getenv("APP_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"},
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serves React build static files (JS, CSS, images) from Vite
if os.path.exists("web/dist"):
    app.mount("/assets", StaticFiles(directory="web/dist/assets"), name="assets")

# Include routers
app.include_router(upload_router, prefix="/api")
app.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
app.include_router(batch_router, prefix="/api", tags=["batch"])


@app.get("/")
def home():
    if os.path.exists("web/dist/index.html"):
        response = FileResponse("web/dist/index.html")
    else:
        # Fallback if front-end hasn't been built yet
        return {"message": "Document Intelligence Backend is healthy. Please build frontend assets with 'npm run build' inside web/."}
    
    # Disable caching for development
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# NOTE: /health and /metrics MUST be registered before /{catchall:path}.
# FastAPI matches routes in registration order; a catch-all registered first
# will intercept every request, including these named endpoints.
@app.get("/health")
async def health():
    """
    Health check endpoint with component status.
    """
    cache_manager = get_cache_manager()
    task_queue = get_task_queue()
    worker_pool = get_worker_pool()
    
    cache_stats = cache_manager.get_stats()
    queue_stats = task_queue.get_stats()
    worker_stats = worker_pool.get_stats()
    
    return {
        "status": "healthy",
        "version": "3.0.0",
        "components": {
            "cache": {
                "status": "healthy",
                "size": cache_stats["size"],
                "hit_rate": cache_stats["hit_rate_percent"],
            },
            "queue": {
                "status": "healthy",
                "pending": queue_stats["pending"],
                "processing": queue_stats["processing"],
            },
            "workers": {
                "status": "healthy" if worker_stats["active"] else "stopped",
                "count": worker_stats["max_workers"],
            },
        },
    }


@app.get("/metrics")
async def metrics():
    """
    Performance metrics endpoint.
    """
    cache_manager = get_cache_manager()
    task_queue = get_task_queue()
    worker_pool = get_worker_pool()
    
    return {
        "cache": cache_manager.get_stats(),
        "queue": task_queue.get_stats(),
        "workers": worker_pool.get_stats(),
    }


@app.get("/{catchall:path}")
def fallback(catchall: str):
    """
    Catch-all route to serve the SPA React application index.html for any sub-routes
    (like /batch, /history, /settings) so page reloads do not trigger 404s.
    Must remain LAST so it does not shadow named endpoints above.
    """
    if os.path.exists("web/dist/index.html"):
        return FileResponse("web/dist/index.html")
    return {"message": "Frontend assets not found. Please build the frontend."}
