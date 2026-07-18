from __future__ import annotations

import asyncio
import copy
import html
import io
import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.adaptive import map_tables
from backend.audit import BLOCKED_NAMES, analyze, evidence_context, search_corpus
from backend.ingest import normalize_legacy
from backend.synthesis import answer_question, enhance, extract_vision_evidence


BASE = Path(__file__).resolve().parents[1]
SAMPLE = BASE / "Uebungsdaten Muster Verpackungen"
DIST = BASE / "frontend" / "dist"
RUN_ROOT = Path(tempfile.gettempdir()) / "proofline-runs"
RUN_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Proofline", version="1.0.0")
RUNS: dict[str, dict] = {}
RUN_PATHS: dict[str, Path] = {}
RUN_CREATED: dict[str, float] = {}
REVIEWS: dict[tuple[str, str], dict] = {}
_DEMO: dict | None = None
_AI_DEMO: dict | None = None
ALLOWED_UPLOADS = {".zip", ".txt", ".csv", ".xml", ".dtd", ".xlsx", ".xls", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".md", ".json", ".png", ".jpg", ".jpeg", ".webp"}
MAX_EXPANDED_BYTES = 600 * 1024 * 1024


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class ReviewRequest(BaseModel):
    status: str = Field(pattern="^(confirmed|dismissed|unreviewed)$")
    note: str = Field(default="", max_length=2000)
    run_id: str = "sample"


@app.middleware("http")
async def demo_gate(request: Request, call_next):
    expected = os.getenv("DEMO_TOKEN", "")
    if expected and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        supplied = request.headers.get("x-demo-token") or request.query_params.get("token")
        if supplied != expected:
            return JSONResponse({"detail": "Demo token required"}, status_code=401)
    return await call_next(request)


def _base_demo() -> dict:
    global _DEMO
    if _DEMO is None:
        if not SAMPLE.exists():
            raise HTTPException(503, "Sample dossier is not available")
        _DEMO = analyze(SAMPLE)
    payload = copy.deepcopy(_DEMO)
    for finding in payload["findings"]:
        review = REVIEWS.get(("sample", finding["id"]))
        if review:
            finding["auditor_status"] = review["status"]
            finding["review_note"] = review["note"]
    return payload


def _payload(run_id: str) -> dict:
    if run_id == "sample":
        return _base_demo()
    if run_id not in RUNS:
        raise HTTPException(404, "Run not found")
    return RUNS[run_id]


def _source_root(run_id: str) -> Path:
    _payload(run_id)
    if run_id == "sample":
        return SAMPLE.resolve()
    root = RUN_PATHS.get(run_id)
    if not root:
        raise HTTPException(404, "Run sources are no longer available")
    return root.resolve()


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "deterministic", "sample": SAMPLE.exists()}


@app.get("/api/demo")
def demo(ai: bool = False):
    global _AI_DEMO
    payload = _base_demo()
    if not ai:
        return {**payload, "ai": {"status": "available" if os.getenv("OPENAI_API_KEY") else "offline"}}
    if _AI_DEMO is not None:
        return copy.deepcopy(_AI_DEMO)
    reviewed = enhance(payload, SAMPLE)
    if reviewed.get("ai", {}).get("status") == "enhanced":
        _AI_DEMO = copy.deepcopy(reviewed)
    return reviewed


def _safe_name(filename: str) -> PurePosixPath:
    normalized = filename.replace("\\", "/").lstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise HTTPException(400, f"Unsafe upload path: {filename}")
    if any(word in path.name.upper() for word in BLOCKED_NAMES):
        raise HTTPException(400, f"Excluded answer-like file: {path.name}")
    if path.suffix.lower() not in ALLOWED_UPLOADS:
        raise HTTPException(400, f"Unsupported file type: {path.suffix or '(none)'}")
    return path


def _engagement_name(files: list[UploadFile]) -> str:
    paths = [PurePosixPath((item.filename or "").replace("\\", "/")) for item in files]
    if len(paths) == 1 and paths[0].suffix.casefold() == ".zip":
        return paths[0].stem
    roots = {path.parts[0] for path in paths if len(path.parts) > 1}
    return roots.pop() if len(roots) == 1 else "Uploaded dossier"


def _extract_zip(data: bytes, destination: Path, remaining_files: int, prefix: PurePosixPath = PurePosixPath(), depth: int = 0) -> tuple[int, int]:
    if depth > 3:
        raise HTTPException(400, "Nested ZIP depth exceeds 3")
    expanded = 0
    count = 0
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(400, "Invalid ZIP archive") from exc
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            metadata_path = PurePosixPath(member.filename.replace("\\", "/"))
            if "__MACOSX" in metadata_path.parts or metadata_path.name == ".DS_Store" or metadata_path.name.startswith("._"):
                continue
            relative = _safe_name(member.filename)
            expanded += member.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise HTTPException(413, "Expanded archive exceeds 600 MB")
            if relative.suffix.casefold() == ".zip":
                nested = archive.read(member)
                added, nested_size = _extract_zip(nested, destination, remaining_files - count, prefix / relative.with_suffix(""), depth + 1)
                count += added
                expanded += nested_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise HTTPException(413, "Expanded archive exceeds 600 MB")
                continue
            count += 1
            if count > remaining_files:
                raise HTTPException(400, "Archive exceeds the 100-file dossier limit")
            target = destination.joinpath(*(prefix / relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return count, expanded


def _prune_runs() -> None:
    cutoff = time.time() - 6 * 60 * 60
    expired = [run_id for run_id, created in RUN_CREATED.items() if created < cutoff]
    while len(RUNS) - len(expired) >= 10:
        remaining = [(created, run_id) for run_id, created in RUN_CREATED.items() if run_id not in expired]
        if not remaining:
            break
        expired.append(min(remaining)[1])
    for run_id in expired:
        path = RUN_PATHS.pop(run_id, None)
        if path and path.parent == RUN_ROOT:
            shutil.rmtree(path, ignore_errors=True)
        RUNS.pop(run_id, None)
        RUN_CREATED.pop(run_id, None)


@app.post("/api/runs", status_code=202)
async def create_run(files: list[UploadFile] = File(...), ai: bool = False):
    if not files or len(files) > 100:
        raise HTTPException(400, "Upload between 1 and 100 files")
    _prune_runs()
    engagement_name = _engagement_name(files)
    run_id = uuid4().hex[:12]
    destination = RUN_ROOT / run_id
    destination.mkdir(parents=True, exist_ok=False)
    total = 0
    expanded_total = 0
    file_count = 0
    try:
        for upload in files:
            upload_path = PurePosixPath((upload.filename or "").replace("\\", "/"))
            if "__MACOSX" in upload_path.parts or upload_path.name == ".DS_Store" or upload_path.name.startswith("._"):
                continue
            relative = _safe_name(upload.filename or "")
            data = await upload.read()
            total += len(data)
            if total > MAX_EXPANDED_BYTES:
                raise HTTPException(413, "Dossier exceeds 600 MB")
            if relative.suffix.lower() == ".zip":
                added, expanded = _extract_zip(data, destination, 100 - file_count)
                file_count += added
                expanded_total += expanded
                if expanded_total > MAX_EXPANDED_BYTES:
                    raise HTTPException(413, "Expanded dossier exceeds 600 MB")
            else:
                file_count += 1
                if file_count > 100:
                    raise HTTPException(400, "Dossier exceeds the 100-file limit")
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        converted = await asyncio.to_thread(normalize_legacy, destination)
        vision, vision_errors = await asyncio.to_thread(extract_vision_evidence, destination)
        mapped_tables, mappings, mapping_error = {}, [], None
        try:
            mapped_tables, mappings = await asyncio.to_thread(map_tables, destination)
        except Exception as exc:
            mapping_error = exc
        try:
            payload = await asyncio.to_thread(analyze, destination, mapped_tables, list(vision.values()))
        except ValueError as exc:
            if mapping_error:
                raise ValueError(f"Native schema mapping failed; AI fallback returned {type(mapping_error).__name__}") from mapping_error
            raise exc
        if mappings:
            payload["adaptive"] = {"status": "mapped", "sources": mappings}
            payload["run"]["adaptive_sources"] = len(mappings)
        payload["evidence"].update(vision)
        payload["run"]["vision_passages"] = len(vision)
        payload["run"]["vision_errors"] = vision_errors
        payload["run"]["legacy_conversions"] = converted
        if ai:
            payload = await asyncio.to_thread(enhance, payload, destination)
        payload["run"]["id"] = run_id
        payload["run"]["engagement"] = engagement_name
        RUNS[run_id] = payload
        RUN_PATHS[run_id] = destination
        RUN_CREATED[run_id] = time.time()
        return {"run_id": run_id, "status": "complete"}
    except ValueError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _payload(run_id)


@app.get("/api/runs/{run_id}/findings")
def get_findings(run_id: str):
    return _payload(run_id)["findings"]


@app.post("/api/runs/{run_id}/ai-review")
async def ai_review(run_id: str):
    global _AI_DEMO
    if run_id == "sample" and _AI_DEMO is not None:
        return copy.deepcopy(_AI_DEMO)
    reviewed = await asyncio.to_thread(enhance, copy.deepcopy(_payload(run_id)), _source_root(run_id))
    if run_id == "sample" and reviewed.get("ai", {}).get("status") == "enhanced":
        _AI_DEMO = copy.deepcopy(reviewed)
    if run_id in RUNS:
        RUNS[run_id] = reviewed
    return reviewed


@app.get("/api/runs/{run_id}/events")
def events(run_id: str):
    _payload(run_id)

    async def stream():
        for stage in ("ingest", "normalize", "reconcile", "detect", "done"):
            yield f"event: progress\ndata: {json.dumps({'stage': stage, 'run_id': run_id})}\n\n"
            await asyncio.sleep(0.03)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/evidence/{evidence_id}")
def get_evidence(evidence_id: str, run_id: str = "sample"):
    item = _payload(run_id)["evidence"].get(evidence_id)
    if not item:
        raise HTTPException(404, "Evidence not found")
    return item


@app.get("/api/runs/{run_id}/evidence/{evidence_id}/context")
def get_evidence_context(run_id: str, evidence_id: str):
    item = _payload(run_id)["evidence"].get(evidence_id)
    if not item:
        raise HTTPException(404, "Evidence not found")
    try:
        return evidence_context(_source_root(run_id), item)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/runs/{run_id}/source/{source_path:path}")
def get_source(run_id: str, source_path: str):
    root = _source_root(run_id)
    relative = _safe_name(source_path)
    target = root.joinpath(*relative.parts).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "Source not found")
    return FileResponse(target)


@app.get("/api/runs/{run_id}/search")
def search(run_id: str, q: str):
    if len(q.strip()) < 2 or len(q) > 200:
        raise HTTPException(422, "Search query must contain 2–200 characters")
    return {"query": q, "results": search_corpus(_source_root(run_id), q)}


@app.post("/api/runs/{run_id}/ask")
def ask(run_id: str, request: AskRequest):
    payload = _payload(run_id)
    ai_answer = answer_question(payload, _source_root(run_id), request.question)
    if ai_answer:
        return ai_answer
    if not payload["findings"]:
        raise HTTPException(409, "No evidence-backed finding is available; search the source corpus instead.")
    query = request.question.casefold()
    if any(word in query for word in ("create", "anlegen", "pay", "zahlen", "vendor", "kreditor")):
        selected = next((finding for finding in payload["findings"] if finding["id"] == "vendor-control-chain"), payload["findings"][0])
        answer = "The evidence shows one user spanning vendor creation, approval, posting, and payment. Service delivery still requires independent confirmation."
    elif any(word in query for word in ("profit", "gewinn", "materiality", "wesentlich")):
        if payload["run"].get("reported_profit") is None:
            raise HTTPException(409, "No sourced trial balance is available for a profit answer.")
        selected = next((finding for finding in payload["findings"] if finding["id"] == "year-end-cutoff"), payload["findings"][0])
        answer = f"Reported profit is {payload['run']['reported_profit']} EUR; proposed classification and cut-off adjustments produce {payload['run']['proposed_adjusted_profit']} EUR, subject to the stated caveats."
    elif any(word in query for word in ("threshold", "limit", "split", "freigabe")):
        selected = next((finding for finding in payload["findings"] if finding["id"] == "threshold-splitting"), payload["findings"][0])
        answer = "Several same-day payments sit immediately below the sourced two-approval threshold. This is a control indicator, not proof of intent."
    else:
        selected = payload["findings"][0]
        answer = "The strongest case combines access rights, master-data approval, ledger activity, rapid settlement, and a reproducible absence test."
    evidence_ids = list(selected["evidence_ids"])
    facts = list(selected["facts"])
    if any(word in query for word in ("profit", "gewinn", "materiality", "wesentlich")):
        reported_evidence = payload["run"].get("reported_profit_evidence_id")
        if reported_evidence:
            evidence_ids.insert(0, reported_evidence)
            facts.insert(0, {"label": "Reported draft profit", "value": payload["run"]["reported_profit"], "evidence_id": reported_evidence})
    return {"answer": answer, "finding_id": selected["id"], "evidence_ids": evidence_ids, "facts": facts}


@app.patch("/api/findings/{finding_id}/review")
def review(finding_id: str, request: ReviewRequest):
    payload = _payload(request.run_id)
    if not any(finding["id"] == finding_id for finding in payload["findings"]):
        raise HTTPException(404, "Finding not found")
    if request.status == "dismissed" and not request.note.strip():
        raise HTTPException(422, "A dismissal reason is required")
    result = {"status": request.status, "note": request.note}
    REVIEWS[(request.run_id, finding_id)] = result
    if request.run_id in RUNS:
        finding = next(finding for finding in RUNS[request.run_id]["findings"] if finding["id"] == finding_id)
        finding["auditor_status"] = request.status
        finding["review_note"] = request.note
    return {"finding_id": finding_id, **result}


@app.get("/api/runs/{run_id}/report", response_class=HTMLResponse)
def report(run_id: str, request: Request):
    payload = _payload(run_id)
    supplied_token = request.query_params.get("token", "")
    token_suffix = f"?token={quote(supplied_token)}" if supplied_token else ""
    sections = []
    for finding in payload["findings"]:
        all_evidence = [*finding["evidence_ids"], *finding.get("counter_evidence_ids", [])]
        evidence = "".join(
            "<li>"
            f"<a href='/api/runs/{quote(run_id)}/source/{quote(payload['evidence'][eid]['file'])}{token_suffix}'><strong>{html.escape(payload['evidence'][eid]['label'])}</strong></a> — "
            f"{html.escape(payload['evidence'][eid]['file'])}, {html.escape(str(payload['evidence'][eid]['locator']))}<br>"
            f"<code>SHA-256 {html.escape(payload['evidence'][eid]['sha256'])}</code><br>"
            f"{html.escape(payload['evidence'][eid]['excerpt'])}</li>"
            for eid in all_evidence
        )
        amounts = " · ".join(f"{key}: {value} EUR" for key, value in finding.get("amounts", {}).items() if value is not None)
        review_status = finding.get("auditor_status", "unreviewed")
        review_note = finding.get("review_note", "")
        sections.append(
            f"<section><p class='meta'>{html.escape(finding['severity'].upper())} · {html.escape(finding['confidence'])} confidence · auditor: {html.escape(review_status)}</p>"
            f"<h2>{html.escape(finding['title'])}</h2><p>{html.escape(finding['summary'])}</p>"
            f"<p><strong>Amounts:</strong> {html.escape(amounts or 'No monetary conclusion')}</p>"
            f"<h3>Evidence and counter-evidence</h3><ol>{evidence}</ol>"
            f"<p><strong>Caveat:</strong> {html.escape(' '.join(finding['caveats']))}</p>"
            f"<p><strong>Next procedure:</strong> {html.escape(finding['next_step'])}</p>"
            + (f"<p><strong>Review note:</strong> {html.escape(review_note)}</p>" if review_note else "")
            + "</section>"
        )
    calculations = "".join(
        f"<li><code>{html.escape(item['expression'])}</code> = <strong>{html.escape(item['output'])} EUR</strong></li>"
        for item in payload.get("calculations", [])
    )
    run = payload["run"]
    return (
        "<!doctype html><meta charset='utf-8'><title>Proofline evidence report</title>"
        "<style>body{font:14px system-ui;max-width:940px;margin:40px auto;color:#17201d;line-height:1.5}section{break-inside:avoid;border-top:1px solid #ccd5d0;padding:20px 0}h1{font-size:34px}h2{font-size:21px}li{margin:12px 0}.meta{color:#59665f;text-transform:uppercase;font-size:11px}code{font-size:10px;overflow-wrap:anywhere}a{color:#176247}</style>"
        "<h1>Proofline evidence report</h1>"
        f"<p><strong>Engagement:</strong> {html.escape(str(run.get('engagement', '')))} · <strong>FY:</strong> {html.escape(str(run.get('fiscal_year') or 'unknown'))} · <strong>Integrity:</strong> {html.escape(run['integrity'])}</p>"
        f"<p><strong>Reported profit:</strong> {html.escape(str(run['reported_profit']) if run['reported_profit'] is not None else 'unavailable')} EUR · <strong>Proposed adjusted:</strong> {html.escape(str(run['proposed_adjusted_profit']) if run['proposed_adjusted_profit'] is not None else 'unavailable')} EUR</p>"
        f"<h2>Calculation lineage</h2><ul>{calculations}</ul>"
        + "".join(sections)
    )


@app.get("/", response_class=HTMLResponse)
def root():
    index = DIST / "index.html"
    return index.read_text(encoding="utf-8") if index.exists() else "<h1>Proofline API</h1><p>Build the frontend to open the cockpit.</p>"


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
