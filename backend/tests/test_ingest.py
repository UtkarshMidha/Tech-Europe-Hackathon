import io
import zipfile
from pathlib import Path

from backend.app import _extract_zip
from backend.ingest import docx_passages, office_media, office_tables, pptx_passages


def _package(path: Path, files: dict[str, str | bytes]) -> None:
    with zipfile.ZipFile(path, "w") as package:
        for name, value in files.items():
            package.writestr(name, value)


def test_office_text_tables_and_embedded_images_are_normalized(tmp_path: Path):
    docx = tmp_path / "renamed.docx"
    _package(docx, {
        "word/document.xml": """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Payment approval from 10000 EUR</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Amount</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>User</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>10</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>U1</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>""",
        "word/media/image1.png": b"image",
    })
    pptx = tmp_path / "renamed.pptx"
    _package(pptx, {
        "ppt/slides/slide1.xml": """<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><a:t>Vendor control</a:t><a:tbl><a:tr><a:tc><a:t>Vendor</a:t></a:tc><a:tc><a:t>Bank</a:t></a:tc></a:tr><a:tr><a:tc><a:t>V1</a:t></a:tc><a:tc><a:t>DE1</a:t></a:tc></a:tr></a:tbl></p:cSld></p:sld>""",
        "ppt/media/image1.jpg": b"image",
    })

    assert docx_passages(docx)[0][0] == "Payment approval from 10000 EUR"
    assert pptx_passages(pptx)[0] == ("Vendor control Vendor Bank V1 DE1", "slide", {"slide": 1})
    tables = office_tables(tmp_path)
    assert any(table["rows"] == [["Amount", "User"], ["10", "U1"]] for table in tables)
    assert any(table["rows"] == [["Vendor", "Bank"], ["V1", "DE1"]] for table in tables)
    assert {item["path"].name for item in office_media(tmp_path)} == {"renamed.docx", "renamed.pptx"}


def test_markdown_json_xml_tables_and_nested_zip_are_discovered(tmp_path: Path):
    (tmp_path / "data.md").write_text("| Amount | User |\n|---|---|\n| 10 | U1 |", encoding="utf-8")
    (tmp_path / "data.json").write_text('[{"Amount": 20, "User": "U2"}]', encoding="utf-8")
    (tmp_path / "data.xml").write_text("<root><row><Amount>30</Amount><User>U3</User></row></root>", encoding="utf-8")
    tables = office_tables(tmp_path)
    assert {table["file"] for table in tables} == {"data.md", "data.json", "data.xml"}

    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as package:
        package.writestr("ledger.csv", "a;b\n1;2")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as package:
        package.writestr("folder/inner.zip", inner.getvalue())
    count, _ = _extract_zip(outer.getvalue(), tmp_path / "nested", 100)
    assert count == 1
    assert (tmp_path / "nested/folder/inner/ledger.csv").exists()
