import json
from types import SimpleNamespace

from backend.synthesis import AuditAnswer, Candidate, Narrative, ReviewBundle, SearchPlan, _safe, _safe_candidate, answer_question, enhance


def test_offline_path_keeps_deterministic_payload(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    payload = {"findings": [], "evidence": {}}

    assert enhance(payload)["ai"]["status"] == "offline"


def test_claim_firewall_rejects_new_numbers_and_unknown_evidence():
    finding = {"id": "case", "system_status": "investigate"}
    good = Narrative(
        finding_id="case",
        assessment="investigate",
        summary="Control conflict requires review.",
        rationale=["The same role spans incompatible duties."],
        caveats=["Service delivery still needs confirmation."],
        next_step="Obtain independent service acceptance.",
        evidence_ids=["ev-known"],
    )
    bad_number = good.model_copy(update={"summary": "Cash exposure is 10."})
    bad_evidence = good.model_copy(update={"evidence_ids": ["ev-made-up"]})

    assert _safe(good, finding, {"ev-known"})
    assert not _safe(bad_number, finding, {"ev-known"})
    assert not _safe(bad_evidence, finding, {"ev-known"})


def test_candidate_firewall_requires_high_confidence_cross_document_evidence():
    evidence = {
        "ev-a": {"file": "vendor.csv"},
        "ev-b": {"file": "payments.csv"},
        "ev-c": {"file": "vendor.csv"},
    }
    candidate = Candidate(
        title="Bank detail change precedes unusual settlement",
        category="Cash diversion indicator",
        summary="Independent records show a control-sensitive sequence requiring investigation.",
        confidence="high",
        rationale=["The sources describe linked events across separate records."],
        caveats=["A legitimate supplier update remains possible."],
        next_step="Confirm beneficiary ownership through a known supplier contact.",
        evidence_ids=["ev-a", "ev-b"],
    )

    assert _safe_candidate(candidate, evidence, set())
    assert not _safe_candidate(candidate.model_copy(update={"confidence": "medium"}), evidence, set())
    assert not _safe_candidate(candidate.model_copy(update={"evidence_ids": ["ev-a", "ev-c"]}), evidence, set())
    assert not _safe_candidate(candidate.model_copy(update={"summary": "There are 2 linked events."}), evidence, set())


def test_ai_search_can_promote_a_cross_document_candidate(monkeypatch, tmp_path):
    (tmp_path / "vendor.csv").write_text("bank detail changed without approval", encoding="utf-8")
    (tmp_path / "payments.csv").write_text("bank beneficiary received unusual settlement", encoding="utf-8")

    class Responses:
        def parse(self, **kwargs):
            if kwargs["text_format"] is SearchPlan:
                return SimpleNamespace(output_parsed=SearchPlan(queries=["bank"]))
            search_evidence = json.loads(kwargs["input"])["search_evidence"]
            ids = [item["id"] for item in search_evidence]
            candidate = Candidate(
                title="Bank change and settlement sequence requires review",
                category="Cash diversion indicator",
                summary="Separate records support a control-sensitive sequence requiring investigation.",
                confidence="high",
                rationale=["Independent source records describe related control events."],
                caveats=["A legitimate supplier update remains possible."],
                next_step="Confirm beneficiary ownership through a known supplier contact.",
                evidence_ids=ids[:2],
            )
            return SimpleNamespace(output_parsed=ReviewBundle(findings=[], candidates=[candidate]))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(responses=Responses()))
    payload = {"manifest": [], "findings": [], "signals": [], "evidence": {}, "metrics": {"promoted_findings": 0}}
    result = enhance(payload, tmp_path)

    assert result["ai"]["candidates"] == 1
    assert result["findings"][0]["source"] == "ai_investigation"
    assert len(result["findings"][0]["evidence_ids"]) == 2


def test_grounded_answer_rejects_unknown_citations(monkeypatch, tmp_path):
    class Responses:
        def parse(self, **_):
            return SimpleNamespace(output_parsed=AuditAnswer(answer="The record supports review.", evidence_ids=["missing"]))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("openai.OpenAI", lambda **_: SimpleNamespace(responses=Responses()))
    payload = {"findings": [], "evidence": {"known": {"id": "known", "file": "a.csv", "excerpt": "record", "locator": {}}}}

    assert answer_question(payload, tmp_path, "What happened?") is None
