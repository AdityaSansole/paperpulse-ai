# Document Intelligence System

AI-powered document extraction system for Indian documents with support for multiple document types including Aadhaar, PAN, Voter ID, Driving License, Passport, and Invoices.

## Features

- **Multi-Document Support**: Aadhaar, PAN, Voter ID, Driving License, Passport, Invoice, eKYC
- **Hybrid Extraction**: Gemini AI + OCR fallback for maximum accuracy
- **Async Processing**: Concurrent document processing with worker pool
- **Smart Caching**: File hash-based caching to avoid reprocessing
- **Type-Safe Schemas**: Pydantic models with validation and review flags
- **REST API**: FastAPI-based API with async task management
- **Web Interface**: Simple frontend for document upload and results

## Architecture

```
┌─────────────┐
│   Frontend  │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────┐
│              FastAPI Server                  │
│  ┌────────────┐  ┌──────────────┐           │
│  │   Upload   │  │  Task Queue  │           │
│  │   Router   │  │              │           │
│  └─────┬──────┘  └──────┬───────┘           │
│        │                │                    │
│  ┌─────▼────────────────▼─────┐             │
│  │     Worker Pool              │            │
│  │  (Concurrent Processing)     │            │
│  └─────┬────────────────────────┘            │
│        │                                     │
│  ┌─────▼──────────┐  ┌──────────────┐       │
│  │  LLM Service   │  │ OCR Service  │       │
│  │  (Gemini/Groq) │  │ (Tesseract)  │       │
│  └────────────────┘  └──────────────┘       │
│                                              │
│  ┌──────────────┐  ┌──────────────┐         │
│  │Cache Manager │  │ Normalizer   │         │
│  └──────────────┘  └──────────────┘         │
└──────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.11+
- Tesseract OCR
- Google Gemini API key or Groq API key

### Setup

1. Clone the repository
```bash
git clone <repository-url>
cd project-text-extraction
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Install Tesseract OCR
- **Windows**: Download from https://github.com/UB-Mannheim/tesseract/wiki
- **Linux**: `sudo apt-get install tesseract-ocr`
- **Mac**: `brew install tesseract`

4. Configure environment variables
```bash
cp .env.example .env
# Edit .env with your API keys
```

Required environment variables:
```
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key (optional)
AI_PROVIDER=gemini
OCR_ENGINE=tesseract
```

## Usage

### Start the Server

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Access the Application

- **Web Interface**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### API Endpoints

#### Upload Document
```bash
POST /api/upload
Content-Type: multipart/form-data

Response:
{
  "task_id": "abc123",
  "status": "pending",
  "message": "Task created successfully"
}
```

#### Check Task Status
```bash
GET /api/tasks/status/{task_id}

Response:
{
  "task_id": "abc123",
  "filename": "document.jpg",
  "status": "completed",
  "progress": 100.0
}
```

#### Get Task Result
```bash
GET /api/tasks/result/{task_id}

Response:
{
  "task_id": "abc123",
  "filename": "document.jpg",
  "status": "completed",
  "extracted_data": {
    "document_type": "aadhaar",
    "name": "John Doe",
    "aadhaar_number_masked": "XXXX XXXX 1234",
    ...
  }
}
```

## Document Types

### Supported Documents

1. **Aadhaar Card**
   - Name, DOB, Gender, Address
   - Masked Aadhaar number
   - Front/Back side detection

2. **PAN Card**
   - Name, Father's name, DOB
   - PAN number

3. **Voter ID**
   - Name, Father's name, DOB, Gender
   - Voter ID number, Address
   - Polling station details

4. **Driving License**
   - Name, DOB, Address
   - License number, Issue/Expiry dates
   - Vehicle classes

5. **Passport**
   - Name, DOB, Gender, Nationality
   - Passport number, Issue/Expiry dates
   - MRZ parsing

6. **Invoice**
   - Vendor/Buyer details
   - Invoice number, date
   - Line items, amounts

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_PROVIDER` | `gemini` | AI provider (gemini/groq) |
| `GEMINI_API_KEY` | - | Google Gemini API key |
| `GROQ_API_KEY` | - | Groq API key (optional) |
| `OCR_ENGINE` | `tesseract` | OCR engine |
| `OCR_LANG` | `eng+hin` | OCR languages |
| `UPLOAD_DIR` | `uploads` | Upload directory |
| `OUTPUT_DIR` | `outputs` | Output directory |
| `CACHE_DIR` | `cache` | Cache directory |

### Worker Pool

Configure concurrent processing:
- Default: 8 workers
- Adjust based on CPU cores and memory

### Cache

- File hash-based caching
- Automatic cache invalidation
- Persistent storage in JSON format

## Development

### Project Structure

```
project/
├── main.py                 # FastAPI application
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables
├── models/                 # Pydantic schemas
│   ├── schemas.py          # Document schemas
│   └── task_schemas.py     # Task schemas
├── routes/                 # API routes
│   ├── upload.py           # Upload endpoint
│   ├── tasks.py            # Task management
│   └── batch.py            # Batch processing
├── services/               # Business logic
│   ├── document_service.py # Main processing
│   ├── llm_service.py      # AI extraction
│   ├── ocr_service.py      # OCR processing
│   ├── cache_manager.py    # Caching
│   ├── task_queue.py       # Task management
│   └── worker_pool.py      # Concurrent processing
├── frontend/               # Web interface
│   └── index.html          # UI
├── tests/                  # Test suite
└── logs/                   # Application logs
```

### Running Tests

```bash
python -m pytest tests/
```

## Performance

- **Processing Time**: 5-10 seconds per document
- **Cache Hit Rate**: >50% for repeated documents
- **Concurrent Processing**: Up to 8 documents simultaneously
- **Accuracy**: >90% for clear images

## Security

- Automatic Aadhaar number masking
- No storage of sensitive data in logs
- File hash-based deduplication
- Input validation and sanitization

## Deploying a Demo on Render

The repository includes a Dockerfile and `render.yaml` Blueprint for deploying
the combined React frontend and FastAPI backend. The container installs
Tesseract with English and Hindi language data and builds the frontend before
starting the API server.

1. Push the reviewed project to a GitHub repository. Keep `.env` and real
   documents out of Git; provide API keys only through the hosting dashboard.
2. In Render, create a new Blueprint and select the GitHub repository.
3. Set the requested `GROQ_API_KEY` secret in Render, then deploy the service.
4. Open the generated `onrender.com` URL and check `/health`.

The Blueprint provisions a persistent disk, which may incur hosting charges.
Treat the deployed service as a demo with non-sensitive sample documents
only: the upload API is not authenticated or rate-limited. Add access control,
abuse protection, and a privacy/data-retention policy before accepting real
identity documents or opening the service to general public use.

## License

MIT License

## Support

For issues and questions, please open an issue on the repository.
