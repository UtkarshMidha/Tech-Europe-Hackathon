# Cortea Audit Manager

> Follow the money. Find the fraud. Prove it.

Cortea Audit Manager is an evidence-first audit investigation application built for the Cortea challenge. It ingests mixed-format company dossiers, reconciles financial and operational records, ranks supportable exceptions, and lets auditors verify every claim against the exact source file, page, sheet, row, cell, slide, paragraph, or extracted image passage.

The system assists professional judgment; it does not autonomously issue a fraud verdict. Deterministic audit procedures establish the financial facts. OpenAI is used only where semantic interpretation adds value, and AI-generated claims must pass an evidence firewall before appearing as findings.

## Key capabilities

- Upload a ZIP or an entire folder; the engagement is named after the uploaded container.
- Recursively unpack nested ZIP archives up to three levels.
- Read CSV, TXT, XML, DTD, JSON, Markdown, XLS/XLSX, DOC/DOCX, PPT/PPTX, PDF, PNG, JPG/JPEG, and WebP files.
- Convert legacy Microsoft Office documents through LibreOffice inside Docker.
- Discover renamed and unfamiliar table schemas with confidence-gated AI mapping.
- Extract evidence from scanned PDFs, standalone images, and images embedded in Office files.
- Run explicit audit tests across ledgers, bank records, invoices, purchase orders, receipts, permissions, vendor masters, and financial statements.
- Show a ranked Precision Queue while holding contradictory or weak signals outside the accusation queue.
- Open evidence in an in-app table with the previous, relevant, and next source rows.
- Trace each fact to its original locator and SHA-256 digest.
- Search the entire dossier and ask evidence-grounded questions in English or German.
- Record auditor confirmation or dismissal, with a mandatory reason for dismissal.
- Export a printable evidence report.

## Architecture

```text
ZIP / folder upload
        |
        v
Safe extraction and format normalization
        |
        +--> Native parsers and deterministic schema recognition
        +--> AI schema mapping for unfamiliar tables (optional)
        +--> Vision extraction for scans and embedded images (optional)
        |
        v
Canonical audit tables and source locators
        |
        v
Deterministic reconciliations and explicit audit tests
        |
        v
Evidence and counter-evidence validation
        |
        +--> Optional AI investigation and grounded Q&A
        |
        v
Ranked findings, materiality bridge, evidence viewer, report
```

The application is a single deployable Docker service. Vite builds the React frontend, FastAPI serves the API and compiled frontend, and analysis results remain in process memory for the hackathon demo.

## Technology stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React | Auditor workspace, findings, evidence tables, review actions |
| Build tooling | Vite | Development server and optimized production bundle |
| Backend | Python 3.12, FastAPI | Upload API, analysis orchestration, evidence and report endpoints |
| ASGI server | Uvicorn | Production HTTP server |
| Validation | Pydantic | Request validation and bounded input models |
| Spreadsheets | openpyxl | XLSX sheets, formulas, cells, and structured row extraction |
| PDF | pypdf | PDF text and page extraction |
| Legacy Office | LibreOffice | Headless conversion of DOC, PPT, and XLS files |
| AI | OpenAI Python SDK | Adaptive schema mapping, image understanding, investigation, grounded Q&A |
| Testing | pytest, FastAPI TestClient, Node test runner | Backend integration and frontend calculation checks |
| Packaging | Docker multi-stage build | Reproducible frontend and backend deployment |
| Hosting | Render blueprint | Optional Frankfurt-region demo deployment |

Exact dependency versions are defined in `requirements.txt`; frontend dependencies and scripts are defined in `frontend/package.json`.

## Repository structure

```text
backend/
  app.py          FastAPI routes, upload controls, run lifecycle, reports
  ingest.py       document parsing and legacy Office normalization
  adaptive.py     confidence-gated schema discovery and canonical mapping
  audit.py        deterministic audit procedures and evidence construction
  synthesis.py    OpenAI vision, investigation, and grounded answers
  tests/          backend and integration tests
frontend/
  src/App.jsx     auditor workflow and interface components
  src/model.js    presentation calculations and data normalization
  src/styles.css  responsive visual system
Dockerfile        production multi-stage image
render.yaml       optional Render deployment blueprint
.env.example      supported environment variables
```

`TECHNICAL_DOCUMENTATION.md` contains a deeper implementation walkthrough.

## Prerequisites

Recommended:

- Docker Desktop with Docker Engine running
- At least 2 GB free memory for the container
- An OpenAI API key only if AI enhancement is required

For non-Docker development:

- Python 3.12
- Node.js 22 and npm
- LibreOffice for legacy DOC/PPT/XLS conversion

## Quick start with Docker

From the repository root:

```bash
docker build -t cortea-audit-manager .
docker run --rm --name cortea-audit-manager -p 8000:8000 cortea-audit-manager
```

Open <http://localhost:8000>. Verify the service at <http://localhost:8000/api/health>.

### Enable OpenAI features

Copy the environment template and insert the key locally. Never commit `.env`.

PowerShell:

```powershell
Copy-Item .env.example .env
# Edit .env, then run:
docker run --rm --name cortea-audit-manager --env-file .env -p 8000:8000 cortea-audit-manager
```

macOS/Linux:

```bash
cp .env.example .env
# Edit .env, then run:
docker run --rm --name cortea-audit-manager --env-file .env -p 8000:8000 cortea-audit-manager
```

Environment variables:

| Variable | Required | Default | Description |
|---|---:|---|---|
| `OPENAI_API_KEY` | No | empty | Enables adaptive mapping, vision, AI investigation, and grounded answers |
| `OPENAI_MODEL` | No | `gpt-5.6` | OpenAI model used by optional AI passes |
| `DEMO_TOKEN` | No | empty | Shared hackathon demo gate; empty disables it locally |
| `PORT` | No | `8000` | HTTP port inside the container |

When `DEMO_TOKEN` is set, send it as `?token=<value>` or the `x-demo-token` header for every API request except `/api/health`.

## Local development

Create and activate a Python virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Build the frontend and run the integrated service:

```powershell
Set-Location frontend
npm install
npm run build
Set-Location ..
uvicorn backend.app:app --reload --port 8000
```

For live frontend development, run `npm run dev` from `frontend/`. The production Docker path remains the authoritative integrated build.

## Testing

Backend:

```bash
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

The backend suite covers API behavior, upload controls, German and English money parsing, adaptive schema handling, fraud procedures, evidence context, reviews, and engagement naming. The frontend test checks financial normalization and the profit bridge.

## Using the application

1. Open the application and choose **Open ZIP** or **Open folder**.
2. Wait for ingestion, normalization, reconciliation, and detection to complete.
3. Select a promoted exception from the Precision Queue.
4. Read the plain-language case summary and inspect the evidence chain.
5. Click any evidence item to view the relevant source row plus surrounding context.
6. Use **Sources** to inspect coverage and search the complete dossier.
7. Use **Materiality** to trace the effect on reported profit where a sourced trial balance exists.
8. Ask the ledger a question; answers return linked evidence rather than unsupported prose.
9. Confirm or dismiss the finding and record the auditor's judgment.
10. Open the printable evidence report for the final audit trail.

Upload limits and protections:

- Maximum expanded dossier size: 600 MB
- Maximum files: 100
- Maximum nested ZIP depth: 3
- Path traversal and unsupported extensions are rejected
- macOS metadata files are ignored
- filenames suggesting answer keys or ground truth are rejected

## How fraud cases are identified

The core engine in `backend/audit.py` runs explicit, reproducible audit procedures rather than asking an LLM to label the dossier as fraudulent. Procedures include:

- bank-to-ledger reconciliation;
- invoice, order, receipt, ledger, and payment matching;
- duplicate invoice and duplicate payment detection;
- supplier overpayment and unexplained payment variance;
- missing goods-receipt or service-delivery evidence;
- vendor master changes immediately preceding cash movement;
- segregation-of-duties conflicts across creation, approval, posting, and payment rights;
- approval-threshold splitting;
- rapid settlement and unusual timing;
- period cut-off and premature revenue;
- asset versus expense classification;
- trial-balance integrity and profit adjustment lineage;
- source hash and custody verification.

Each promoted finding contains:

- a factual summary;
- severity and confidence;
- sourced monetary amounts;
- evidence IDs and counter-evidence IDs;
- source locators and excerpts;
- explicit caveats;
- the professional judgment still required.

Weak, contradictory, or incomplete signals are held back. This reduces false positives and prevents innocent discrepancies from being presented as accusations.

## OpenAI integration and safeguards

OpenAI is optional. Without an API key, native extraction, deterministic reconciliation, evidence links, corpus search, review actions, and rule-based question routing remain available.

With a key, OpenAI supports four bounded tasks:

1. **Adaptive schema mapping:** maps unfamiliar column names to canonical audit fields.
2. **Vision extraction:** reads scans and images that native text parsers cannot interpret.
3. **Investigation:** proposes additional cross-document hypotheses from focused excerpts.
4. **Ask the Ledger:** produces a concise answer grounded in the current run's evidence.

AI output is not accepted merely because the model is confident. A claim firewall requires traceable source evidence, rejects unsourced amounts, retains original locators and hashes, and requires multiple source files before an AI-generated lead can become a promoted finding. Requests use `store=false`.

## API reference

FastAPI also exposes interactive OpenAPI documentation at `/docs` and the schema at `/openapi.json` while the service is running.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service health and sample availability |
| `GET` | `/api/demo?ai=false` | Load the bundled sample run; optionally request AI enhancement |
| `POST` | `/api/runs?ai=false` | Upload one ZIP or multiple folder files and create an analysis run |
| `GET` | `/api/runs/{run_id}` | Return the complete run, findings, evidence, manifest, and metrics |
| `GET` | `/api/runs/{run_id}/findings` | Return findings for a run |
| `POST` | `/api/runs/{run_id}/ai-review` | Run optional AI enhancement on an existing run |
| `GET` | `/api/runs/{run_id}/events` | Stream analysis stage events using server-sent events |
| `GET` | `/api/evidence/{evidence_id}?run_id={run_id}` | Return one evidence object |
| `GET` | `/api/runs/{run_id}/evidence/{evidence_id}/context` | Return surrounding source rows or document context |
| `GET` | `/api/runs/{run_id}/source/{source_path}` | Download or open an original uploaded source |
| `GET` | `/api/runs/{run_id}/search?q={query}` | Search the parsed dossier corpus |
| `POST` | `/api/runs/{run_id}/ask` | Ask an evidence-grounded question |
| `PATCH` | `/api/findings/{finding_id}/review` | Save confirmed, dismissed, or unreviewed status |
| `GET` | `/api/runs/{run_id}/report` | Render a printable HTML evidence report |

### Create a run

```bash
curl -X POST "http://localhost:8000/api/runs?ai=true" \
  -F "files=@Cortea_Track_Final_Dataset.zip"
```

Response:

```json
{
  "run_id": "a1b2c3d4e5f6",
  "status": "complete"
}
```

Folder uploads send each file under the same multipart field, preserving its relative path.

### Ask the Ledger

```bash
curl -X POST "http://localhost:8000/api/runs/a1b2c3d4e5f6/ask" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"Which supplier payments lack receipt evidence?\"}"
```

The response contains `answer`, `finding_id`, `evidence_ids`, and sourced `facts`.

### Record auditor judgment

```bash
curl -X PATCH "http://localhost:8000/api/findings/supplier-overpayment-1/review" \
  -H "Content-Type: application/json" \
  -d "{\"run_id\":\"a1b2c3d4e5f6\",\"status\":\"confirmed\",\"note\":\"Validated against bank confirmation.\"}"
```

Allowed statuses are `confirmed`, `dismissed`, and `unreviewed`. A dismissal requires a non-empty note.

## Data and evidence model

Every evidence object contains the original relative file path, evidence type, format-specific locator, label, excerpt, and SHA-256 digest. Tabular context returns nearby rows with the relevant row explicitly identified. A monetary figure is displayed only when it originates from a cited source or a reproducible calculation whose inputs are cited.

Run results are stored in memory and source files are stored in a temporary run directory. At most ten runs are retained; runs older than six hours are pruned, and all runs disappear when the process restarts.

## Deployment

The included `render.yaml` creates a Docker web service in Render's Frankfurt region and checks `/api/health`. Connect the repository as a Render Blueprint, set `OPENAI_API_KEY` if required, and retain the generated `DEMO_TOKEN`.

For any public deployment, add production identity, encrypted persistence, malware scanning, audit logging, retention controls, rate limits, and a security review. The included token is a shared demo gate, not a production authentication system.

## Security and known limitations

- Use synthetic hackathon data only unless organizational data-processing approval is in place.
- Uploaded unfamiliar table previews and images may be sent to OpenAI when AI is enabled.
- XLSX macros are not executed.
- Formula support is deliberately limited to the arithmetic and common aggregation formulas required by the audit procedures; unresolved formulas remain visible rather than being guessed.
- DOCX and PPTX use paragraph, table, slide, or embedded-object locators because these formats lack stable rendered page numbers.
- The app uses one process and in-memory state; it is designed for a hackathon demo, not concurrent production audit teams.
- Auditor confirmation remains mandatory. A detected anomaly is an investigation lead, not proof of intent.

## Jury evaluation guide

The fastest technical evaluation path is:

1. Upload the final ZIP and confirm that its filename becomes the engagement title.
2. Open the top Precision Queue finding and read the primary factual summary.
3. Click each evidence-chain item and verify the highlighted source row with adjacent context.
4. Open the consolidated evidence register and original documents.
5. Ask a new bilingual question and inspect its evidence citations.
6. Open Materiality and trace the profit bridge to sourced inputs.
7. Review Sources for format coverage, hashes, and mapping status.
8. Confirm or dismiss a finding, then open the printable report.
9. Run both test suites and inspect `/docs` for the live API contract.

The central design principle is simple: **the auditor never has to trust an unexplained conclusion—every claim can be reproduced from evidence.**

## License and challenge context

This repository is a hackathon prototype created for the Cortea audit challenge. Cortea branding remains the property of Cortea. No production assurance or audit opinion is provided by this software.
