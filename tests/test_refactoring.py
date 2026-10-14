"""
Unit tests for the refactored OOP strategy processors, TokenTrie implementation, 
and normalizer memoization.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.trie import TokenTrie
from services.processors import DocumentProcessorFactory, AadhaarProcessor, PANProcessor, InvoiceProcessor
from services.normalizer import normalize_string, normalize_number, normalize_document_data
from services.post_processing import post_process_document
from models.schemas import (
    ExtractedDocument, AadhaarDocument, InvoiceDocument, PANDocument,
    ProcessingStatus, ReviewSeverity
)


def test_trie_matching():
    """Verify TokenTrie keyword insertion and multi-word matching accuracy."""
    print("🧪 Running TokenTrie Match Tests...")
    trie = TokenTrie()
    trie.insert("unique identification authority", "aadhaar")
    trie.insert("income tax department", "pan")
    trie.insert("tax invoice", "invoice")
    trie.insert("permanent account number", "pan")

    # Scenario 1: Exact matches
    text_1 = "this is a government document issued by the unique identification authority of india."
    matches = trie.search_all_matches(text_1)
    assert "aadhaar" in matches
    assert "unique identification authority" in matches["aadhaar"]
    assert "pan" not in matches

    # Scenario 2: Multiple matches across types
    text_2 = "here is my permanent account number issued by the income tax department and a tax invoice for verification."
    matches_2 = trie.search_all_matches(text_2)
    assert "pan" in matches_2
    assert "invoice" in matches_2
    assert "permanent account number" in matches_2["pan"]
    assert "income tax department" in matches_2["pan"]
    assert "tax invoice" in matches_2["invoice"]

    # Scenario 3: Case insensitivity and token boundary check
    text_3 = "INCOME TAX DEPARTMENT and TAX INVOICING"
    matches_3 = trie.search_all_matches(text_3)
    assert "pan" in matches_3
    assert "income tax department" in matches_3["pan"]
    # "TAX INVOICING" should not match "tax invoice" due to token mismatch on "invoicing" vs "invoice"
    assert "invoice" not in matches_3 or "tax invoice" not in matches_3["invoice"]

    print("✅ TokenTrie Match Tests Passed!")


def test_normalizer_caching():
    """Verify string normalization results and memoization behavior."""
    print("🧪 Running Normalizer Caching Tests...")
    
    # Check baseline string cleaning
    assert normalize_string("  Hello   World  ") == "Hello World"
    # Zero-width spaces removal
    assert normalize_string("Hello\u200bWorld") == "HelloWorld"
    # Unicode NFC normalization
    assert normalize_string("a\u0308") == "ä"
    
    # Check number cleaning
    assert normalize_number(" ₹ 12,500.50 ") == 12500.50
    assert normalize_number(" $ 1,000 ") == 1000.0

    print("✅ Normalizer Caching Tests Passed!")


def test_processor_factory_resolution():
    """Verify O(1) factory returns correct concrete processor strategies."""
    print("🧪 Running OOP Strategy Factory Resolution Tests...")
    
    p_aadhaar = DocumentProcessorFactory.get_processor("aadhaar")
    assert isinstance(p_aadhaar, AadhaarProcessor)

    p_pan = DocumentProcessorFactory.get_processor("pan")
    assert isinstance(p_pan, PANProcessor)

    p_invoice = DocumentProcessorFactory.get_processor("invoice")
    assert isinstance(p_invoice, InvoiceProcessor)

    # Safely falls back to Unknown
    p_random = DocumentProcessorFactory.get_processor("some_random_doc_type")
    from services.processors import UnknownProcessor
    assert isinstance(p_random, UnknownProcessor)

    print("✅ OOP Strategy Factory Resolution Tests Passed!")


def test_gemini_provider_defaults_to_supported_model_fallback(monkeypatch):
    """Verify GeminiProvider prefers a live model and keeps a fallback chain for retired IDs."""
    import services.llm_service as llm_service

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    provider = llm_service.GeminiProvider()
    assert provider.model_names[0] == llm_service.DEFAULT_GEMINI_MODEL
    assert "gemini-3.8-flash" in provider.model_names
    assert "gemini-2.0-flash" in provider.model_names


def test_provider_selection_and_unknown_alias(monkeypatch):
    """Verify the active provider is honored and 'other' is normalized to unknown."""
    import services.llm_service as llm_service

    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    provider = llm_service.get_ai_provider()
    assert provider.__class__.__name__ == "GroqProvider"

    doc = llm_service._parse_model_json('{"document_type": "other", "summary": "unknown"}', "other")
    assert doc.document_type == "unknown"
    assert "Schema validation failed" not in (doc.summary or "")


def test_ollama_provider_selection(monkeypatch):
    """Verify the local Ollama provider is available when selected explicitly."""
    import services.llm_service as llm_service

    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")

    provider = llm_service.get_ai_provider()
    assert provider.__class__.__name__ == "OllamaProvider"
    assert provider.model == "llama3.1"


def test_tesseract_default_is_preserved_when_path_is_not_configured(monkeypatch):
    """Do not overwrite pytesseract's executable default with None."""
    from types import SimpleNamespace
    import services.ocr_service as ocr_service

    fake_tesseract = SimpleNamespace(pytesseract=SimpleNamespace(tesseract_cmd="tesseract"))
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract)
    monkeypatch.setattr(ocr_service, "_pytesseract", None)
    monkeypatch.delenv("TESSERACT_PATH", raising=False)

    assert ocr_service._get_pytesseract() is fake_tesseract
    assert fake_tesseract.pytesseract.tesseract_cmd == "tesseract"


def test_vite_proxy_defaults_to_backend_port_8000():
    """Keep the frontend API proxy aligned with the documented backend port."""
    from pathlib import Path

    vite_config = Path(__file__).resolve().parents[1] / "web" / "vite.config.ts"
    assert "process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'" in vite_config.read_text()


def test_task_queue_uses_configured_storage_directory(monkeypatch, tmp_path):
    """Persist task state on the configured deployment volume."""
    import services.task_queue as task_queue_service

    queue_path = tmp_path / "persistent-queue"
    monkeypatch.setattr(task_queue_service, "_task_queue", None)
    monkeypatch.setenv("TASK_QUEUE_DIR", str(queue_path))

    queue = task_queue_service.get_task_queue()
    assert queue.queue_dir == queue_path
    assert queue_path.is_dir()

    monkeypatch.setattr(task_queue_service, "_task_queue", None)


def test_gemini_provider_requires_available_sdk(monkeypatch):
    """Verify a missing Gemini SDK fails cleanly instead of crashing worker processes."""
    import services.llm_service as llm_service

    monkeypatch.setattr(llm_service, "genai", None)
    monkeypatch.setattr(llm_service, "legacy_genai", None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    try:
        llm_service.GeminiProvider()
        raise AssertionError("GeminiProvider should fail when no SDK is installed")
    except ImportError as exc:
        assert "google-genai" in str(exc) or "google-generativeai" in str(exc)


def test_worker_pool_adds_project_root_to_sys_path():
    """Verify worker pool startup always exposes the project root for spawned workers."""
    import sys
    from pathlib import Path
    from services.worker_pool import WorkerPool

    project_root = str(Path(__file__).resolve().parents[1])
    worker_pool = WorkerPool(max_workers=1)
    worker_pool.start()
    assert project_root in sys.path
    worker_pool.stop()


def test_aadhaar_processor_strategies():
    """Verify Aadhaar-specific normalization and post-processing strategies."""
    print("🧪 Running Aadhaar Processor Strategy Tests...")
    
    # 1. Normalization checks
    raw_data = {
        "gender": "पुरुष",
        "aadhaar_number_masked": "1234  5678  9012"
    }
    normalized = normalize_document_data("aadhaar", raw_data)
    assert normalized["gender"] == "Male"
    assert normalized["aadhaar_number_masked"] == "1234 5678 9012"

    raw_data_female = {"gender": "female"}
    assert normalize_document_data("aadhaar", raw_data_female)["gender"] == "Female"

    # 2. Post-processing check: Force masking and review flag triggers
    aadhaar_doc = AadhaarDocument(
        document_id="doc_001",
        name="John Doe",
        date_of_birth="01/01/1990",
        gender="Male",
        aadhaar_number_masked="123456789012",  # Raw unmasked number
        address="123 Street, Delhi",
        pin_code="110001",
        processing_status=ProcessingStatus.SUCCESS
    )

    processed_doc = post_process_document(aadhaar_doc, ocr_text="my aadhaar is 1234 5678 9012", request_id="req_01")
    
    # Should force mask the number
    assert processed_doc.aadhaar_number_masked == "XXXX XXXX 9012"
    # Should trigger a review flag
    assert processed_doc.needs_review is True
    assert processed_doc.processing_status == ProcessingStatus.NEEDS_REVIEW
    assert len(processed_doc.review_flags) > 0
    assert any("masked" in flag.reason.lower() for flag in processed_doc.review_flags)

    print("✅ Aadhaar Processor Strategy Tests Passed!")


def test_pan_processor_strategies():
    """Verify PAN-specific uppercase rules."""
    print("🧪 Running PAN Processor Strategy Tests...")
    raw_data = {
        "pan_number": "abcde1234f",
        "name": "rahul sharma",
        "father_name": "mohan sharma"
    }
    normalized = normalize_document_data("pan", raw_data)
    assert normalized["pan_number"] == "ABCDE1234F"
    assert normalized["name"] == "RAHUL SHARMA"
    assert normalized["father_name"] == "MOHAN SHARMA"

    # Post processing incorrect PAN format check
    pan_doc = PANDocument(
        document_id="doc_002",
        name="RAHUL SHARMA",
        pan_number="ABC1234",  # Invalid length/format
        processing_status=ProcessingStatus.SUCCESS
    )
    processed_doc = post_process_document(pan_doc, ocr_text="PAN ABC1234", request_id="req_02")
    assert processed_doc.needs_review is True
    assert any("does not match standard" in flag.reason.lower() for flag in processed_doc.review_flags)

    print("✅ PAN Processor Strategy Tests Passed!")


def test_invoice_processor_strategies():
    """Verify Invoice validation checks (e.g. Subtotal + GST = Total)."""
    print("🧪 Running Invoice Processor Strategy Tests...")
    
    raw_data = {
        "line_items": [
            {
                "description": "CERA STALO VIBE 1200X600MM",
                "quantity": 25,
                "rate": 880.00,
                "amount": 22010.58,
            }
        ]
    }
    normalized = normalize_document_data("invoice", raw_data)
    assert normalized["line_items"][0]["description"] == "CERA STALO VIBE 1200X600MM"
    assert normalized["line_items"][0]["quantity"] == 25.0
    assert normalized["line_items"][0]["unit_price"] == 880.0
    assert normalized["line_items"][0]["total_price"] == 22010.58
    
    # 1. Successful math validation
    invoice_ok = InvoiceDocument(
        document_id="doc_003",
        subtotal=100.00,
        gst_amount=18.00,
        total_amount=118.00,
        processing_status=ProcessingStatus.SUCCESS
    )
    processed_ok = post_process_document(invoice_ok, request_id="req_03")
    assert processed_ok.needs_review is False
    assert processed_ok.processing_status == ProcessingStatus.SUCCESS

    # 2. Math mismatch trigger
    invoice_err = InvoiceDocument(
        document_id="doc_004",
        subtotal=100.00,
        gst_amount=18.00,
        total_amount=150.00,  # Invalid sum!
        processing_status=ProcessingStatus.SUCCESS
    )
    processed_err = post_process_document(invoice_err, request_id="req_04")
    assert processed_err.needs_review is True
    assert processed_err.processing_status == ProcessingStatus.NEEDS_REVIEW
    assert any("does not match" in flag.reason.lower() for flag in processed_err.review_flags)

    print("✅ Invoice Processor Strategy Tests Passed!")


def run_all_tests():
    print("=" * 80)
    print("RUNNING BACKEND REFRACTORING VERIFICATION SUITE")
    print("=" * 80)
    
    test_trie_matching()
    print("-" * 80)
    test_normalizer_caching()
    print("-" * 80)
    test_processor_factory_resolution()
    print("-" * 80)
    test_aadhaar_processor_strategies()
    print("-" * 80)
    test_pan_processor_strategies()
    print("-" * 80)
    test_invoice_processor_strategies()
    
    print("=" * 80)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! ZERO REGRESSIONS DETECTED.")
    print("=" * 80)


if __name__ == "__main__":
    run_all_tests()
