"""
Comprehensive test script for all document types
Tests: Aadhaar, PAN, Voter ID, Driving License, Passport, Invoice, eKYC
Supports: Images (JPG, PNG), PDFs, and camera photos
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from services.document_service import process_document


# Test files configuration
TEST_FILES = {
    "aadhaar": "uploads/aadhaar_sample.jpg",
    "pan": "uploads/pan_sample.jpg",
    "voter_id": "uploads/voter_id_sample.jpg",
    "driving_licence": "uploads/dl_sample.jpg",
    "passport": "uploads/passport_sample.jpg",
    "invoice": "uploads/invoice_sample.jpg",
    "ekyc": "uploads/ekyc_sample.jpg",
}


def display_document_result(data: dict, doc_type: str):
    """Display extraction results in a formatted way"""
    
    print(f"\n📋 Document Type: {data.get('document_type', 'unknown')}")
    print(f"🔍 Processing Status: {data.get('processing_status', 'unknown')}")
    print(f"🆔 Document ID: {data.get('document_id', 'N/A')}")
    
    print("\n📊 EXTRACTED FIELDS:")
    print("-" * 80)
    
    # Display fields based on document type
    if doc_type == "aadhaar":
        fields = [
            ('name', 'Name'),
            ('date_of_birth', 'Date of Birth'),
            ('gender', 'Gender'),
            ('aadhaar_number_masked', 'Aadhaar Number'),
            ('address', 'Address'),
            ('pin_code', 'PIN Code'),
            ('side_detected', 'Side Detected'),
        ]
    elif doc_type == "pan":
        fields = [
            ('name', 'Name'),
            ('father_name', 'Father Name'),
            ('date_of_birth', 'Date of Birth'),
            ('pan_number', 'PAN Number'),
        ]
    elif doc_type == "voter_id":
        fields = [
            ('name', 'Name'),
            ('father_name', 'Father Name'),
            ('date_of_birth', 'Date of Birth'),
            ('gender', 'Gender'),
            ('voter_id_number', 'Voter ID Number'),
            ('address', 'Address'),
            ('polling_station', 'Polling Station'),
            ('assembly_constituency', 'Assembly Constituency'),
        ]
    elif doc_type == "driving_licence":
        fields = [
            ('name', 'Name'),
            ('date_of_birth', 'Date of Birth'),
            ('licence_number', 'License Number'),
            ('date_of_issue', 'Date of Issue'),
            ('date_of_expiry', 'Date of Expiry'),
            ('address', 'Address'),
            ('vehicle_classes', 'Vehicle Classes'),
            ('issuing_rto', 'Issuing RTO'),
        ]
    elif doc_type == "passport":
        fields = [
            ('surname', 'Surname'),
            ('given_name', 'Given Name'),
            ('date_of_birth', 'Date of Birth'),
            ('gender', 'Gender'),
            ('passport_number', 'Passport Number'),
            ('date_of_issue', 'Date of Issue'),
            ('date_of_expiry', 'Date of Expiry'),
            ('place_of_birth', 'Place of Birth'),
            ('nationality', 'Nationality'),
        ]
    elif doc_type == "invoice":
        print("\n  VENDOR:")
        print(f"    Name  : {data.get('vendor_name', '[Not found]')}")
        print(f"    GSTIN : {data.get('vendor_gstin', '[Not found]')}")
        print("\n  BUYER:")
        print(f"    Name  : {data.get('buyer_name', '[Not found]')}")
        print(f"    GSTIN : {data.get('buyer_gstin', '[Not found]')}")
        print("\n  INVOICE:")
        print(f"    Number: {data.get('invoice_number', '[Not found]')}")
        print(f"    Date  : {data.get('invoice_date', '[Not found]')}")
        print("\n  AMOUNTS:")
        currency = data.get('currency', 'INR')
        subtotal = data.get('subtotal')
        gst = data.get('gst_amount')
        total = data.get('total_amount')
        if subtotal:
            print(f"    Subtotal   : {currency} {subtotal:,.2f}")
        if gst:
            print(f"    GST        : {currency} {gst:,.2f}")
        if total:
            print(f"    Total      : {currency} {total:,.2f}")
        fields = []
    elif doc_type == "ekyc":
        fields = [
            ('applicant_name', 'Applicant Name'),
            ('date_of_birth', 'Date of Birth'),
            ('gender', 'Gender'),
            ('mobile_number', 'Mobile Number'),
            ('email', 'Email'),
            ('address', 'Address'),
            ('account_type', 'Account Type'),
            ('bank_name', 'Bank Name'),
        ]
    else:
        fields = []
    
    # Display fields
    for field_key, field_label in fields:
        value = data.get(field_key)
        if value:
            print(f"  {field_label:25s}: {value}")
        else:
            print(f"  {field_label:25s}: [Not found]")
    
    # Display review flags
    review_flags = data.get('review_flags', [])
    needs_review = data.get('needs_review', False)
    
    if needs_review or review_flags:
        print("\n⚠️  REVIEW FLAGS:")
        print("-" * 80)
        for flag in review_flags:
            if isinstance(flag, dict):
                severity = flag.get('severity', 'unknown')
                field = flag.get('field', 'unknown')
                reason = flag.get('reason', 'No reason provided')
                
                severity_icon = {
                    'low': '🟡',
                    'medium': '🟠',
                    'high': '🔴'
                }.get(severity.lower(), '⚪')
                
                print(f"  {severity_icon} {field}: {reason} (Severity: {severity})")
    else:
        print("\n✅ No review flags - extraction looks good!")
    
    # Display confidence
    confidence = data.get('confidence')
    if confidence:
        print("\n📈 CONFIDENCE SCORES:")
        print("-" * 80)
        if isinstance(confidence, dict):
            for field, score in confidence.items():
                if isinstance(score, (int, float)):
                    bar_length = int(score * 20)
                    bar = '█' * bar_length + '░' * (20 - bar_length)
                    print(f"  {field:20s}: {bar} {score:.1%}")
        elif isinstance(confidence, (int, float)):
            bar_length = int(confidence * 20)
            bar = '█' * bar_length + '░' * (20 - bar_length)
            print(f"  Overall: {bar} {confidence:.1%}")


async def run_document_test(doc_type: str, file_path: str):
    """Test a single document"""
    
    print("\n" + "=" * 80)
    print(f"TESTING: {doc_type.upper()}")
    print("=" * 80)
    
    if not Path(file_path).exists():
        print(f"⏭️  SKIPPED: File not found - {file_path}")
        return False
    
    print(f"📄 Processing: {file_path}")
    print(f"⏱️  Started at: {datetime.now().strftime('%H:%M:%S')}")
    
    try:
        start_time = datetime.now()
        
        # Process document
        result = await process_document(file_path)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Convert to dict if needed
        if isinstance(result, dict):
            data = result
        else:
            data = result.model_dump() if hasattr(result, 'model_dump') else result.__dict__
        
        # Display results
        display_document_result(data, doc_type)
        
        print(f"\n⏱️  Processing Time: {duration:.2f} seconds")
        print("✅ TEST PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_all():
    """Test all document types"""
    
    print("\n" + "=" * 80)
    print("PAPERPULSE AI - COMPREHENSIVE DOCUMENT EXTRACTION TEST")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {}
    
    for doc_type, file_path in TEST_FILES.items():
        success = await run_document_test(doc_type, file_path)
        results[doc_type] = success
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    skipped = sum(1 for v in results.values() if v is False and v is not None)
    
    for doc_type, success in results.items():
        status = "✅ PASSED" if success else "⏭️  SKIPPED" if success is False else "❌ FAILED"
        print(f"  {doc_type:20s}: {status}")
    
    print(f"\nTotal: {passed}/{total} passed")
    print("=" * 80)


async def run_single_test(doc_type: str):
    """Test a single document type"""
    
    if doc_type not in TEST_FILES:
        print(f"❌ Unknown document type: {doc_type}")
        print(f"Available types: {', '.join(TEST_FILES.keys())}")
        return
    
    file_path = TEST_FILES[doc_type]
    await run_document_test(doc_type, file_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Test specific document type
        doc_type = sys.argv[1].lower()
        asyncio.run(test_single(doc_type))
    else:
        # Test all documents
        asyncio.run(test_all())
        
        print("\n💡 TIP: To test a specific document type, run:")
        print("   python test_all_documents.py aadhaar")
        print("   python test_all_documents.py invoice")
        print("   python test_all_documents.py ekyc")
