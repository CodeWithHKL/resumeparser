# Resume Parser API

A FastAPI service that ranks resumes against a list of keywords/skills. It accepts many resumes in one request, extracts the text (PDF, DOCX, or images, with OCR fallback for scanned files), counts how many of the requested skills each resume contains, and streams the results back as they finish (NDJSON).

## Project layout

| Path | Purpose |
|---|---|
| `api_v2.py` | API v2: per-file timeouts, crash isolation, auth, limits. Recommended |
| `api_v1.py` | FastAPI server exposing `POST /rank-resumes` |
| `client_v2.py` | Improved client (v2): batching, CLI options, CSV export. Recommended |
| `client.py` | Terminal client: asks for keywords, uploads every resume in the configured folders, prints a live table and a Top 10 |
| `Resume/`, `INFORMATION-TECHNOLOGY/`, `ENGINEERING/` | Sample resume folders used by `client.py` |
| `requirements.txt` | Python dependencies |
| `requirements-dev.txt` | Test dependencies (pytest, httpx, reportlab) |
| `Dockerfile`, `docker-compose.yml` | Container setup (includes Tesseract and Poppler) |
| `tests/` | Unit and API tests |

## Requirements

- **Python 3.10 – 3.12** recommended (spaCy wheels may not be available for newer versions such as 3.14 yet)
- **Tesseract OCR** (for scanned PDFs and image resumes)
- **Poppler** (used by `pdf2image` to render PDF pages for OCR)

### 1. Install system dependencies

**Windows**
1. Tesseract: install from <https://github.com/UB-Mannheim/tesseract/wiki> (default path `C:\Program Files\Tesseract-OCR`) and add that folder to `PATH`.
2. Poppler: download from <https://github.com/oschwartz10612/poppler-windows/releases>, extract, and add its `Library\bin` folder to `PATH`.
3. Open a new terminal and verify: `tesseract --version` and `pdftoppm -h`.

**macOS**
```bash
brew install tesseract poppler
```

**Ubuntu / Debian**
```bash
sudo apt update && sudo apt install -y tesseract-ocr poppler-utils
```

### 2. Create a virtual environment and install packages

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## Running the server

```bash
python api_v1.py
```

or, with auto-reload during development:

```bash
uvicorn api_v1:app --reload --port 8000
```

The server listens on `127.0.0.1:8000` by default (override with the `HOST` and `PORT` environment variables; add authentication before exposing it on a network). Health check: `GET /health`. The API is at <http://127.0.0.1:8000>, with interactive docs at <http://127.0.0.1:8000/docs>.

> Note: the server uses `ProcessPoolExecutor`. On Windows, don't remove the `if __name__ == "__main__":` guard, and `--reload` may behave inconsistently with worker processes. Prefer `python api_v1.py` there.

### API v2 (recommended)

```bash
python api_v2.py
```

Same endpoint and response format as v1 (`/rank-resumes`, also available as `/v2/rank-resumes`), so `client.py` and `client_v2.py` work with either. What's new:

- **Per-file timeout:** a stuck or very slow file is killed after `FILE_TIMEOUT_SEC` and reported as an error; the worker is replaced and the rest of the batch continues.
- **Crash isolation:** a crashed worker fails only the file it was processing.
- **Disconnect handling:** if the client goes away, pending and running work is cancelled.
- **Bounded memory:** files are read lazily with a limited number in flight.
- **Limits:** `429` when too many requests run at once, `413` for oversized requests, max 50 skills of 64 characters each.
- **Content check:** a `.pdf` must really start like a PDF, and so on.
- **Optional API key:** set `API_KEY` on the server; clients send `X-API-Key` (`client_v2.py --api-key KEY` or the `RESUME_API_KEY` env var).
- **DOCX headers and footers** are now searched too.

| Environment variable | Default | Meaning |
|---|---|---|
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Bind address |
| `WORKERS` | half the CPUs | Parser processes |
| `FILE_TIMEOUT_SEC` | `60` | Per-file time limit |
| `MAX_CONCURRENT_REQUESTS` | `2` | Simultaneous requests before `429` |
| `MAX_REQUEST_MB` | `256` | Largest accepted request |
| `API_KEY` | unset | If set, required in `X-API-Key` |

PowerShell example: `$env:API_KEY="secret"; python api_v2.py`. The Docker image runs `api_v2.py`.

## Using the client

With the server running, in a second terminal:

```bash
python client.py
```

Enter comma-separated keywords (e.g. `python, sql, docker`). Results appear as each resume finishes, followed by a Top 10 ranking. Edit `resume_folders` at the top of `client.py` to point to your own folders.

### Client v2 (recommended)

```bash
python client_v2.py -k "python, sql, docker" -o ranking.csv
```

| Option | Meaning |
|---|---|
| `-k, --keywords` | Comma-separated keywords (prompted if omitted) |
| `-f, --folders` | One or more resume folders (default: the three sample folders) |
| `-r, --recursive` | Include subfolders |
| `-o, --output` | Write the full ranking, plus failures, to a CSV file |
| `--batch-size` | Files per request, default 50 (server max 300) |
| `--top` | How many ranked results to print, default 10 |
| `--url`, `--timeout`, `--no-pause` | Server URL, read timeout, don't wait for Enter at the end |

Compared with `client.py`, v2 shows files by relative path (so same-named files in different folders don't collide), skips files over 5 MB or of unsupported type with a warning, reports failed files separately, and handles a stopped server cleanly. It talks to the same API, so the server doesn't change. `client.py` is kept as v1.

## API reference

### `POST /rank-resumes`

`multipart/form-data` fields:

| Field | Type | Description |
|---|---|---|
| `skills` | string | Comma-separated skills, e.g. `python, sql, aws` |
| `files` | file(s), repeated | `.pdf`, `.docx`, `.jpg`, `.jpeg`, `.png` |

Limits: max **300 files** per request, max **5 MB** per file, first **10 pages** OCR'd for scanned PDFs. Skills are matched case-insensitively as whole words/phrases (multi-word skills and `c++`, `c#`, `node.js` work).

Response: `application/x-ndjson`, one JSON object per line, in completion order (not ranked):

```json
{"status": "success", "filename": "cv.pdf", "score": 2, "matched_skills": ["python", "sql"], "time_taken_sec": 0.412}
{"status": "error", "filename": "broken.pdf", "error": "..."}
```

Example with curl:

```bash
curl -N -X POST http://127.0.0.1:8000/rank-resumes \
  -F "skills=python,sql,docker" \
  -F "files=@Resume/My Resume.pdf" \
  -F "files=@Resume/Ikmal Resume.pdf"
```

Error codes: `400` too many files / no skills, `413` file over 5 MB.

## Running with Docker (optional)

The image bundles Tesseract and Poppler, so no system installs are needed.

```bash
docker compose up --build
```

The API is then at <http://127.0.0.1:8000> (published on localhost only). Run `python client.py` on your host as usual. Set `WORKERS` (default: half the CPU count) to control the number of parser processes.

Without compose:

```bash
docker build -t resume-parser .
docker run --rm -p 127.0.0.1:8000:8000 resume-parser
```

> The Docker setup has not been built or tested yet. The image runs `api_v2.py`.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests generate their own sample PDFs/DOCX files and mock OCR, so they need neither Tesseract/Poppler nor your real resumes.

## Troubleshooting

- **`TesseractNotFoundError`** – Tesseract isn't on `PATH`. Add it, or set `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`.
- **`PDFInfoNotInstalledError`** – Poppler isn't on `PATH`.
- **`Form data requires "python-multipart"`** – run `pip install -r requirements.txt`.
- **spaCy fails to install** – use Python 3.12 or lower.
- **Connection refused in the client** – make sure the server is running on port 8000.
