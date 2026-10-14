"""
Worker process function for document processing.
Runs in separate process via ProcessPoolExecutor.
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Configure logging for worker process
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [Worker] - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _sanitize_stem(filename: str) -> str:
    stem = Path(filename).stem
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return safe[:80] or "document"


def _write_output_json(filename: str, file_hash: str, extracted_data: dict) -> tuple[str, str]:
    output_dir = Path(os.getenv("OUTPUT_DIR", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f"{_sanitize_stem(filename)}_{timestamp}_{file_hash}.json"
    output_path = output_dir / json_filename

    payload = {
        "success": True,
        "filename": filename,
        "extracted_data": extracted_data,
        "message": "Document processed successfully.",
        "json_output_file": json_filename,
        "download_url": f"/api/download/{json_filename}",
        "file_hash": file_hash,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return json_filename, f"/api/download/{json_filename}"


def process_document_worker(file_path: str, filename: str, file_hash: str) -> dict:
    """
    Worker function that processes a document in a separate process.
    
    This function is executed by ProcessPoolExecutor workers.
    It must be picklable (top-level function, no closures).
    
    Args:
        file_path: Path to the uploaded file
        filename: Original filename
        file_hash: SHA256 hash of the file
        
    Returns:
        dict: Serializable result dictionary containing DocumentResponse data
    """
    try:
        # Import here to avoid issues with multiprocessing
        from services.document_service import process_document
        
        logger.info(f"Worker processing: {filename}")
        
        # Process the document (async function - need to run in event loop)
        result = asyncio.run(process_document(file_path, filename))
        
        # Convert to dict for serialization
        result_dict = result if isinstance(result, dict) else result.model_dump(mode="json")

        if result_dict.get("processing_status") == "failed":
            summary = result_dict.get("summary") or "Document extraction failed"
            return {
                "error": summary,
                "success": False,
                "filename": filename,
                "file_hash": file_hash,
                "extracted_data": {
                    "document_type": "unknown",
                    "detected_document_type": result_dict.get("document_type", "unknown"),
                    "summary": summary,
                    "processing_status": "failed",
                    "review_flags": [],
                    "review_notes": [summary],
                    "needs_review": False,
                    "raw_text": None,
                    "people": [],
                },
            }

        if not result_dict.get("error"):
            json_output_file, download_url = _write_output_json(filename, file_hash, result_dict)
            result_dict["json_output_file"] = json_output_file
            result_dict["download_url"] = download_url
        
        logger.info(f"Worker completed: {filename}")
        return result_dict
        
    except Exception as exc:
        logger.error(f"Worker error processing {filename}: {exc}", exc_info=True)
        error_message = f"Error: {str(exc)}"
        fallback = {
            "document_type": "unknown",
            "detected_document_type": "unknown",
            "summary": error_message,
            "processing_status": "failed",
            "review_flags": [],
            "review_notes": [error_message],
            "needs_review": False,
            "raw_text": None,
            "people": [],
        }
        return {
            "success": False,
            "filename": filename,
            "error": error_message,
            "message": error_message,
            "file_hash": file_hash,
            "extracted_data": fallback,
        }
    
    finally:
        # Always clean up uploaded file, even if processing fails
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up file: {file_path}")
        except Exception as exc:
            logger.warning(f"Failed to clean up file {file_path}: {exc}")
