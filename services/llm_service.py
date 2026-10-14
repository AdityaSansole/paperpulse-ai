"""
AI Provider Service

Primary: Gemini 1.5 Flash (vision-capable, free, handles Hindi)
Fallback: Groq llama-3.1-8b (text-only, ultra fast)

Architecture:
    Gemini/Groq Response
        ↓
    normalize_document_data()
        ↓
    create_document() (typed schema)
        ↓
    Typed Document (AadhaarDocument, PANDocument, etc.)
"""

import os
import json
import logging
import re
import uuid
import warnings
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

try:
    # Preferred SDK.
    from google import genai
    from google.genai import types
    legacy_genai = None
except ImportError:
    genai = None
    types = None
    legacy_genai = None
    try:
        # Older SDK fallback for environments still using the legacy package.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            import google.generativeai as legacy_genai
    except ImportError:
        legacy_genai = None
from PIL import Image

# NEW: Import normalizer and schema factory
from services.normalizer import normalize_document_data
from models.schemas import create_document, ExtractedDocument, ProcessingStatus

load_dotenv()

logger = logging.getLogger(__name__)

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
DEFAULT_GEMINI_MODELS = (
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)
DEFAULT_GEMINI_MODEL = DEFAULT_GEMINI_MODELS[0]
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 8192
DEFAULT_GEMINI_RETRY_MAX_OUTPUT_TOKENS = 16384


def _resolve_model_candidates(model_name: Optional[str]) -> list[str]:
    """Return the configured model first, then a fallback chain for retired model IDs."""
    candidates: list[str] = []
    if model_name:
        candidates.append(model_name)

    for candidate in DEFAULT_GEMINI_MODELS:
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _get_int_env(name: str, default: int, min_value: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid %s=%r. Using default %s.", name, raw_value, default)
        return default

    if value < min_value:
        logger.warning("%s=%s is too low. Using minimum %s.", name, value, min_value)
        return min_value

    return value


def _get_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _extract_response_text(response) -> str:
    response_text = getattr(response, "text", None)
    if response_text:
        return response_text

    candidates = getattr(response, "candidates", None) or []
    parts_text: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                parts_text.append(text)

    if parts_text:
        return "".join(parts_text)

    return str(response)


def _get_finish_reason(response) -> Optional[str]:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None

    finish_reason = getattr(candidates[0], "finish_reason", None)
    if finish_reason is None:
        return None

    return getattr(finish_reason, "name", str(finish_reason))

# ============================================================
# PROMPTS — One per document type. Specific. No fluff.
# ============================================================

PROMPTS = {
    "aadhaar": """***You are analyzing an Aadhaar card.
Extract ONLY what is clearly visible. Return null for anything unclear.
NEVER guess. NEVER make up data.

CRITICAL RULES:
- If card shows ONLY year (e.g. "Year of Birth: 1990"), return ONLY "1990" for date_of_birth
- Gender: Look for English text FIRST. पुरुष = Male. If both Hindi and English present, use English.
- Name: Return ONLY a clean human name. If the line contains OCR junk, merged fragments, stray prefixes, or uncertain characters, return null instead of guessing.
- Do NOT reconstruct missing letters in names. Do NOT return partial noisy names.
- Address: Extract ONLY actual address with house/flat number, street, city. IGNORE short fragments.
- PIN code: 6-digit number only. If not clearly visible, return null.

AADHAAR NUMBER MASKING (CRITICAL - SECURITY REQUIREMENT):
You MUST mask the Aadhaar number for privacy and security. This is a legal requirement.
- If the visible Aadhaar number is "3511 2297 5747", you MUST return "XXXX XXXX 5747"
- If the visible Aadhaar number is "3179 3974 5818", you MUST return "XXXX XXXX 5818"
- If the visible Aadhaar number is "1234 5678 9012", you MUST return "XXXX XXXX 9012"
- ALWAYS replace the first 8 digits with "XXXX XXXX"
- ONLY show the last 4 digits
- Format: "XXXX XXXX" followed by space and the actual last 4 digits
- NEVER return the full Aadhaar number in ANY field
- Do NOT put unmasked Aadhaar in raw_fields or any other field
- Example: For card showing "3511 2297 5747", you MUST return "XXXX XXXX 5747" in aadhaar_number_masked

Return ONLY this JSON (do NOT add extra fields):
{
  "document_type": "aadhaar",
  "name": "clean name only or null",
  "date_of_birth": "DD/MM/YYYY or YYYY if only year available or null",
  "gender": "Male or Female or null",
  "aadhaar_number_masked": "XXXX XXXX followed by space and the actual last 4 digits, or null",
  "address": "real address only or null",
  "pin_code": "6-digit string or null",
  "side_detected": "front or back or both"
}***

IMPORTANT: Do NOT include raw_fields, summary, or confidence in your response. Only return the exact JSON structure shown above.""",
    
    "pan": """You are analyzing a PAN card — India's tax ID document. Extract ONLY what is clearly visible. Return null for anything unclear. NEVER guess or make up data.

RULES:
- PAN number is exactly 10 characters: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)
- DOB format: DD/MM/YYYY
- PAN numbers are NOT masked — show full number

Return ONLY this JSON, nothing else:
{
  "document_type": "pan",
  "name": "string or null",
  "father_name": "string or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "pan_number": "10-char string or null"
}""",

    "driving_licence": """You are analyzing an Indian Driving License.
Extract ONLY what is clearly visible. Return null for unclear fields.
NEVER guess or make up data.

RULES:
- License number format: State(2) + RTO(2) + Year(4) + Sequence(7). Example: TNBB2019000099
- Date format: DD/MM/YYYY
- Issuing authority is the RTO (Regional Transport Office)

Return ONLY this JSON:
{
  "document_type": "driving_licence",
  "name": "string or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "licence_number": "string or null",
  "date_of_issue": "DD/MM/YYYY or null",
  "date_of_expiry": "DD/MM/YYYY or null",
  "address": "string or null",
  "vehicle_classes": "string or null",
  "issuing_rto": "string or null"
}""",

    "passport": """You are analyzing an Indian Passport.
Extract ONLY what is clearly visible. Return null for unclear fields.
NEVER guess or make up data.

RULES:
- Passport number: 1 letter + 7 digits. Example: K8016274
- MRZ (Machine Readable Zone) is the two lines at the bottom — most reliable part
- Date format: DD/MM/YYYY
- Extract from MRZ if main fields are unclear

Return ONLY this JSON:
{
  "document_type": "passport",
  "surname": "string or null",
  "given_name": "string or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "gender": "Male or Female or null",
  "passport_number": "string or null",
  "date_of_issue": "DD/MM/YYYY or null",
  "date_of_expiry": "DD/MM/YYYY or null",
  "place_of_birth": "string or null",
  "nationality": "Indian or null",
  "mrz_line1": "string or null",
  "mrz_line2": "string or null"
}""",
    
    "invoice": """You are analyzing an Indian TAX INVOICE or GST INVOICE. This is a business document showing goods/services sold.

Extract ONLY what is clearly visible. Return null for anything unclear. NEVER guess.

CRITICAL RULES:
- Look for "TAX INVOICE" or "INVOICE" at the top
- Vendor = Seller/Supplier (top section, has "YOUR COMPANY" or company name)
- Buyer = Customer/Recipient (section with "Buyer" or customer details)
- GSTIN format: 15 characters (e.g., 19BB577660S, 29AABCN9911K)
- Invoice number: Look for "Invoice No." or "LMT.0893.2023-24"
- Date format: DD-MM-YYYY or DD/MM/YYYY
- Amounts: Look for "Total", "CGST", "SGST", "IGST"
- Total amount is the FINAL amount (after all taxes)
- Line items: Extract from table with Description, Quantity, Rate, Amount

IMPORTANT:
- Vendor GSTIN and Buyer GSTIN are DIFFERENT
- Don't confuse vendor with buyer
- Total amount includes all taxes (CGST + SGST or IGST)
- Currency is always INR for Indian invoices

Return ONLY this JSON, nothing else:
{
  "document_type": "invoice",
  "vendor_name": "string or null",
  "vendor_gstin": "15-char string or null",
  "invoice_number": "string or null",
  "invoice_date": "DD-MM-YYYY or null",
  "buyer_name": "string or null",
  "buyer_gstin": "15-char string or null",
  "subtotal": "number (before tax) or null",
  "gst_amount": "number (CGST+SGST or IGST) or null",
  "total_amount": "number (final amount) or null",
  "currency": "INR",
  "line_items": []
}""",
    
    "voter_id": """You are analyzing an Indian Voter ID card (EPIC - Electors Photo Identity Card).
Extract ONLY what is clearly visible. Return null for unclear fields.
NEVER guess or make up data.

RULES:
- Voter ID number format varies by state but typically 3 letters + 7 digits (e.g., ABC1234567)
- Date format: DD/MM/YYYY
- Card has front and back - extract from visible side

Return ONLY this JSON:
{
  "document_type": "voter_id",
  "name": "string or null",
  "father_name": "string or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "gender": "Male or Female or null",
  "voter_id_number": "string or null",
  "address": "string or null",
  "polling_station": "string or null",
  "assembly_constituency": "string or null",
  "side_detected": "front or back or both"
}""",
    
    "ekyc": """You are analyzing a KYC (Know Your Customer) form - bank account opening, investment, or financial services application form.

IMPORTANT: This is NOT a passport, even if passport is mentioned as ID proof.

Extract ONLY what is clearly visible. Return null for anything unclear.

RULES:
- This is a FORM, not an identity document
- Look for: Customer ID, Account Number, Applicant Name, Father/Spouse Name
- Mobile number: 10 digits with +91 or without
- Email: standard email format
- Bank/Organization name: Look for bank name or organization
- Account type: Savings, Current, Demat, Trading, etc.
- Address: Residential or correspondence address
- If form has multiple sections, extract from "Personal Details" or "Identity Details" section

Return ONLY this JSON, nothing else:
{
  "document_type": "ekyc",
  "applicant_name": "string or null",
  "date_of_birth": "DD/MM/YYYY or null",
  "gender": "Male or Female or null",
  "address": "string or null",
  "mobile_number": "10-digit string or null",
  "email": "string or null",
  "account_type": "string or null",
  "bank_name": "string or null"
}""",
    
    "unknown": """You are analyzing a document. Identify what type it is and extract key information. Extract ONLY what is clearly visible. Return null for anything unclear.

Return ONLY this JSON, nothing else:
{
  "document_type": "detected type (aadhaar/pan/invoice/ekyc/other)",
  "raw_fields": {},
  "summary": "one sentence describing what this document is"
}"""
}


def _strip_response_wrappers(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    fence_match = JSON_FENCE_RE.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    return cleaned.strip()


def _repair_json_candidate(text: str) -> str:
    candidate = text.strip()
    if not candidate:
        return candidate

    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    open_braces = candidate.count("{")
    close_braces = candidate.count("}")
    if open_braces > close_braces:
        candidate += "}" * (open_braces - close_braces)

    open_brackets = candidate.count("[")
    close_brackets = candidate.count("]")
    if open_brackets > close_brackets:
        candidate += "]" * (open_brackets - close_brackets)

    return candidate


def _decode_json_value(raw: str):
    raw = raw.strip()
    if raw == "null":
        return None
    if raw.startswith('"') and raw.endswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip('"')
    return raw


def _parse_relaxed_aadhaar_json(text: str) -> dict | None:
    parsed: dict = {"document_type": "aadhaar", "confidence": {"overall": 0.0}}
    field_patterns = {
        "name": r'"?name"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
        "date_of_birth": r'"?date_of_birth"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
        "gender": r'"?gender"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
        "aadhaar_number_masked": r'"?aadhaar_number_masked"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
        "address": r'"?address"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
        "pin_code": r'"?pin_code"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
        "side_detected": r'"?side_detected"?\s*:\s*(null|"[^"]*"|[^,\n}]+)',
    }

    found_any = False
    for field, pattern in field_patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            parsed[field] = _decode_json_value(match.group(1))
            found_any = True

    confidence_fields = ("name", "date_of_birth", "gender", "aadhaar_number", "address")
    confidence: dict[str, float] = {}
    for field in confidence_fields:
        match = re.search(rf'"?{field}"?\s*:\s*([0-9]+(?:\.[0-9]+)?)', text, flags=re.IGNORECASE)
        if match:
            try:
                confidence[field] = float(match.group(1))
            except ValueError:
                pass
    if confidence:
        parsed["confidence"] = confidence

    return parsed if found_any else None


def _parse_model_json(
    text: str,
    doc_type: str,
    request_id: Optional[str] = None
) -> ExtractedDocument:
    """
    Parse Gemini/Groq JSON response into typed document.
    
    NEW ARCHITECTURE:
    1. Parse raw JSON
    2. Normalize data
    3. Create typed document via factory
    
    Args:
        text: Raw JSON response from LLM
        doc_type: Document type
        request_id: Correlation ID for logging
    
    Returns:
        Typed document (AadhaarDocument, PANDocument, etc.)
    """
    log_prefix = f"[{request_id}]" if request_id else ""
    
    logger.info(f"{log_prefix} RAW LLM RESPONSE LENGTH: {len(text)} chars")
    logger.debug(f"{log_prefix} RAW LLM RESPONSE FULL:\n{text}")
    logger.debug(f"{log_prefix} RAW LLM RESPONSE REPR: {repr(text)}")
    
    # Step 1: Parse raw JSON
    cleaned = _strip_response_wrappers(text)
    candidates = [cleaned]

    repaired = _repair_json_candidate(cleaned)
    if repaired and repaired not in candidates:
        candidates.append(repaired)

    raw_data = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            raw_data = json.loads(candidate)
            logger.info(f"{log_prefix} Raw LLM response parsed successfully")
            break
        except json.JSONDecodeError as e:
            logger.warning(f"{log_prefix} JSON parse failed for candidate: {str(e)}")
            continue

    # Fallback: Try relaxed Aadhaar parsing
    if not raw_data and doc_type == "aadhaar":
        raw_data = _parse_relaxed_aadhaar_json(cleaned or text)
        if raw_data:
            logger.warning(f"{log_prefix} Recovered Aadhaar fields from malformed JSON")

    # If still no data, return failed UnknownDocument
    if not raw_data:
        logger.error(f"{log_prefix} Unable to parse LLM JSON response")
        return create_document(
            document_type="unknown",
            data={
                "detected_document_type": doc_type,
                "summary": "Failed to parse LLM response",
                "processing_status": ProcessingStatus.FAILED
            },
            request_id=request_id
        )
    
    # Log raw response (for debugging)
    logger.debug(f"{log_prefix} Raw parsed data: {raw_data}")
    
    # Step 2: Detect document type
    detected_type = str(raw_data.get("document_type", doc_type) or doc_type).strip().lower()
    if detected_type in {"other", "unknown", "unclear", "not_applicable"}:
        detected_type = "unknown"

    # Step 3: Normalize data BEFORE schema validation
    logger.info(f"{log_prefix} Normalizing {detected_type} data")
    normalized_data = normalize_document_data(detected_type, raw_data)
    normalized_data["document_type"] = detected_type
    logger.debug(f"{log_prefix} Normalized data: {normalized_data}")

    # Step 4: Create typed document via factory
    logger.info(f"{log_prefix} Creating typed document: {detected_type}")
    document = create_document(
        document_type=detected_type,
        data=normalized_data,
        request_id=request_id
    )
    
    # Log document type for verification
    logger.info(f"{log_prefix} Created document type: {type(document).__name__}")
    
    return document


# ============================================================
# BASE PROVIDER
# ============================================================

class BaseAIProvider(ABC):
    @abstractmethod
    def extract_from_image(
        self,
        image_path: str,
        doc_type: str,
        request_id: Optional[str] = None
    ) -> ExtractedDocument:
        """Extract fields from document image"""
        pass
    
    @abstractmethod
    def extract_from_text(
        self,
        text: str,
        doc_type: str = "unknown",
        request_id: Optional[str] = None
    ) -> ExtractedDocument:
        """Extract fields from OCR text"""
        pass
    
    def get_prompt(self, doc_type: str) -> str:
        return PROMPTS.get(doc_type, PROMPTS["unknown"])


# ============================================================
# GEMINI PROVIDER (PRIMARY)
# ============================================================

class GeminiProvider(BaseAIProvider):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY/GOOGLE_API_KEY not set in .env")

        if genai is None and legacy_genai is None:
            raise ImportError(
                "Neither google-genai nor google-generativeai is installed. "
                "Install the project dependencies with: pip install -r requirements.txt"
            )
        
        self.model_name = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.model_names = _resolve_model_candidates(self.model_name)
        self.model_name = self.model_names[0]
        self.max_output_tokens = _get_int_env(
            "GEMINI_MAX_OUTPUT_TOKENS",
            DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
            min_value=1024,
        )
        self.retry_max_output_tokens = _get_int_env(
            "GEMINI_RETRY_MAX_OUTPUT_TOKENS",
            max(DEFAULT_GEMINI_RETRY_MAX_OUTPUT_TOKENS, self.max_output_tokens),
            min_value=self.max_output_tokens,
        )
        self.disable_thinking = _get_bool_env("GEMINI_DISABLE_THINKING", True)
        self.sdk_name = "google-genai" if genai is not None else "google-generativeai"

        if genai is not None:
            self.client = genai.Client(api_key=api_key)
            self.model = None
        else:
            legacy_genai.configure(api_key=api_key)
            self.client = None
            self.model = None

        logger.info(
            "GeminiProvider initialized with %s via %s (max_output_tokens=%s, "
            "retry_max_output_tokens=%s, disable_thinking=%s)",
            self.model_name,
            self.sdk_name,
            self.max_output_tokens,
            self.retry_max_output_tokens,
            self.disable_thinking,
        )

    def _generation_config(self, max_output_tokens: int):
        config_kwargs = {
            "temperature": 0.0,
            "max_output_tokens": max_output_tokens,
            "response_mime_type": "application/json",
        }

        if self.sdk_name == "google-generativeai":
            return config_kwargs

        if self.disable_thinking and hasattr(types, "ThinkingConfig"):
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception as exc:
                logger.debug("Unable to configure Gemini thinking budget: %s", exc)

        try:
            return types.GenerateContentConfig(**config_kwargs)
        except Exception:
            config_kwargs.pop("thinking_config", None)
            return types.GenerateContentConfig(**config_kwargs)

    def _generate_content(self, contents, request_id: Optional[str] = None):
        log_prefix = f"[{request_id}]" if request_id else ""
        last_error: Optional[Exception] = None

        for model_name in self.model_names:
            self.model_name = model_name
            try:
                if self.sdk_name == "google-genai":
                    response = self.client.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=self._generation_config(self.max_output_tokens),
                    )
                else:
                    if self.model is None:
                        self.model = legacy_genai.GenerativeModel(self.model_name)
                    response = self.model.generate_content(
                        contents,
                        generation_config=self._generation_config(self.max_output_tokens),
                    )

                finish_reason = _get_finish_reason(response)

                if finish_reason == "MAX_TOKENS" and self.retry_max_output_tokens > self.max_output_tokens:
                    logger.warning(
                        "%s Gemini response hit MAX_TOKENS at %s. Retrying with %s.",
                        log_prefix,
                        self.max_output_tokens,
                        self.retry_max_output_tokens,
                    )
                    if self.sdk_name == "google-genai":
                        response = self.client.models.generate_content(
                            model=self.model_name,
                            contents=contents,
                            config=self._generation_config(self.retry_max_output_tokens),
                        )
                    else:
                        if self.model is None:
                            self.model = legacy_genai.GenerativeModel(self.model_name)
                        response = self.model.generate_content(
                            contents,
                            generation_config=self._generation_config(self.retry_max_output_tokens),
                        )

                return response
            except Exception as exc:
                last_error = exc
                error_text = str(exc).upper()
                if "404" not in error_text and "NOT_FOUND" not in error_text:
                    raise
                logger.warning(
                    "%s Gemini model %s is unavailable (%s). Trying next available model.",
                    log_prefix,
                    model_name,
                    exc,
                )

        if last_error is not None:
            raise last_error
        raise RuntimeError("No Gemini model candidates were available")
    
    def extract_from_image(
        self,
        image_path: str,
        doc_type: str,
        request_id: Optional[str] = None
    ) -> ExtractedDocument:
        """
        Extract from image using Gemini Vision.
        
        NEW: Returns typed document (not dict)
        """
        log_prefix = f"[{request_id}]" if request_id else ""
        
        try:
            from PIL import Image
            image = Image.open(image_path)
            prompt = self.get_prompt(doc_type)
            
            response = None  # Initialize response
            
            try:
                logger.info(f"{log_prefix} Calling Gemini Vision for {doc_type}")
                
                # NEW SDK: Can pass PIL Image and text directly in contents list.
                response = self._generate_content([prompt, image], request_id)
                
                # Extract text from response
                response_text = _extract_response_text(response)
                finish_reason = _get_finish_reason(response)
                
                # DEBUG: Log response details
                logger.debug(f"{log_prefix} Response type: {type(response)}")
                logger.debug(f"{log_prefix} Response has .text: {hasattr(response, 'text')}")
                logger.debug(f"{log_prefix} Response.text length: {len(response_text)}")
                logger.info(f"{log_prefix} Gemini finish reason: {finish_reason or 'unknown'}")
                logger.debug(f"{log_prefix} Response candidates: {len(response.candidates) if hasattr(response, 'candidates') else 'N/A'}")
                if hasattr(response, 'candidates') and response.candidates:
                    logger.debug(f"{log_prefix} First candidate parts: {len(response.candidates[0].content.parts) if hasattr(response.candidates[0], 'content') else 'N/A'}")
                
                if finish_reason == "MAX_TOKENS":
                    raise ValueError(
                        "Gemini response was truncated by MAX_TOKENS even after retry. "
                        "Increase GEMINI_RETRY_MAX_OUTPUT_TOKENS."
                    )
                
                # Validate response is not empty/bad
                if not response_text or len(response_text.strip()) < 10:
                    raise ValueError("Gemini returned empty or invalid response")
                
                # Log raw response (truncated)
                logger.debug(f"{log_prefix} Raw Gemini response: {response_text[:200]}...")
                
                # NEW: Parse into typed document
                document = _parse_model_json(response_text, doc_type, request_id)
                
                # Validate result is not garbage (basic check)
                if document.processing_status == ProcessingStatus.FAILED:
                    raise ValueError("Gemini returned failed document")
                
                logger.info(f"{log_prefix} Gemini extraction successful: {type(document).__name__}")
                return document
            
            finally:
                # Cleanup: close image to free memory
                if image:
                    try:
                        image.close()
                    except Exception:
                        pass
        
        except Exception as e:
            logger.error(f"{log_prefix} Gemini extraction failed: {e}")
            # Return failed UnknownDocument
            return create_document(
                document_type="unknown",
                data={
                    "detected_document_type": doc_type,
                    "summary": f"Gemini extraction failed: {str(e)}",
                    "processing_status": ProcessingStatus.FAILED
                },
                request_id=request_id
            )
    
    def extract_from_text(
        self,
        text: str,
        doc_type: str = "unknown",
        request_id: Optional[str] = None
    ) -> ExtractedDocument:
        """
        Extract from OCR text using Gemini.
        
        NEW: Returns typed document (not dict)
        """
        log_prefix = f"[{request_id}]" if request_id else ""
        
        try:
            prompt = self.get_prompt(doc_type)
            full_prompt = f"{prompt}\n\nDocument text:\n{text}"
            
            logger.info(f"{log_prefix} Calling Gemini for text extraction: {doc_type}")
            
            response = self._generate_content(full_prompt, request_id)
            
            # Extract text from response
            response_text = _extract_response_text(response)
            finish_reason = _get_finish_reason(response)
            logger.info(f"{log_prefix} Gemini finish reason: {finish_reason or 'unknown'}")
            if finish_reason == "MAX_TOKENS":
                raise ValueError(
                    "Gemini response was truncated by MAX_TOKENS even after retry. "
                    "Increase GEMINI_RETRY_MAX_OUTPUT_TOKENS."
                )
            
            # Validate response
            if not response_text or len(response_text.strip()) < 10:
                raise ValueError("Gemini returned empty or invalid response")
            
            # NEW: Parse into typed document
            document = _parse_model_json(response_text, doc_type, request_id)
            
            logger.info(f"{log_prefix} Gemini text extraction successful: {type(document).__name__}")
            return document
        
        except Exception as e:
            logger.error(f"{log_prefix} Gemini text extraction failed: {e}")
            # Return failed UnknownDocument
            return create_document(
                document_type="unknown",
                data={
                    "detected_document_type": doc_type,
                    "summary": f"Gemini text extraction failed: {str(e)}",
                    "processing_status": ProcessingStatus.FAILED
                },
                request_id=request_id
            )


# ============================================================
# GROQ PROVIDER (TEXT-ONLY FALLBACK)
# ============================================================

class GroqProvider(BaseAIProvider):
    def __init__(self):
        try:
            from groq import Groq
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY not set in .env")
            self.client = Groq(api_key=api_key)
            self.model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
            logger.info("GroqProvider initialized with model %s", self.model)
        except ImportError:
            raise ImportError("groq not installed. Run: pip install groq")
    
    def extract_from_image(self, image_path: str, doc_type: str) -> dict:
        """Groq cannot process images — use OCR first then extract_from_text"""
        raise NotImplementedError("Groq is text-only. Run OCR first, then use extract_from_text()")
    
    def extract_from_text(
        self,
        text: str,
        doc_type: str = "unknown",
        request_id: Optional[str] = None
    ) -> ExtractedDocument:
        """
        Extract from OCR text using Groq.
        
        NEW: Returns typed document (not dict)
        """
        log_prefix = f"[{request_id}]" if request_id else ""
        
        try:
            prompt = self.get_prompt(doc_type)
            full_prompt = f"{prompt}\n\nDocument text:\n{text}"
            
            logger.info(f"{log_prefix} Calling Groq for text extraction: {doc_type}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=1024,
            )
            
            # Validate response
            if not response or not response.choices or not response.choices[0].message.content:
                raise ValueError("Groq returned empty or invalid response")
            
            # NEW: Parse into typed document
            document = _parse_model_json(response.choices[0].message.content, doc_type, request_id)
            
            logger.info(f"{log_prefix} Groq text extraction successful: {type(document).__name__}")
            return document
        
        except Exception as e:
            logger.error(f"{log_prefix} Groq text extraction failed: {e}")
            # Return failed UnknownDocument
            return create_document(
                document_type="unknown",
                data={
                    "detected_document_type": doc_type,
                    "summary": f"Groq text extraction failed: {str(e)}",
                    "processing_status": ProcessingStatus.FAILED
                },
                request_id=request_id
            )


# ============================================================
# OLLAMA PROVIDER (LOCAL TEXT-ONLY FALLBACK)
# ============================================================

class OllamaProvider(BaseAIProvider):
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self.model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self.timeout = _get_int_env("OLLAMA_TIMEOUT_SECONDS", 120, min_value=10)
        logger.info("OllamaProvider initialized with model %s at %s", self.model, self.base_url)

    def _chat(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")

        if not body:
            raise ValueError("Ollama returned an empty response")

        parsed = json.loads(body)
        message = parsed.get("message") or {}
        content = message.get("content") or parsed.get("response")
        if not content:
            raise ValueError("Ollama response did not include usable content")

        return str(content)

    def extract_from_image(self, image_path: str, doc_type: str) -> dict:
        """Ollama is text-only. Run OCR first, then use extract_from_text()."""
        raise NotImplementedError("Ollama is text-only. Run OCR first, then use extract_from_text()")

    def extract_from_text(
        self,
        text: str,
        doc_type: str = "unknown",
        request_id: Optional[str] = None
    ) -> ExtractedDocument:
        """Extract from OCR text using a local Ollama model."""
        log_prefix = f"[{request_id}]" if request_id else ""

        try:
            prompt = self.get_prompt(doc_type)
            full_prompt = f"{prompt}\n\nDocument text:\n{text}"

            logger.info(f"{log_prefix} Calling Ollama for text extraction: {doc_type}")
            response_text = self._chat(full_prompt)
            if not response_text or len(response_text.strip()) < 10:
                raise ValueError("Ollama returned empty or invalid response")

            document = _parse_model_json(response_text, doc_type, request_id)
            logger.info(f"{log_prefix} Ollama text extraction successful: {type(document).__name__}")
            return document

        except Exception as e:
            logger.error(f"{log_prefix} Ollama text extraction failed: {e}")
            return create_document(
                document_type="unknown",
                data={
                    "detected_document_type": doc_type,
                    "summary": f"Ollama text extraction failed: {str(e)}",
                    "processing_status": ProcessingStatus.FAILED
                },
                request_id=request_id
            )


# ============================================================
# PROVIDER FACTORY — Call this everywhere
# ============================================================

def get_ai_provider() -> BaseAIProvider:
    provider = (os.getenv("AI_PROVIDER") or "").strip().lower()
    if not provider:
        provider = "groq" if os.getenv("GROQ_API_KEY") else "gemini"

    if provider == "gemini":
        return GeminiProvider()
    elif provider == "groq":
        return GroqProvider()
    elif provider == "ollama":
        return OllamaProvider()
    else:
        logger.warning(f"Unknown provider '{provider}', defaulting to Groq when available else Gemini")
        if os.getenv("GROQ_API_KEY"):
            return GroqProvider()
        return GeminiProvider()


# ============================================================
# MAIN EXTRACTION FUNCTION — Use this in document_service.py
# ============================================================

def extract_document(image_path: str, doc_type: str = "unknown") -> tuple[ExtractedDocument, dict]:
    """
    Main entry point for document extraction.
    
    NEW ARCHITECTURE:
    - Returns typed document (not dict)
    - Generates request_id for correlation
    - Returns metadata separately
    
    Tries Gemini Vision first (no OCR needed).
    Falls back to OCR + Groq if Gemini fails.
    
    Args:
        image_path: Path to image or PDF file
        doc_type: Document type (aadhaar/pan/invoice/ekyc/unknown)
    
    Returns:
        Tuple of (ExtractedDocument, metadata_dict)
    """
    import time
    
    # Generate request ID at entry (correlation backbone)
    request_id = str(uuid.uuid4())
    start_time = time.time()
    provider_errors: list[str] = []
    
    logger.info(f"[{request_id}] Starting extraction: {doc_type} from {image_path}")
    
    provider = get_ai_provider()
    provider_name = type(provider).__name__.lower()

    if provider_name == "groqprovider":
        logger.info(f"[{request_id}] AI provider is configured as Groq; skipping Gemini and using Groq OCR-text path.")
    else:
        # Try Gemini Vision first when Gemini is the active provider.
        try:
            provider = GeminiProvider()
            document = provider.extract_from_image(image_path, doc_type, request_id)

            if document.processing_status == ProcessingStatus.FAILED:
                reason = getattr(document, "summary", None) or "Gemini extraction returned failed status"
                raise RuntimeError(reason)

            metadata = {
                "request_id": request_id,
                "provider": "gemini_vision",
                "model_used": provider.model_name,
                "processing_time_ms": round((time.time() - start_time) * 1000, 2),
                "ocr_used": False,
                "fallback_used": False,
                "provider_errors": provider_errors,
            }

            logger.info(f"[{request_id}] Extraction successful via Gemini Vision")
            return document, metadata

        except Exception as e:
            provider_errors.append(f"Gemini Vision: {e}")
            logger.warning(f"[{request_id}] Gemini Vision failed: {e}. Trying OCR + Groq fallback.")

    # Fallback: OCR + Groq
    try:
        from services.ocr_service import extract_text
        ocr_text, ocr_confidence = extract_text(image_path)
        logger.info(f"[{request_id}] OCR done: {len(ocr_text)} chars, confidence {ocr_confidence:.2f}")

        if ocr_text and len(ocr_text.strip()) > 20:
            provider = GroqProvider()
            document = provider.extract_from_text(ocr_text, doc_type, request_id)

            if document.processing_status == ProcessingStatus.FAILED:
                reason = getattr(document, "summary", None) or "Groq extraction returned failed status"
                raise RuntimeError(reason)

            metadata = {
                "request_id": request_id,
                "provider": "groq",
                "model_used": getattr(provider, "model", DEFAULT_GROQ_MODEL),
                "processing_time_ms": round((time.time() - start_time) * 1000, 2),
                "ocr_used": True,
                "ocr_confidence": ocr_confidence,
                "fallback_used": True,
                "provider_errors": provider_errors,
            }

            logger.info(f"[{request_id}] Extraction successful via Groq fallback")
            return document, metadata
        else:
            raise RuntimeError("OCR text too short or empty")

    except Exception as e:
        provider_errors.append(f"OCR/Groq fallback: {e}")
        logger.error(f"[{request_id}] Groq fallback also failed: {e}")
    
    # Everything failed - return failed UnknownDocument
    logger.error(f"[{request_id}] All extraction methods failed")
    
    failed_document = create_document(
        document_type="unknown",
        data={
            "detected_document_type": doc_type,
            "summary": "; ".join(provider_errors) if provider_errors else "All extraction providers failed",
            "processing_status": ProcessingStatus.FAILED
        },
        request_id=request_id
    )
    
    metadata = {
        "request_id": request_id,
        "provider": "none",
        "model_used": None,
        "processing_time_ms": round((time.time() - start_time) * 1000, 2),
        "ocr_used": False,
        "fallback_used": True,
        "provider_errors": provider_errors,
    }
    
    return failed_document, metadata
