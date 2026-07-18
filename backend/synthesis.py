"""Optional evidence-searching OpenAI reviewer with deterministic fallbacks."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from backend.audit import _pdf_pages, search_corpus
from backend.ingest import office_media, source_path


ShortText = Annotated[str, Field(max_length=160)]
Paragraph = Annotated[str, Field(max_length=500)]


class Narrative(BaseModel):
    finding_id: str
    assessment: Literal["exception", "investigate", "data_quality", "cleared"]
    summary: Paragraph
    rationale: list[Paragraph] = Field(max_length=4)
    caveats: list[Paragraph] = Field(max_length=4)
    next_step: Paragraph
    evidence_ids: list[str]


class SearchPlan(BaseModel):
    queries: list[ShortText] = Field(min_length=1, max_length=6)


class Candidate(BaseModel):
    title: ShortText
    category: ShortText
    summary: Paragraph
    confidence: Literal["low", "medium", "high"]
    rationale: list[Paragraph] = Field(min_length=1, max_length=4)
    caveats: list[Paragraph] = Field(min_length=1, max_length=4)
    next_step: Paragraph
    evidence_ids: list[str] = Field(min_length=2, max_length=6)


class ReviewBundle(BaseModel):
    findings: list[Narrative]
    candidates: list[Candidate] = Field(max_length=3)


class VisionPassage(BaseModel):
    page: int = Field(ge=1)
    kind: ShortText
    text: Annotated[str, Field(min_length=2, max_length=1000)]
    confidence: Literal["low", "medium", "high"]


class VisionExtraction(BaseModel):
    passages: list[VisionPassage] = Field(max_length=30)


class AuditAnswer(BaseModel):
    answer: Annotated[str, Field(min_length=2, max_length=1400)]
    evidence_ids: list[str] = Field(min_length=1, max_length=6)
    finding_id: str | None = None


_NUMBER = re.compile(r"[\d€$£]")


def _safe(narrative: Narrative, finding: dict, evidence: set[str]) -> bool:
    """Reject model content that adds numbers, unknown IDs, or changes status."""
    prose = [narrative.summary, narrative.next_step, *narrative.rationale, *narrative.caveats]
    return (
        narrative.finding_id == finding.get("id")
        and narrative.assessment == finding.get("system_status")
        and bool(narrative.evidence_ids)
        and set(narrative.evidence_ids) <= evidence
        and not any(_NUMBER.search(item) for item in prose)
    )


def _safe_candidate(candidate: Candidate, evidence: dict[str, dict], existing_titles: set[str]) -> bool:
    prose = [candidate.title, candidate.category, candidate.summary, candidate.next_step, *candidate.rationale, *candidate.caveats]
    cited = [evidence.get(evidence_id) for evidence_id in candidate.evidence_ids]
    return (
        candidate.confidence == "high"
        and candidate.title.casefold() not in existing_titles
        and all(cited)
        and len({item["file"] for item in cited if item}) >= 2
        and not any(_NUMBER.search(item) for item in prose)
    )


def _compact_findings(payload: dict) -> list[dict]:
    return [
        {
            "id": finding.get("id"),
            "assessment": finding.get("system_status"),
            "title": finding.get("title"),
            "summary": finding.get("summary"),
            "facts": finding.get("facts", []),
            "caveats": finding.get("caveats", []),
            "next_step": finding.get("next_step"),
            "evidence": [
                payload.get("evidence", {}).get(evidence_id)
                for evidence_id in finding.get("evidence_ids", []) + finding.get("counter_evidence_ids", [])
                if evidence_id in payload.get("evidence", {})
            ],
        }
        for finding in payload.get("findings", [])[:8]
    ]


def _search_evidence(root: Path, queries: list[str]) -> dict[str, dict]:
    evidence: dict[str, dict] = {}
    for query in queries[:8]:
        for result in search_corpus(root, query, limit=8):
            identity = json.dumps([result["file"], result["locator"]], sort_keys=True, ensure_ascii=False)
            evidence_id = "ai-ev-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
            evidence[evidence_id] = {
                "id": evidence_id,
                "file": result["file"],
                "kind": "search",
                "locator": result["locator"],
                "label": f"AI search evidence: {query}",
                "excerpt": result["excerpt"],
                "fields": {"search_query": query},
                "sha256": result["sha256"],
            }
            if len(evidence) >= 40:
                return evidence
    return evidence


def _vision_evidence(client, root: Path, model: str) -> tuple[dict[str, dict], int]:
    """Use vision for image documents and images embedded in Office files."""
    evidence: dict[str, dict] = {}
    errors = 0
    candidates = []
    for path in root.rglob("*"):
        suffix = path.suffix.casefold()
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            continue
        if suffix == ".pdf":
            pages = _pdf_pages(path)
            if pages and sum(len(page.strip()) for page in pages) < 40 * len(pages):
                candidates.append({"path": path, "data": path.read_bytes(), "media": "pdf", "pages": len(pages), "locator": None})
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            media = "jpeg" if suffix in {".jpg", ".jpeg"} else suffix.lstrip(".")
            candidates.append({"path": path, "data": path.read_bytes(), "media": media, "pages": 1, "locator": {"page": 1}})
    candidates.extend({**item, "pages": 1} for item in office_media(root))
    for candidate in candidates:
        try:
            path = source_path(candidate["path"])
            page_count = candidate["pages"]
            encoded = base64.b64encode(candidate["data"]).decode("ascii")
            media = candidate["media"]
            document = (
                {"type": "input_file", "filename": path.name, "file_data": f"data:application/pdf;base64,{encoded}", "detail": "high"}
                if media == "pdf"
                else {"type": "input_image", "image_url": f"data:image/{media};base64,{encoded}", "detail": "high"}
            )
            response = client.responses.parse(
                model=model,
                instructions=(
                    "Extract only audit-relevant visible text and table passages from this image document. "
                    "Preserve wording and numbers exactly. For PDFs identify the one-based page; for embedded or standalone images use page one. Omit uncertain passages."
                ),
                input=[{
                    "role": "user",
                    "content": [
                        document,
                        {"type": "input_text", "text": "Return the visible passages needed for an evidence-first financial audit."},
                    ],
                }],
                text_format=VisionExtraction,
                reasoning={"effort": "none"},
                max_output_tokens=3500,
                store=False,
                safety_identifier="proofline-demo",
                text={"verbosity": "low"},
            )
            extracted = response.output_parsed
            if not extracted:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            for passage in extracted.passages:
                if passage.confidence == "low" or passage.page > page_count:
                    continue
                locator = candidate["locator"] or {"page": passage.page}
                identity = f"{path}:{locator}:{passage.text}"
                evidence_id = "ai-vision-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
                evidence[evidence_id] = {
                    "id": evidence_id,
                    "file": path.relative_to(root).as_posix(),
                    "kind": "vision",
                    "locator": locator,
                    "label": f"Vision extraction: {passage.kind}",
                    "excerpt": passage.text,
                    "fields": {"extraction": "openai_vision", "confidence": passage.confidence},
                    "sha256": digest,
                }
        except Exception:
            errors += 1
    return evidence, errors


def extract_vision_evidence(root: Path) -> tuple[dict[str, dict], int]:
    """Extract otherwise unreadable PDFs once, before detectors need their facts."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}, 0
    from openai import OpenAI

    return _vision_evidence(
        OpenAI(api_key=api_key, timeout=45.0, max_retries=0),
        root,
        os.getenv("OPENAI_MODEL", "gpt-5.6"),
    )


def answer_question(payload: dict, root: Path, question: str) -> dict | None:
    """Answer from bounded dossier evidence; return None for deterministic fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI

    evidence = dict(payload.get("evidence", {}))
    for result in search_corpus(root, question, limit=16):
        identity = json.dumps([result["file"], result["locator"]], sort_keys=True, ensure_ascii=False)
        evidence_id = "qa-ev-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
        evidence[evidence_id] = {
            "id": evidence_id, "file": result["file"], "kind": "search", "locator": result["locator"],
            "label": "Question evidence", "excerpt": result["excerpt"], "fields": {}, "sha256": result["sha256"],
        }
    context = {
        "question": question,
        "findings": _compact_findings(payload),
        "evidence": [{key: item.get(key) for key in ("id", "file", "locator", "label", "excerpt")} for item in evidence.values()],
    }
    try:
        response = OpenAI(api_key=api_key, timeout=45.0, max_retries=0).responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
            instructions=(
                "Answer the auditor's question using only the supplied dossier evidence. Be direct, practical, and concise. "
                "Cite only supplied evidence IDs. Distinguish what the records show from what still requires professional judgement. "
                "If the evidence is insufficient, say so explicitly and identify the next audit procedure. Do not invent facts or amounts."
            ),
            input=json.dumps(context, ensure_ascii=False, default=str),
            text_format=AuditAnswer,
            reasoning={"effort": "low"},
            max_output_tokens=1800,
            store=False,
            safety_identifier="proofline-demo",
            text={"verbosity": "low"},
        )
        answer = response.output_parsed
        if not answer or not set(answer.evidence_ids) <= set(evidence):
            return None
        return {
            "answer": answer.answer,
            "finding_id": answer.finding_id if any(item.get("id") == answer.finding_id for item in payload.get("findings", [])) else None,
            "evidence_ids": answer.evidence_ids,
            "facts": [],
            "evidence": {evidence_id: evidence[evidence_id] for evidence_id in answer.evidence_ids},
            "method": "openai_grounded",
        }
    except Exception:
        return None


def _candidate_finding(candidate: Candidate, evidence: dict[str, dict]) -> dict:
    candidate_id = "ai-candidate-" + hashlib.sha1(candidate.title.encode("utf-8")).hexdigest()[:10]
    cited = [evidence[evidence_id] for evidence_id in candidate.evidence_ids]
    nodes = [(item["id"], Path(item["file"]).name, "document") for item in cited]
    nodes.append(("hypothesis", "Cross-document hypothesis", "control"))
    return {
        "id": candidate_id,
        "title": candidate.title,
        "category": candidate.category,
        "source": "ai_investigation",
        "system_status": "investigate",
        "auditor_status": "unreviewed",
        "severity": "medium",
        "confidence": candidate.confidence,
        "summary": candidate.summary,
        "amounts": {"net": None, "tax": None, "gross": None, "pnl_effect": None},
        "facts": [
            {"label": f"Source {index}", "value": Path(item["file"]).name, "evidence_id": item["id"]}
            for index, item in enumerate(cited, start=1)
        ],
        "caveats": candidate.caveats,
        "next_step": candidate.next_step,
        "evidence_ids": candidate.evidence_ids,
        "counter_evidence_ids": [],
        "graph": {
            "nodes": [{"id": node, "label": label, "type": kind, "meta": {}} for node, label, kind in nodes],
            "edges": [{"source": item["id"], "target": "hypothesis", "label": "supports review"} for item in cited],
        },
        "ai_narrative": {
            "summary": candidate.summary,
            "rationale": candidate.rationale,
            "caveats": candidate.caveats,
            "next_step": candidate.next_step,
            "evidence_ids": candidate.evidence_ids,
        },
    }


def enhance(payload: dict, root: Path | None = None) -> dict:
    """Search for unseen schemes, then attach only evidence-locked AI output."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        payload["ai"] = {"status": "offline", "detail": "Deterministic analysis active"}
        return payload

    from openai import OpenAI

    model = os.getenv("OPENAI_MODEL", "gpt-5.6")
    client = OpenAI(api_key=api_key, timeout=45.0, max_retries=0)
    search_evidence: dict[str, dict] = {}
    vision_errors = payload.get("run", {}).get("vision_errors", 0)
    try:
        if root:
            plan_response = client.responses.parse(
                model=model,
                instructions=(
                    "You are planning a forensic audit search. Return no more than six concise bilingual German/English search queries, each no longer than eight words, "
                    "for plausible fraud schemes not already covered. Search across documents to test relationships; "
                    "do not make conclusions and do not repeat known findings."
                ),
                input=json.dumps({
                    "manifest": [{key: item.get(key) for key in ("path", "kind", "records")} for item in payload.get("manifest", [])],
                    "known_findings": [finding.get("title") for finding in payload.get("findings", [])],
                    "held_signals": [signal.get("title") for signal in payload.get("signals", [])],
                }, ensure_ascii=False),
                text_format=SearchPlan,
                reasoning={"effort": "none"},
                max_output_tokens=1000,
                store=False,
                safety_identifier="proofline-demo",
                text={"verbosity": "low"},
            )
            plan = plan_response.output_parsed
            if plan:
                search_evidence = _search_evidence(root, plan.queries)
            visual = {key: item for key, item in payload.get("evidence", {}).items() if item.get("kind") == "vision"}
            if not visual:
                visual, vision_errors = _vision_evidence(client, root, model)
            search_evidence.update(visual)

        compact_findings = _compact_findings(payload)
        review_response = client.responses.parse(
            model=model,
            instructions=(
                "You are an audit reviewer. Improve known-finding clarity and inspect the separately supplied search evidence "
                "for unseen schemes. Preserve known assessments. A new candidate must be high confidence, cite at least two "
                "different source files, state only observations supported by those excerpts, include contrary explanations, "
                "and require auditor investigation rather than allege fraud. Return no candidate when evidence is insufficient. "
                "Do not state any number, date, currency, percentage, account, user, or vendor ID in prose. Use only supplied evidence IDs."
            ),
            input=json.dumps({
                "known_findings": compact_findings,
                "search_evidence": list(search_evidence.values()),
            }, ensure_ascii=False),
            text_format=ReviewBundle,
            reasoning={"effort": "low"},
            max_output_tokens=4000,
            store=False,
            safety_identifier="proofline-demo",
            text={"verbosity": "low"},
        )
        reviewed = review_response.output_parsed
        if not reviewed:
            payload["ai"] = {"status": "rejected", "accepted": 0, "candidates": 0, "model": model}
            return payload

        by_id = {item.finding_id: item for item in reviewed.findings}
        accepted = 0
        for finding in payload.get("findings", []):
            narrative = by_id.get(finding.get("id"))
            allowed = set(finding.get("evidence_ids", [])) | set(finding.get("counter_evidence_ids", []))
            if narrative and _safe(narrative, finding, allowed):
                finding["ai_narrative"] = narrative.model_dump()
                accepted += 1

        existing_titles = {finding.get("title", "").casefold() for finding in payload.get("findings", [])}
        accepted_candidates = [
            candidate for candidate in reviewed.candidates
            if _safe_candidate(candidate, search_evidence, existing_titles)
        ]
        if accepted_candidates:
            payload.setdefault("evidence", {}).update(search_evidence)
            payload["findings"].extend(_candidate_finding(candidate, search_evidence) for candidate in accepted_candidates)
            payload.get("metrics", {})["promoted_findings"] = len(payload["findings"])

        payload["ai"] = {
            "status": "enhanced" if accepted or accepted_candidates else "rejected",
            "accepted": accepted,
            "candidates": len(accepted_candidates),
            "searches": len(search_evidence),
            "vision_passages": sum(item.get("kind") == "vision" for item in search_evidence.values()),
            "vision_errors": vision_errors,
            "model": model,
        }
    except Exception as exc:  # deterministic output must survive provider failure
        payload["ai"] = {"status": "unavailable", "detail": f"{type(exc).__name__}: {str(exc)[:240]}"}
    return payload
