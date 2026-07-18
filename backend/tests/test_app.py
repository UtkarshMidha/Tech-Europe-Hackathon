import io
import zipfile
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import _engagement_name, app
from fastapi import UploadFile
from backend.audit import analyze, evidence_context, money


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "Uebungsdaten Muster Verpackungen"


def test_engagement_name_uses_uploaded_container():
    assert _engagement_name([UploadFile(io.BytesIO(), filename="Final Audit.zip")]) == "Final Audit"
    assert _engagement_name([UploadFile(io.BytesIO(), filename="Client Folder/ledger.csv"), UploadFile(io.BytesIO(), filename="Client Folder/bank.pdf")]) == "Client Folder"


def test_sample_analysis_is_balanced_grounded_and_precise():
    payload = analyze(SAMPLE)
    findings = {finding["id"]: finding for finding in payload["findings"]}

    assert payload["run"]["files"] == 35
    assert payload["metrics"]["general_ledger_rows"] == 20258
    assert payload["metrics"]["general_ledger_balance"] == "0.00"
    assert payload["metrics"]["formula_resolved"] == 47
    assert payload["metrics"]["unsupported_claims"] == 0
    assert payload["metrics"]["hashes_verified"] == payload["metrics"]["hashes_expected"]
    assert payload["signals"][0]["status"] == "data_quality"
    assert payload["run"]["proposed_adjusted_profit"] == "2257041.80"
    assert payload["run"]["reported_profit_evidence_id"] in payload["evidence"]
    assert payload["calculations"][0]["output"] == "2257041.80"
    assert findings["vendor-control-chain"]["amounts"] == {
        "net": "248000.00",
        "tax": "47120.00",
        "gross": "295120.00",
        "pnl_effect": None,
    }
    assert findings["capitalized-repairs"]["amounts"]["net"] == "150800.00"
    assert findings["year-end-cutoff"]["amounts"]["net"] == "192000.00"
    assert findings["threshold-splitting"]["amounts"]["gross"] == "39040.00"
    assert all(finding["evidence_ids"] for finding in findings.values())
    assert not any("GROUND-TRUTH" in item["path"].upper() for item in payload["manifest"])


def test_demo_api_question_and_review_round_trip():
    client = TestClient(app)
    response = client.get("/api/demo")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["findings"]) == 4

    question = client.post("/api/runs/sample/ask", json={"question": "Who can create and pay a vendor?"})
    assert question.status_code == 200
    assert question.json()["finding_id"] == "vendor-control-chain"
    assert question.json()["evidence_ids"]

    profit = client.post("/api/runs/sample/ask", json={"question": "Trace the profit adjustment"})
    assert profit.json()["evidence_ids"][0] == payload["run"]["reported_profit_evidence_id"]

    review = client.patch(
        "/api/findings/vendor-control-chain/review",
        json={"run_id": "sample", "status": "confirmed", "note": "Control failure confirmed."},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "confirmed"


def test_demo_token_gate(monkeypatch):
    monkeypatch.setenv("DEMO_TOKEN", "secret")
    client = TestClient(app)
    assert client.get("/api/demo").status_code == 401
    assert client.get("/api/demo?token=secret").status_code == 200
    monkeypatch.delenv("DEMO_TOKEN")


def test_upload_rejects_executable_files():
    client = TestClient(app)
    response = client.post("/api/runs", files={"files": ("payload.exe", b"nope")})
    assert response.status_code == 400


def test_money_parser_supports_german_and_english_grouping():
    assert money("1.234,56 EUR") == money("1,234.56")
    assert money("1.234,56 EUR") == Decimal("1234.56")


def test_upload_rejects_unmapped_or_oversized_dossiers():
    client = TestClient(app)
    unrelated = client.post("/api/runs", files={"files": ("ledger.csv", b"amount\nnot-a-number", "text/csv")})
    assert unrelated.status_code == 422
    assert "general-ledger" in unrelated.json()["detail"]

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        for index in range(101):
            package.writestr(f"row-{index}.csv", "a;b\n1;2")
    too_many = client.post("/api/runs", files={"files": ("dossier.zip", archive.getvalue(), "application/zip")})
    assert too_many.status_code == 400


def test_original_source_and_dismissal_reason_are_enforced():
    client = TestClient(app)
    source = client.get("/api/runs/sample/source/Begleitdokumente/Wareneingangsliste_2025.csv")
    assert source.status_code == 200
    assert "WARENEINGANG" in source.text
    search = client.get("/api/runs/sample/search", params={"q": "approval"})
    assert search.status_code == 200
    assert any("Pruefungsplanung" in result["file"] for result in search.json()["results"])

    missing_reason = client.patch(
        "/api/findings/vendor-control-chain/review",
        json={"run_id": "sample", "status": "dismissed", "note": ""},
    )
    assert missing_reason.status_code == 422


def test_schema_discovery_accepts_renamed_ledger_and_keeps_missing_profit_null(tmp_path):
    (tmp_path / "renamed-ledger.txt").write_text(
        "1000;10,00;DOC-1;31.12.2025;U1\n2000;-10,00;DOC-1;31.12.2025;U1\n",
        encoding="utf-8",
    )
    (tmp_path / "index.xml").write_text(
        """<DataSet><Table><URL>renamed-ledger.txt</URL><VariableColumn><Name>SACHKONTONUMMER</Name></VariableColumn><VariableColumn><Name>BUCHUNGSBETRAG</Name></VariableColumn><VariableColumn><Name>DOKUMENT</Name></VariableColumn><VariableColumn><Name>BUCHUNGSDATUM</Name></VariableColumn><VariableColumn><Name>BENUTZERKENNUNG</Name></VariableColumn></Table></DataSet>""",
        encoding="utf-8",
    )
    payload = analyze(tmp_path)
    assert payload["run"]["integrity"] == "balanced"
    assert payload["run"]["reported_profit"] is None
    assert payload["run"]["proposed_adjusted_profit"] is None
    assert payload["calculations"] == []


def test_evidence_context_marks_previous_current_and_next_rows(tmp_path):
    source = tmp_path / "rows.csv"
    source.write_text("id;amount\n1;10\n2;20\n3;30\n", encoding="utf-8")
    context = evidence_context(tmp_path, {"file": "rows.csv", "locator": {"row": 3}, "excerpt": "id: 2"})

    assert [row["position"] for row in context["rows"]] == [2, 3, 4]
    assert [row["relevant"] for row in context["rows"]] == [False, True, False]
    assert context["rows"][1]["values"]["amount"] == "20"


def test_zip_ignores_macos_metadata(tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("__MACOSX/._ledger.csv", b"metadata")
        package.writestr("dossier/.DS_Store", b"metadata")
        package.writestr("dossier/ledger.csv", b"a;b\n1;2")

    from backend.app import _extract_zip
    count, expanded = _extract_zip(archive.getvalue(), tmp_path / "out", 100)

    assert count == 1
    assert expanded == len(b"a;b\n1;2")
