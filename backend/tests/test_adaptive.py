from backend.adaptive import ColumnMapping, MappingPlan, SourceMapping, _materialize
from backend.audit import analyze


def test_ai_mapping_can_normalize_an_unfamiliar_csv_schema(tmp_path):
    (tmp_path / "mystery.csv").write_text(
        "Account,Value,Reference,When,Operator\nCash,10.00,DOC-A,2025-12-31,U1\nRevenue,-10.00,DOC-A,2025-12-31,U1\n",
        encoding="utf-8",
    )
    plan = MappingPlan(sources=[SourceMapping(
        file="mystery.csv",
        role="general_ledger",
        header_row=1,
        confidence="high",
        columns=[
            ColumnMapping(source="Account", target="SACHKONTONUMMER"),
            ColumnMapping(source="Value", target="BUCHUNGSBETRAG"),
            ColumnMapping(source="Reference", target="DOKUMENT"),
            ColumnMapping(source="When", target="BUCHUNGSDATUM"),
            ColumnMapping(source="Operator", target="BENUTZERKENNUNG"),
        ],
    )])

    tables, mappings = _materialize(tmp_path, plan)
    payload = analyze(tmp_path, tables)

    assert len(mappings) == 1
    assert payload["run"]["integrity"] == "balanced"
    assert payload["metrics"]["general_ledger_rows"] == 2
