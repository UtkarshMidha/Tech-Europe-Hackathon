# Proofline Technical Documentation

## 1. System Purpose

Proofline is an evidence-first forensic audit application built for the Cortea hackathon challenge. It ingests a mixed-format company dossier, normalizes accounting data, executes deterministic audit procedures, optionally uses OpenAI for uncertain schemas and visual documents, and presents only findings that remain traceable to original evidence.

The core design principle is:

> No claim without evidence. No amount without a reproducible source.

Proofline is an auditor-assistance system, not an autonomous fraud verdict engine. It distinguishes observations, calculations, hypotheses, counter-evidence, professional judgement, and auditor conclusions.

## 2. High-Level Architecture

```text
Browser
  |
  | ZIP / folder / individual files
  v
FastAPI upload boundary
  |
  +-- path and archive validation
  +-- recursive ZIP expansion
  +-- SHA-256 source hashing
  +-- legacy Office conversion
  v
Format-neutral ingestion
  |
  +-- text passages
  +-- tables
  +-- Office embedded media
  +-- PDF pages
  v
Native schema discovery + optional OpenAI mapping/vision
  |
  v
Canonical accounting records
  |
  +-- reconciliation
  +-- deterministic fraud detectors
  +-- evidence and counter-evidence construction
  +-- calculation lineage
  v
Claim firewall + optional AI review
  |
  v
React forensic audit cockpit
```

The application is deployed as one Docker service. Vite builds the frontend during the first Docker stage. The production image contains Python, FastAPI, the compiled frontend, LibreOffice conversion utilities, and the sample dossier.

## 3. Technology Stack

### 3.1 Frontend

| Technology | Purpose |
|---|---|
| React | Component rendering, state management, interaction flow |
| React DOM | Browser mounting and rendering |
| Vite | Development server and optimized production build |
| JavaScript ES modules | Application and financial visualization logic |
| CSS | Responsive layout, typography, visual system, animation and accessibility |
| Native SVG/HTML | Evidence visualization and graphical elements without a chart dependency |

The frontend deliberately avoids a component framework. This keeps the runtime small and allows the forensic experience to use a highly customized editorial design.

Main frontend files:

- `frontend/src/App.jsx`: application state, API calls and all primary views.
- `frontend/src/styles.css`: visual system, responsive rules, animation and print behavior.
- `frontend/src/model.js`: numeric normalization, currency formatting and financial bridge calculations.
- `frontend/src/fallback.js`: static fallback payload displayed if the live demo API cannot load.
- `frontend/src/model.test.js`: runnable checks for financial presentation logic.

### 3.2 Backend

| Technology | Version | Purpose |
|---|---:|---|
| Python | 3.12 | Backend runtime |
| FastAPI | 0.139.2 | HTTP API and request validation |
| Uvicorn | 0.51.0 | ASGI production server |
| Pydantic | FastAPI/OpenAI dependency | Request and structured AI-output validation |
| OpenPyXL | 3.1.5 | XLSX reading and formula inspection |
| PyPDF | 6.14.2 | PDF page and embedded-text extraction |
| OpenAI Python SDK | 2.37.0 | Responses API, structured outputs and vision |
| Python Multipart | 0.0.32 | Multipart file uploads |
| HTTPX | 0.28.1 | API testing transport |
| Pytest | 8.4.2 | Backend regression suite |

Main backend modules:

- `backend/app.py`: API boundary, run lifecycle, upload security and frontend serving.
- `backend/ingest.py`: format-neutral Office normalization and legacy conversion.
- `backend/adaptive.py`: AI-assisted table-role and column mapping.
- `backend/audit.py`: deterministic accounting normalization, reconciliation, detection and evidence construction.
- `backend/synthesis.py`: optional evidence search, visual extraction and AI review firewall.

### 3.3 Infrastructure

| Technology | Purpose |
|---|---|
| Docker multi-stage build | Reproducible frontend build and backend runtime |
| Node 22 Alpine | Frontend build stage |
| Python 3.12 Slim | Production runtime stage |
| LibreOffice Writer/Calc/Impress | Legacy DOC, XLS and PPT conversion |
| Render Blueprint | Hosted Docker deployment in Frankfurt |

## 4. Upload and Trust Boundary

The upload endpoint is `POST /api/runs`.

Supported extensions:

```text
zip, txt, csv, xml, dtd, xlsx, xls, pdf,
doc, docx, ppt, pptx, md, json,
png, jpg, jpeg, webp
```

Security and resource limits:

- Maximum 100 uploaded or expanded files.
- Maximum 250 MB direct upload size.
- Maximum 250 MB expanded archive size.
- Nested ZIP depth is limited to three.
- Absolute paths and `..` traversal are rejected.
- Answer-like files containing `GROUND-TRUTH`, `SEALED`, or `ANSWER` are rejected.
- Expanded files stay inside a run-specific temporary directory.
- Source-serving endpoints resolve and verify the requested path remains inside the run root.
- Runs expire after six hours.
- A process retains at most ten runs and prunes the oldest when necessary.

Every accepted original is hashed with SHA-256. The hash travels with evidence and allows an auditor to confirm that a cited source has not changed.

## 5. Format-Neutral Ingestion

### 5.1 Native Structured Data

CSV and TXT ingestion uses delimiter detection across semicolon, comma, tab and pipe. GDPdU tables use their XML-declared columns and a deterministic semicolon delimiter to avoid confusing German decimal commas with separators.

XML GDPdU `index.xml` files define table URLs and column names. Proofline reads those definitions instead of depending on file names.

XLSX workbooks are read in read-only mode. The engine inspects all worksheets, searches initial rows for headers, and retains the original sheet and row number for each record.

### 5.2 Modern Office Documents

DOCX, PPTX and XLSX are ZIP-based OOXML containers. Proofline uses the Python standard library to inspect their XML parts and embedded media.

Extracted structures include:

- DOCX paragraphs and tables.
- PPTX slide text and tables.
- XLSX worksheets and cell values.
- PNG, JPEG and WebP media embedded in Office packages.

Text locators use paragraph, slide, table, worksheet or row references. Embedded-media locators retain the original Office file and embedded object name.

### 5.3 Legacy Office Documents

Binary DOC, PPT and XLS files are converted with headless LibreOffice:

```text
DOC -> DOCX
PPT -> PPTX
XLS -> XLSX
```

Converted files are internal derivatives. Evidence continues to cite and hash the original legacy file. This prevents conversion artifacts from replacing the chain-of-custody source.

### 5.4 PDF and Image Documents

PyPDF extracts native PDF text per page. If a PDF contains essentially no extractable text, the visual path sends the PDF to the configured multimodal OpenAI model.

Standalone PNG, JPEG and WebP documents and images embedded inside Office files enter the same visual path. The model returns structured passages containing:

- one-based page number;
- passage type;
- extracted visible text;
- low, medium or high confidence.

Low-confidence passages and impossible page references are rejected.

### 5.5 Markdown, JSON and General XML

Markdown pipe tables are normalized into rows and columns. JSON arrays of objects and object properties containing record arrays become tables. General XML groups repeated record-like elements into tabular sources.

These formats are also included in local corpus search and policy discovery.

## 6. Canonical Schema and Adaptive Mapping

Proofline detectors operate on canonical German accounting fields so the fraud logic remains independent of filenames and most source-header changes.

Example canonical fields include:

- `SACHKONTONUMMER`: general-ledger account.
- `BUCHUNGSBETRAG`: posting amount.
- `BUCHUNGSDATUM`: posting date.
- `DOKUMENT`: document identifier.
- `BENUTZERKENNUNG`: posting user.
- `LIEFERANTENKONTONUMMER`: vendor identifier.
- `WARENEINGANG_DATUM`: goods-receipt date.
- `GEAENDERT_VON`: master-data changer.
- `GENEHMIGT_VON`: approver.

Native mappings and known aliases are attempted first. With `OPENAI_API_KEY` configured, unfamiliar tables are inventoried in batches of 25 and sent to the OpenAI Responses API using Pydantic structured output.

For each source, the model must return:

- source file;
- sheet or table identifier;
- inferred business role;
- header row;
- confidence;
- explicit source-column to canonical-column mappings.

Roles include general ledger, vendor transactions, vendor master, chart of accounts, assets, asset postings, goods receipts, master-data changes, supplier journals, sales journals and permissions.

A mapping is accepted only when:

1. the role is supported;
2. confidence is medium or high;
3. all mandatory fields for the role are present;
4. every claimed source column exists;
5. the mapped table contains non-empty records.

The model cannot invent source columns. Accepted records retain `_file`, `_sheet`, `_row` and `_role` provenance before entering deterministic checks.

## 7. Deterministic Accounting Engine

The audit engine performs calculations with Python `Decimal`, not binary floating-point arithmetic. It supports German and English number formats such as:

```text
1.234,56 EUR
1,234.56
(1,234.56)
```

Date parsing supports common German, ISO and English formats.

Core procedures include:

- ledger balance verification;
- GDPdU custody-hash comparison;
- trial-balance formula inspection;
- reported-profit reconstruction;
- proposed profit-adjustment bridge;
- source population counts;
- citation coverage measurement;
- unsupported-claim measurement.

The trial-balance engine does not execute Excel. It deterministically resolves the arithmetic, `SUM` and supported `SUMIF` patterns required by the dossier. Unsupported formulas remain unresolved rather than being guessed.

## 8. Fraud and Audit Detectors

### 8.1 Vendor Control Chain

Links vendor creation or master-data approval, incompatible permissions, vendor postings, cash movement and missing receipt evidence. A finding is promoted only when the cross-document sequence is supportable.

### 8.2 Bank Change Before Payment

Finds vendor bank-detail changes without independent approval and tests whether supplier payments follow inside a short dated window.

### 8.3 Capitalized Repair-Like Expenditure

Matches repair, maintenance, replacement or overhaul language across supplier transactions, asset master data, asset postings and ledger records.

### 8.4 Year-End Cut-Off

Matches pre-year-end goods receipts to following-period supplier invoices and tests for missing document-level accruals in the current-year ledger.

### 8.5 Approval-Threshold Splitting

Discovers the approval threshold from policy documents and identifies multiple same-day supplier payments immediately below the threshold.

### 8.6 Duplicate Supplier Invoices

Identifies repeated supplier invoice references and requires supporting records before promotion.

### 8.7 Supplier Overpayment

Reconciles supplier invoices and payments to identify cash settlements exceeding matched invoice amounts.

### 8.8 Premature Revenue

Compares invoice dates and performance dates to identify revenue invoiced in the reporting period for later-period performance.

### 8.9 Held-Back Data-Quality Signals

Contradictory related-party or vendor mappings remain visible as data-quality signals but are not promoted as fraud. This is intentional: clean or ambiguous items must not be treated as accusations.

## 9. Evidence Model

Each evidence object contains:

```json
{
  "id": "ev-...",
  "file": "relative/original/source.ext",
  "kind": "row | rows | cell | page | paragraph | vision | query",
  "locator": {},
  "label": "human-readable evidence title",
  "excerpt": "exact supporting passage or deterministic summary",
  "fields": {},
  "sha256": "original source digest"
}
```

Evidence IDs are generated deterministically from the source, locator and label. Findings refer to evidence IDs instead of copying unaudited values into presentation logic.

A finding can contain:

- supporting evidence;
- counter-evidence;
- sourced facts;
- monetary values;
- caveats;
- next audit procedure;
- entity and transaction graph;
- auditor review status.

## 10. OpenAI Integration

### 10.1 Configuration

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6
```

The OpenAI integration is optional. Without a key, native ingestion, deterministic reconciliation, detectors, evidence linking, local search and reports continue to work.

### 10.2 Model Tasks

The configured multimodal model is used for three bounded tasks:

1. Unknown table-role and column mapping.
2. Text and table extraction from image-only documents.
3. Evidence-focused search planning and narrative review.

The model does not replace deterministic calculations or directly decide the auditor conclusion.

### 10.3 Structured Outputs

All AI stages use `responses.parse` with Pydantic models. This constrains output shape and prevents free-form model text from entering the application unchecked.

Requests use:

- `store=False`;
- low or no reasoning effort depending on the task;
- bounded output tokens;
- low text verbosity;
- a fixed safety identifier.

### 10.4 Claim Firewall

AI-reviewed narratives are accepted only if they:

- reference an existing deterministic finding;
- preserve its assessment status;
- cite known evidence IDs;
- do not introduce numbers into prose.

New AI investigation leads require:

- high confidence;
- evidence from at least two distinct files;
- valid evidence IDs;
- no unsourced numbers;
- a title not duplicating an existing finding.

This intentionally favors false negatives over unsupported accusations.

## 11. Local Search and Question Answering

`search_corpus` searches source content locally. It supports bilingual synonyms for concepts such as approval, payment, vendor, receipt, invoice, bank, repair, asset, revenue and profit.

Search results contain the original file, locator, excerpt, score and SHA-256 digest. The local dossier is not uploaded to a vector database.

The question endpoint routes common audit questions to supported deterministic procedures and returns an answer with evidence IDs and sourced facts. It rejects questions requiring a finding when no evidence-backed finding exists.

## 12. API Reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service health check |
| GET | `/api/demo` | Sample deterministic payload; optional AI query flag |
| POST | `/api/runs` | Upload and analyze dossier |
| GET | `/api/runs/{run_id}` | Retrieve complete run payload |
| GET | `/api/runs/{run_id}/findings` | Retrieve findings |
| POST | `/api/runs/{run_id}/ai-review` | Run optional AI review |
| GET | `/api/runs/{run_id}/events` | Stream stage progress events |
| GET | `/api/evidence/{evidence_id}` | Retrieve an evidence object |
| GET | `/api/runs/{run_id}/source/{path}` | Open an original source |
| GET | `/api/runs/{run_id}/search?q=...` | Search complete dossier |
| POST | `/api/runs/{run_id}/ask` | Ask a supported audit question |
| PATCH | `/api/findings/{finding_id}/review` | Confirm, dismiss or reset auditor status |
| GET | `/api/runs/{run_id}/report` | Printable evidence report |

Dismissal requires a reason, which becomes part of the run's audit trail.

## 13. Frontend Experience

### 13.1 Investigation View

The investigation view presents:

- ranked promoted cases;
- selected-case monetary facts;
- a responsive evidence-chain visualization;
- source-backed observations;
- supporting and counter-evidence;
- AI review state;
- professional-judgement caveats;
- next audit procedure;
- auditor confirmation or reasoned dismissal;
- original source proof object.

The evidence chain uses content-sized HTML cards rather than fixed SVG boxes. Relationship labels stay attached to connectors and long entity names wrap inside their cards.

### 13.2 Materiality View

The materiality view shows reported profit, evidence-adjusted profit, individual finding effects and calculation lineage. The frontend calculates the displayed bridge from the sourced run and finding amounts.

### 13.3 Sources View

The sources view shows format coverage, hash status, adaptive mapping, visual extraction, held-back signals, corpus search and the complete manifest.

### 13.4 Accessibility

The frontend includes:

- semantic buttons and navigation;
- visible keyboard focus;
- `aria-current` navigation state;
- focus transfer when switching views;
- responsive layouts;
- readable working typography;
- `prefers-reduced-motion` handling;
- textual labels in addition to color;
- printable report styling.

## 14. Runtime State and Persistence

Runs are stored in process memory. Source files are stored under the system temporary directory:

```text
<temp>/proofline-runs/<run_id>/
```

There is no database, durable queue or object store. Restarting the service deletes run state. This is appropriate for a synthetic hackathon demonstration but not for production audit retention.

The sample run is loaded from the dossier bundled into the Docker image and cached in memory after its first analysis.

## 15. Authentication and Security Model

`DEMO_TOKEN` optionally enables a shared API gate. The token may be supplied through the `X-Demo-Token` header or URL query parameter.

This is not full authentication. A production system would require:

- TLS and enterprise identity;
- per-engagement authorization;
- encrypted durable storage;
- malware scanning and document sandboxing;
- audit logging;
- key management;
- retention and deletion policies;
- background queues and worker isolation;
- tenant isolation;
- privacy and data-processing review.

When an OpenAI key is configured, unfamiliar table previews, scanned PDFs/images and Office-embedded images may be sent to OpenAI. The application uses `store=False`, but organizations must still review their applicable data-processing terms.

## 16. Testing Strategy

Backend tests cover:

- sample dossier reconciliation and all expected findings;
- evidence completeness and unsupported-claim count;
- API question and auditor-review flows;
- demo-token enforcement;
- executable-file rejection;
- German and English monetary parsing;
- oversized and unmapped dossier rejection;
- original source serving;
- filename-independent schema discovery;
- arbitrary AI column mapping;
- claim-firewall rejection rules;
- AI candidate cross-document requirements;
- PDF policy passage handling;
- DOCX/PPTX text and table extraction;
- Office embedded images;
- Markdown, JSON and XML tables;
- nested ZIP extraction.

Run all backend tests:

```bash
python -m pytest -q
```

Run frontend checks:

```bash
cd frontend
npm test
npm run build
```

## 17. Local Development

### Docker

```bash
docker build -t proofline .
docker run --rm --env-file .env -p 8000:8000 proofline
```

Open `http://localhost:8000`.

### Native Development

```bash
python -m venv .venv
python -m pip install -r requirements.txt

cd frontend
npm install
npm run build
cd ..

uvicorn backend.app:app --reload
```

Legacy DOC/PPT/XLS conversion is available only when LibreOffice is installed. The Docker image includes it.

## 18. Deployment

`render.yaml` declares one Docker web service:

- name: `proofline`;
- region: Frankfurt;
- health check: `/api/health`;
- default model: `gpt-5.6`;
- generated `DEMO_TOKEN`;
- manually supplied `OPENAI_API_KEY`.

The container runs as a non-root `proofline` user with UID 10001.

## 19. Known Constraints

- Run state is not durable.
- One process owns all run state.
- There is no production identity or authorization model.
- LibreOffice conversion increases image size and processing time.
- Visual extraction cost grows with the number of scanned or embedded images.
- Document malware scanning is not implemented.
- DOCX does not have stable page numbers without rendering; paragraph and embedded-object locators are used instead.
- AI schema mapping is conservative and may abstain on unexplained proprietary semantics.
- The system cannot detect every possible fraud pattern automatically.
- Formula support is intentionally bounded.
- Auditor review remains mandatory.

## 20. Technical Summary

Proofline is a single-service React and FastAPI forensic audit application deployed through a multi-stage Docker image. It ingests modern, legacy, textual, tabular and visual document formats; converts them into canonical accounting records; applies deterministic reconciliation and fraud detectors; and attaches every promoted claim to source-level evidence and SHA-256 provenance.

OpenAI `gpt-5.6` is an optional, bounded fallback for unfamiliar schemas, scanned or embedded visual evidence, search planning and narrative review. Pydantic structured outputs, confidence gates and a strict claim firewall prevent AI-generated numbers or unsupported evidence from becoming audit findings.

The frontend provides three connected workflows: investigation, materiality and source review. The backend exposes upload, evidence, source, search, question, review and report APIs. The current implementation is optimized for a hackathon dossier and demonstration environment; production adoption would require durable storage, enterprise authentication, malware isolation, job queues and formal data governance.
