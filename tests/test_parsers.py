import pytest
from pyupstilatex.parsers import parse_yaml_front_matter, parse_named_zones, parse_tex_commands


def test_yaml():
    t = "---\ntitle: Test\nauthor: Someone\n---\n\\section{A}\n"
    meta = parse_yaml_front_matter(t)
    assert meta["title"] == "Test"
    assert meta["author"] == "Someone"


def test_zone():
    t = "%### BEGIN foo ###\n% line1\n% line2\n%### END foo ###\n"
    zones = parse_named_zones(t)
    assert "foo" in zones
    assert "line1" in zones["foo"][0]


def test_commands_simple():
    t = "\\titre{Mon titre} texte \\flagcmd \\auteur{Nom}"
    cmds = parse_tex_commands(t)
    assert cmds["titre"][0] == "Mon titre"
    assert "flagcmd" in cmds
    assert cmds["flagcmd"][0] is None
