"""
Document Extraction Schemas - Production Grade

Architecture:
- Typed document schemas (one per document type)
- Discriminated union for type safety
- Structured review flags
- Computed fields for consistency
- Graceful degradation (never raises exceptions)
- Observability built-in
"""

from pydantic import BaseModel, Field, computed_field
from typing import Optional, List, Union, Literal, Annotated
from enum import Enum
from datetime import datetime
import uuid


# ============================================================
# ENUMS
# ============================================================

class ReviewSeverity(str, Enum):
    """Severity levels for review flags"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProcessingStatus(str, Enum):
    """Processing status for documents"""
    SUCCESS = "success"          # Extraction valid and complete
    PARTIAL = "partial"          # Incomplete extraction
    FAILED = "failed"            # Unusable extraction
    NEEDS_REVIEW = "needs_review"  # Suspicious but usable


# ============================================================
# REVIEW FLAG MODEL
# ============================================================

class ReviewFlag(BaseModel):
    """Structured review flag for field-level issues"""
    field: str
    severity: ReviewSeverity
    reason: str
    # Future: reason_code: ReviewReason (error taxonomy)
    
    model_config = {"extra": "forbid"}


# ============================================================
# BASE DOCUMENT
# ============================================================

class BaseDocument(BaseModel):
    """Base class with fields common to ALL documents"""
    
    # Stable internal ID (CRITICAL for tracking)
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Document type (discriminator)
    document_type: str
    
    # Processing status (operational)
    processing_status: ProcessingStatus = ProcessingStatus.SUCCESS
    
    # Review mechanisms (STRUCTURED + COMPUTED)
    review_flags: List[ReviewFlag] = Field(default_factory=list)
    review_notes: List[str] = Field(default_factory=list)
    
    @computed_field
    @property
    def needs_review(self) -> bool:
        """Computed from review_flags - prevents desync"""
        return len(self.review_flags) > 0
    
    # Internal/debug only - NEVER expose to frontend by default
    raw_fields: Optional[dict] = Field(None, exclude=True)
    
    # STRICT: Reject hallucinated fields
    model_config = {"extra": "forbid"}


# ============================================================
# DOCUMENT SCHEMAS
# ============================================================

class AadhaarDocument(BaseDocument):
    document_type: Literal["aadhaar"] = "aadhaar"
    
    # Identity fields
    name: Optional[str] = None
    date_of_birth: Optional[str] = None  # TODO: normalize to ISO date later
    gender: Optional[str] = None
    father_name: Optional[str] = None
    
    # Aadhaar specific (SECURITY: always masked)
    aadhaar_number_masked: Optional[str] = None
    
    # Address
    address: Optional[str] = None
    pin_code: Optional[str] = None
    
    # Card info
    side_detected: Optional[str] = None


class PANDocument(BaseDocument):
    document_type: Literal["pan"] = "pan"
    
    # Identity fields
    name: Optional[str] = None
    father_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    
    # PAN specific
    pan_number: Optional[str] = None


class VoterIDDocument(BaseDocument):
    document_type: Literal["voter_id"] = "voter_id"
    
    # Identity fields
    name: Optional[str] = None
    father_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    
    # Voter ID specific
    voter_id_number: Optional[str] = None
    
    # Address
    address: Optional[str] = None
    
    # Election info
    polling_station: Optional[str] = None
    assembly_constituency: Optional[str] = None
    
    # Card info
    side_detected: Optional[str] = None


class DrivingLicenseDocument(BaseDocument):
    document_type: Literal["driving_licence"] = "driving_licence"
    
    # Identity fields
    name: Optional[str] = None
    date_of_birth: Optional[str] = None
    
    # License specific
    licence_number: Optional[str] = None
    date_of_issue: Optional[str] = None
    date_of_expiry: Optional[str] = None
    
    # Address
    address: Optional[str] = None
    
    # License details (normalized empty list)
    vehicle_classes: List[str] = Field(default_factory=list)
    issuing_rto: Optional[str] = None


class PassportDocument(BaseDocument):
    document_type: Literal["passport"] = "passport"
    
    # Identity fields
    surname: Optional[str] = None
    given_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    
    # Passport specific
    passport_number: Optional[str] = None
    date_of_issue: Optional[str] = None
    date_of_expiry: Optional[str] = None
    place_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    
    # MRZ
    mrz_line1: Optional[str] = None
    mrz_line2: Optional[str] = None


class InvoiceLineItem(BaseModel):
    """Structured line item for invoices"""
    item_name: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    
    model_config = {"extra": "forbid"}


class InvoiceDocument(BaseDocument):
    document_type: Literal["invoice"] = "invoice"
    
    # Vendor info
    vendor_name: Optional[str] = None
    vendor_gstin: Optional[str] = None
    
    # Buyer info
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    
    # Invoice details
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    
    # Amounts
    subtotal: Optional[float] = None
    gst_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = "INR"
    
    # Line items (normalized empty list)
    line_items: List[InvoiceLineItem] = Field(default_factory=list)


class EKYCDocument(BaseDocument):
    document_type: Literal["ekyc"] = "ekyc"
    
    # Identity fields
    applicant_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    
    # Contact
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    
    # Address
    address: Optional[str] = None
    
    # Bank details
    account_type: Optional[str] = None
    bank_name: Optional[str] = None


class UnknownDocument(BaseDocument):
    document_type: Literal["unknown"] = "unknown"
    
    # What Gemini detected (may be wrong)
    detected_document_type: Optional[str] = None
    
    # Fallback fields (PROTECTED: size limits)
    summary: Optional[str] = Field(None, max_length=1000)
    raw_text: Optional[str] = Field(None, max_length=50000)


# ============================================================
# UNION TYPE
# ============================================================

ExtractedDocument = Annotated[
    Union[
        AadhaarDocument,
        PANDocument,
        VoterIDDocument,
        DrivingLicenseDocument,
        PassportDocument,
        InvoiceDocument,
        EKYCDocument,
        UnknownDocument
    ],
    Field(discriminator='document_type')
]


# ============================================================
# SCHEMA FACTORY
# ============================================================

from pydantic import ValidationError
import logging

logger = logging.getLogger(__name__)


DOCUMENT_SCHEMA_MAP = {
    "aadhaar": AadhaarDocument,
    "pan": PANDocument,
    "voter_id": VoterIDDocument,
    "driving_licence": DrivingLicenseDocument,
    "passport": PassportDocument,
    "invoice": InvoiceDocument,
    "ekyc": EKYCDocument,
    "unknown": UnknownDocument,
}


def create_document(
    document_type: str,
    data: dict,
    request_id: Optional[str] = None
) -> ExtractedDocument:
    """
    Factory function to create correct document schema.
    
    IMPORTANT: Never raises exceptions - always returns valid document.
    
    Args:
        document_type: Type of document
        data: Extracted data dict
        request_id: Optional correlation ID for logging
    
    Returns:
        Typed document instance (may be UnknownDocument on failure)
    """
    log_prefix = f"[{request_id}]" if request_id else ""

    normalized_type = str(document_type or "unknown").strip().lower()
    if normalized_type in {"other", "unknown", "unclear", "not_applicable"}:
        normalized_type = "unknown"
        data = {**data, "document_type": "unknown"}

    schema_class = DOCUMENT_SCHEMA_MAP.get(normalized_type)
    
    if not schema_class:
        # Unknown document type
        logger.warning(f"{log_prefix} Unknown document type: {document_type}")
        return UnknownDocument(
            document_type="unknown",
            detected_document_type=document_type,
            summary=f"Unrecognized document type: {document_type}",
            processing_status=ProcessingStatus.FAILED,
            review_flags=[
                ReviewFlag(
                    field="document_type",
                    severity=ReviewSeverity.HIGH,
                    reason=f"Unknown document type: {document_type}"
                )
            ]
        )
    
    try:
        # Attempt to create typed document
        document = schema_class(**data)
        
        # Set processing status based on review flags
        if document.needs_review:
            document.processing_status = ProcessingStatus.NEEDS_REVIEW
        
        return document
    
    except ValidationError as e:
        # Schema validation failed - return UnknownDocument with errors
        logger.error(f"{log_prefix} Schema validation failed for {document_type}: {e}")
        
        return UnknownDocument(
            document_type="unknown",
            detected_document_type=document_type,
            summary=f"Schema validation failed for {document_type}",
            processing_status=ProcessingStatus.FAILED,
            review_flags=[
                ReviewFlag(
                    field="schema_validation",
                    severity=ReviewSeverity.HIGH,
                    reason=f"Validation error: {str(e)}"
                )
            ]
        )


# ============================================================
# RESPONSE MODELS
# ============================================================

class ProcessingMetadata(BaseModel):
    """Metadata for document processing"""
    # Schema version
    schema_version: str = "3.0"
    validation_version: str = "1.0"  # Validator version
    
    # Timestamps
    processed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Document info
    document_id: str
    document_type: str
    processing_status: ProcessingStatus
    
    # Review summary
    needs_review: bool
    review_count: int
    
    # Observability (correlation IDs)
    request_id: Optional[str] = None
    
    # Processing details
    processing_time_ms: Optional[float] = None
    model_used: Optional[str] = None
    fallback_used: bool = False
    ocr_used: bool = False


class DocumentResponse(BaseModel):
    """External API response structure - SEPARATED from internal schema"""
    success: bool
    filename: str
    
    # TYPED document (not dict)
    document: ExtractedDocument
    
    # Separated metadata
    metadata: ProcessingMetadata
    
    # Optional fields
    message: Optional[str] = None
    json_output_file: Optional[str] = None
    download_url: Optional[str] = None


# ============================================================
# SERIALIZER
# ============================================================

def serialize_document_response(
    document: ExtractedDocument,
    filename: str,
    request_id: Optional[str] = None,
    processing_time_ms: Optional[float] = None,
    model_used: Optional[str] = None,
    fallback_used: bool = False,
    ocr_used: bool = False,
    include_raw_fields: bool = False
) -> DocumentResponse:
    """
    Serialize document for API response.
    
    IMPORTANT: This separates internal schema from external API.
    
    Security:
    - Excludes raw_fields by default (may contain unmasked data)
    - Adds observability metadata
    - Maintains type safety
    
    Args:
        document: Typed document instance
        filename: Original filename
        request_id: Correlation ID for tracking
        processing_time_ms: Processing duration
        model_used: AI model used (gemini/groq)
        fallback_used: Whether fallback was triggered
        ocr_used: Whether OCR was used
        include_raw_fields: Include raw_fields (debug only)
    
    Returns:
        Typed API response with separated document and metadata
    """
    # Build metadata
    metadata = ProcessingMetadata(
        document_id=document.document_id,
        document_type=document.document_type,
        processing_status=document.processing_status,
        needs_review=document.needs_review,
        review_count=len(document.review_flags),
        request_id=request_id,
        processing_time_ms=processing_time_ms,
        model_used=model_used,
        fallback_used=fallback_used,
        ocr_used=ocr_used
    )
    
    # Return typed response
    return DocumentResponse(
        success=document.processing_status != ProcessingStatus.FAILED,
        filename=filename,
        document=document,
        metadata=metadata
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def document_to_json(
    document: ExtractedDocument,
    include_raw_fields: bool = False,
    include_null_fields: bool = False
) -> dict:
    """
    Convert document to JSON dict for storage/API.
    
    Args:
        document: Typed document
        include_raw_fields: Include raw_fields (debug)
        include_null_fields: Keep null fields (analytics)
    
    Returns:
        JSON-serializable dict
    """
    return document.model_dump(
        exclude_none=not include_null_fields,
        exclude={"raw_fields"} if not include_raw_fields else set(),
        mode="json"
    )
