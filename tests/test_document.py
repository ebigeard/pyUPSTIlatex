from pyupstilatex.document import UPSTILatexDocument


def test_from_string_and_metadata():
    content = "---\ntitle: X\n---\n\\titre{T}\n%### BEGIN z ###\n% hello\n%### END z ###\n"
    doc = UPSTILatexDocument.from_string(content)
    assert doc.metadata["title"] == "X"
    assert doc.get_commands()["titre"][0] == "T"
    assert "z" in doc.list_zones()
    assert "hello" in doc.get_zone("z")
