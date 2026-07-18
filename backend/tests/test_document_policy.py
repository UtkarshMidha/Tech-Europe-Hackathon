from pathlib import Path

from backend.audit import _document_passages


def test_document_passages_reads_pdf(monkeypatch, tmp_path: Path):
    policy = tmp_path / "renamed.pdf"
    policy.write_bytes(b"pdf")
    monkeypatch.setattr("backend.audit._pdf_pages", lambda path: ["Intro\nZahlungsfreigaben ab 50.000 EUR durch zwei Personen"])

    assert _document_passages(policy) == [
        ("Intro", "page", {"page": 1}),
        ("Zahlungsfreigaben ab 50.000 EUR durch zwei Personen", "page", {"page": 1}),
    ]
