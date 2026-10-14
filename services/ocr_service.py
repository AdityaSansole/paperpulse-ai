import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OCR_ENGINE = os.getenv("OCR_ENGINE", "tesseract").lower()
OCR_LANG = os.getenv("OCR_LANG", "eng+hin")  # Support Hindi for Aadhaar cards
OCR_PREPROCESS = os.getenv("OCR_PREPROCESS", "grayscale").lower()  # Preprocessing mode

# Lazy imports for heavy dependencies
_pytesseract = None
_pdfplumber = None
_pdfium = None
_Image = None
_paddleocr = None
_cv2 = None
_np = None
_ftfy = None


def _get_cv2():
    """Lazy-load OpenCV only when needed."""
    global _cv2
    if _cv2 is None:
        try:
            import cv2
            _cv2 = cv2
        except ImportError:
            logger.warning("OpenCV not installed. Install with: pip install opencv-python")
            _cv2 = None
    return _cv2


def _get_numpy():
    """Lazy-load numpy only when needed."""
    global _np
    if _np is None:
        try:
            import numpy as np
            _np = np
        except ImportError:
            logger.warning("NumPy not installed. Install with: pip install numpy")
            _np = None
    return _np


def _get_ftfy():
    """Lazy-load ftfy only when needed for text cleaning."""
    global _ftfy
    if _ftfy is None:
        try:
            import ftfy
            _ftfy = ftfy
        except ImportError:
            logger.warning("ftfy not installed. Install with: pip install ftfy")
            _ftfy = None
    return _ftfy


def _get_pytesseract():
    """Lazy-load pytesseract only when needed."""
    global _pytesseract
    if _pytesseract is None:
        import pytesseract as _pt
        tesseract_path = os.getenv("TESSERACT_PATH")
        if tesseract_path:
            _pt.pytesseract.tesseract_cmd = tesseract_path
        _pytesseract = _pt
    return _pytesseract


def _get_pil():
    """Lazy-load PIL modules only when needed."""
    global _Image
    if _Image is None:
        from PIL import Image
        _Image = Image
    return _Image, None, None


def _get_paddleocr():
    """Lazy-load PaddleOCR only when needed."""
    global _paddleocr
    if _paddleocr is None:
        try:
            from paddleocr import PaddleOCR
            # Initialize with English language, use angle classification
            _paddleocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
            logger.info("PaddleOCR initialized successfully")
        except ImportError:
            logger.warning("PaddleOCR not installed. Install with: pip install paddleocr")
            _paddleocr = None
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            _paddleocr = None
    return _paddleocr


def _get_pdfplumber():
    """Lazy-load pdfplumber only when needed."""
    global _pdfplumber
    if _pdfplumber is None:
        import pdfplumber
        _pdfplumber = pdfplumber
    return _pdfplumber


def _get_pdfium():
    """Lazy-load pypdfium2 only when needed."""
    global _pdfium
    if _pdfium is None:
        import pypdfium2 as pdfium
        _pdfium = pdfium
    return _pdfium


def _process_gray_array(gray, method: str):
    """Apply the selected preprocessing method to a grayscale array."""
    cv2 = _get_cv2()
    Image, _, _ = _get_pil()

    if cv2 is None:
        return Image.fromarray(gray)

    if method in {"gray", "grayscale", "none"}:
        processed = gray
    elif method == "thresh":
        processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    elif method == "adaptive":
        processed = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            2,
        )
    elif method == "blur":
        processed = cv2.medianBlur(gray, 3)
    elif method == "bilateral":
        processed = cv2.bilateralFilter(gray, 11, 17, 17)
    elif method == "linear":
        processed = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR)
    elif method == "cubic":
        processed = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    else:
        processed = gray

    return Image.fromarray(processed)


def preprocess_image(image_path: str, method: str = "grayscale") -> any:
    """
    Preprocessing methods matched to image problems.
    Less aggressive than the previous sharpening-heavy pipeline.
    """
    cv2 = _get_cv2()
    Image, _, _ = _get_pil()

    if cv2 is None:
        return Image.open(image_path).convert("L")

    img = cv2.imread(image_path)
    if img is None:
        logger.error(f"Failed to load image: {image_path}")
        return Image.open(image_path).convert("L")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return _process_gray_array(gray, method)


def pick_best_preprocessing(image_path: str) -> tuple[str, any]:
    """
    Pick a conservative preprocessing strategy.

    First pass aims to preserve text shape rather than aggressively binarize it.
    For Aadhaar-style testing, this gives us a cleaner baseline:
    - small images: upscale only
    - everything else: plain grayscale
    """
    cv2 = _get_cv2()
    np = _get_numpy()

    if cv2 is None or np is None:
        return OCR_PREPROCESS, preprocess_image(image_path, OCR_PREPROCESS)

    img = cv2.imread(image_path)
    if img is None:
        return OCR_PREPROCESS, preprocess_image(image_path, OCR_PREPROCESS)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    if width < 800 or height < 500:
        method = "cubic"
    else:
        method = "grayscale"

    return method, _process_gray_array(gray, method)


def preprocess_pil_image(image) -> any:
    """Apply the same conservative preprocessing strategy to a PIL image."""
    cv2 = _get_cv2()
    np = _get_numpy()

    if cv2 is None or np is None:
        return image.convert("L")

    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    height, width = gray.shape

    if width < 800 or height < 500:
        method = "cubic"
    else:
        method = "grayscale"

    return _process_gray_array(gray, method)


def clean_ocr_text(text: str) -> str:
    """
    Clean OCR text using ftfy to fix encoding issues and mojibake.
    Inspired by Aadhaar extraction code.
    """
    ftfy = _get_ftfy()
    if ftfy is None:
        return text
    
    try:
        # Fix text encoding issues
        text = ftfy.fix_text(text)
        text = ftfy.fix_encoding(text)
        return text
    except Exception as exc:
        logger.warning(f"ftfy text cleaning failed: {exc}")
        return text


def extract_text_from_image(file_path: str) -> tuple[str, float]:
    """
    Extract text from an image file with confidence score.
    Supports multi-frame images (e.g., multi-page TIFF) by iterating all frames.
    
    Uses advanced preprocessing and Hindi language support for Aadhaar cards.
    
    Returns:
        (text, confidence): Extracted text and average confidence score (0-100)
    """
    try:
        Image, _, _ = _get_pil()
        pytesseract = _get_pytesseract()
        
        # Try diagnostic preprocessing first
        try:
            selected_method, processed = pick_best_preprocessing(file_path)
            
            # Extract text with Hindi support
            data = pytesseract.image_to_data(processed, lang=OCR_LANG, output_type=pytesseract.Output.DICT)
            text = pytesseract.image_to_string(processed, lang=OCR_LANG).strip()
            
            # Clean text with ftfy
            text = clean_ocr_text(text)
            
            if text:
                # Calculate average confidence
                page_confidences = [
                    float(conf) for conf in data['conf'] 
                    if conf != '-1' and str(conf).replace('.', '').isdigit()
                ]
                avg_confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.0
                
                logger.info(f"OCR extracted text with {avg_confidence:.1f}% confidence (lang={OCR_LANG}, preprocess={selected_method})")
                return text, avg_confidence
        
        except Exception as opencv_exc:
            logger.warning(f"OpenCV preprocessing failed: {opencv_exc}, falling back to PIL")
        
        # Fallback to original PIL-based preprocessing
        image = Image.open(file_path)
        pages: list[str] = []
        confidences: list[float] = []

        frame_index = 0
        while True:
            try:
                image.seek(frame_index)
            except EOFError:
                break

            frame = image.copy().convert("RGB")
            processed = preprocess_pil_image(frame)
            
            # Get text and confidence data with Hindi support
            data = pytesseract.image_to_data(processed, lang=OCR_LANG, output_type=pytesseract.Output.DICT)
            text = pytesseract.image_to_string(processed, lang=OCR_LANG).strip()
            
            # Clean text with ftfy
            text = clean_ocr_text(text)
            
            if text:
                pages.append(text)
                
                # Calculate average confidence for this page
                page_confidences = [
                    float(conf) for conf in data['conf'] 
                    if conf != '-1' and str(conf).replace('.', '').isdigit()
                ]
                if page_confidences:
                    confidences.append(sum(page_confidences) / len(page_confidences))

            frame_index += 1

        if not pages:
            logger.warning("No text extracted from image: %s", file_path)
            return "", 0.0

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return "\n".join(pages).strip(), avg_confidence

    except Exception as exc:
        logger.error("Error extracting text from image %s: %s", file_path, str(exc))
        return f"Error extracting text from image: {str(exc)}", 0.0


def extract_text_from_scanned_pdf(file_path: str) -> tuple[str, float]:
    """
    Render each PDF page as an image and run OCR on it.
    Uses advanced preprocessing and Hindi language support.
    
    Returns:
        (text, confidence): Extracted text and average confidence score (0-100)
    """
    try:
        Image, _, _ = _get_pil()
        pytesseract = _get_pytesseract()
        pdfium = _get_pdfium()
        
        pdf = pdfium.PdfDocument(file_path)
        ocr_pages: list[str] = []
        confidences: list[float] = []

        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = page.render(scale=2)
            pil_image = bitmap.to_pil()
            pil_image = preprocess_pil_image(pil_image)
            
            # Get text and confidence with Hindi support
            data = pytesseract.image_to_data(pil_image, lang=OCR_LANG, output_type=pytesseract.Output.DICT)
            page_text = pytesseract.image_to_string(pil_image, lang=OCR_LANG).strip()
            
            # Clean text with ftfy
            page_text = clean_ocr_text(page_text)
            
            if page_text:
                ocr_pages.append(page_text)
                
                # Calculate average confidence for this page
                page_confidences = [
                    float(conf) for conf in data['conf'] 
                    if conf != '-1' and str(conf).replace('.', '').isdigit()
                ]
                if page_confidences:
                    confidences.append(sum(page_confidences) / len(page_confidences))

        if not ocr_pages:
            logger.warning("No text extracted from scanned PDF: %s", file_path)
            return "", 0.0

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return "\n".join(ocr_pages).strip(), avg_confidence

    except Exception as exc:
        logger.error("Error extracting text from scanned PDF %s: %s", file_path, str(exc))
        return f"Error extracting text from scanned PDF: {str(exc)}", 0.0


# ── PaddleOCR Functions ───────────────────────────────────────────────────────


def extract_text_from_image_paddleocr(file_path: str) -> tuple[str, float]:
    """
    Extract text from an image using PaddleOCR.
    Better for handwritten text and Asian languages.
    
    Returns:
        (text, confidence): Extracted text and average confidence score (0-100)
    """
    try:
        paddleocr = _get_paddleocr()
        if paddleocr is None:
            logger.warning("PaddleOCR not available, falling back to Tesseract")
            return extract_text_from_image(file_path)
        
        # Run OCR
        result = paddleocr.ocr(file_path, cls=True)
        
        if not result or not result[0]:
            return "", 0.0
        
        # Extract text and confidence scores
        lines = []
        confidences = []
        
        for line in result[0]:
            text = line[1][0]  # Text content
            confidence = line[1][1]  # Confidence score (0-1)
            lines.append(text)
            confidences.append(confidence)
        
        # Calculate average confidence
        avg_confidence = (sum(confidences) / len(confidences) * 100) if confidences else 0.0
        
        # Join lines with newlines
        full_text = "\n".join(lines)
        
        logger.info(f"PaddleOCR extracted {len(lines)} lines with {avg_confidence:.1f}% confidence")
        return full_text, avg_confidence
        
    except Exception as exc:
        logger.error(f"PaddleOCR error on {file_path}: {exc}")
        logger.info("Falling back to Tesseract")
        return extract_text_from_image(file_path)


def extract_text_from_pdf_paddleocr(file_path: str) -> tuple[str, float]:
    """
    Extract text from PDF using PaddleOCR.
    Converts PDF pages to images first, then runs OCR.
    
    Returns:
        (text, confidence): Extracted text and average confidence score (0-100)
    """
    try:
        paddleocr = _get_paddleocr()
        if paddleocr is None:
            logger.warning("PaddleOCR not available, falling back to Tesseract")
            return extract_text_from_scanned_pdf(file_path)
        
        pdfium = _get_pdfium()
        pdf = pdfium.PdfDocument(file_path)
        
        all_text = []
        all_confidences = []
        
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            # Render page to image
            pil_image = page.render(scale=2.0).to_pil()
            
            # Convert PIL image to numpy array for PaddleOCR
            import numpy as np
            img_array = np.array(pil_image)
            
            # Run OCR on the image
            result = paddleocr.ocr(img_array, cls=True)
            
            if result and result[0]:
                page_lines = []
                page_confidences = []
                
                for line in result[0]:
                    text = line[1][0]
                    confidence = line[1][1]
                    page_lines.append(text)
                    page_confidences.append(confidence)
                
                all_text.extend(page_lines)
                all_confidences.extend(page_confidences)
        
        # Calculate average confidence
        avg_confidence = (sum(all_confidences) / len(all_confidences) * 100) if all_confidences else 0.0
        
        full_text = "\n".join(all_text)
        logger.info(f"PaddleOCR extracted {len(all_text)} lines from {len(pdf)} pages with {avg_confidence:.1f}% confidence")
        
        return full_text, avg_confidence
        
    except Exception as exc:
        logger.error(f"PaddleOCR PDF error on {file_path}: {exc}")
        logger.info("Falling back to Tesseract")
        return extract_text_from_scanned_pdf(file_path)


# ── Main Extraction Functions ─────────────────────────────────────────────────


def extract_text_from_pdf(file_path: str) -> tuple[str, float]:
    """
    Try native text extraction first (pdfplumber).
    Fall back to OCR if the PDF has no embedded text (scanned document).
    
    Returns:
        (text, confidence): Extracted text and confidence score (0-100)
                           100.0 for native text, OCR confidence for scanned PDFs
    """
    try:
        pdfplumber = _get_pdfplumber()
        full_text: list[str] = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text.append(page_text)

        text = "\n".join(full_text).strip()
        if text:
            # Native text extraction - perfect confidence
            return text, 100.0

        logger.info("No native text in PDF %s, falling back to OCR.", file_path)
        return extract_text_from_scanned_pdf(file_path)

    except Exception as exc:
        logger.error("Error extracting text from PDF %s: %s", file_path, str(exc))
        return f"Error extracting text from PDF: {str(exc)}", 0.0


def extract_text(file_path: str) -> tuple[str, float]:
    """
    Dispatch to the correct extractor based on file extension and OCR engine.
    
    OCR Engine is configured via OCR_ENGINE environment variable:
    - "tesseract" (default): Fast, good for printed text
    - "paddleocr": Better for handwritten text and Asian languages
    
    Returns:
        (text, confidence): Extracted text and OCR confidence score (0-100)
    """
    extension = os.path.splitext(file_path)[1].lower()
    
    # Log which engine is being used
    logger.info(f"Using OCR engine: {OCR_ENGINE}")

    if extension == ".pdf":
        # For PDFs, try native text extraction first
        if OCR_ENGINE == "paddleocr":
            # Try native text first, fall back to PaddleOCR if needed
            try:
                pdfplumber = _get_pdfplumber()
                full_text: list[str] = []
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            full_text.append(page_text)
                text = "\n".join(full_text).strip()
                if text:
                    return text, 100.0
                # No native text, use PaddleOCR
                logger.info("No native text in PDF, using PaddleOCR")
                return extract_text_from_pdf_paddleocr(file_path)
            except Exception:
                return extract_text_from_pdf_paddleocr(file_path)
        else:
            return extract_text_from_pdf(file_path)
            
    elif extension in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}:
        if OCR_ENGINE == "paddleocr":
            return extract_text_from_image_paddleocr(file_path)
        else:
            return extract_text_from_image(file_path)
    else:
        return "Unsupported file type.", 0.0
