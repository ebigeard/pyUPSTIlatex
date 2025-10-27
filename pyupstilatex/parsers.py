import regex as re
import yaml
from typing import Dict, List, Optional
from .exceptions import DocumentParseError

# YAML front-matter at file start delimited by --- ... ---
YAML_FRONT_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.S)


def parse_yaml_front_matter(text: str) -> Dict:
    m = YAML_FRONT_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    try:
        data = yaml.safe_load(block) or {}
        if not isinstance(data, dict):
            raise DocumentParseError("YAML front matter is not a mapping")
        return data
    except yaml.YAMLError as e:
        raise DocumentParseError(f"YAML parse error: {e}")


def _extract_braced(text: str, start: int):
    """Return (content, end_pos) for a braced argument starting at start (pointing at '{')"""
    if start >= len(text) or text[start] != "{":
        return None, start
    depth = 0
    i = start
    L = len(text)
    while i < L:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        i += 1
    raise DocumentParseError("Unmatched brace in TeX")


CMD_RE = re.compile(r"\\(?P<name>[A-Za-z@]+)\s*", re.M)


def parse_tex_commands(text: str, names: Optional[List[str]] = None) -> Dict[str, List[Optional[str]]]:
    """
    Finds simple TeX commands. Returns dict: name -> list of arguments or None for flag commands.
    This is pragmatic and handles single braced argument per occurrence.
    """
    cmds = {}
    i = 0
    L = len(text)
    while i < L:
        m = CMD_RE.search(text, i)
        if not m:
            break
        name = m.group("name")
        i = m.end()
        arg = None
        # skip spaces
        while i < L and text[i].isspace():
            i += 1
        if i < L and text[i] == "{":
            arg, newpos = _extract_braced(text, i)
            i = newpos
        else:
            # flag-like command (no braced arg)
            arg = None
        if names is None or name in names:
            cmds.setdefault(name, []).append(arg)
    return cmds


ZONE_BEGIN_RE = re.compile(r"^\s*%+\s*###\s*BEGIN\s+(?P<name>\S+)\s*###\s*$", re.MULTILINE)
ZONE_END_RE = re.compile(r"^\s*%+\s*###\s*END\s+(?P<name>\S+)\s*###\s*$", re.MULTILINE)


def parse_named_zones(text: str, keep_comment_prefix: bool = False) -> Dict[str, List[str]]:
    """
    Detect zones delimited by comment markers:
      %### BEGIN name ###
      ...
      %### END name ###
    Returns dict name -> list of zone contents (multiple occurrences allowed).
    By default, strips leading '%' comment prefix from each line of the zone.
    """
    zones = {}
    for m in ZONE_BEGIN_RE.finditer(text):
        name = m.group("name")
        start_pos = m.end()
        # find matching END with same name after start_pos
        end_match = None
        for em in ZONE_END_RE.finditer(text, pos=start_pos):
            if em.group("name") == name:
                end_match = em
                break
        if not end_match:
            raise DocumentParseError(f"Zone {name} has no END marker")
        raw_zone = text[start_pos:end_match.start()]
        if not keep_comment_prefix:
            lines = raw_zone.splitlines()
            stripped = []
            for ln in lines:
                if ln.lstrip().startswith("%"):
                    idx = ln.find("%")
                    ln2 = ln[:idx] + ln[idx + 1 :].lstrip(" ")
                    stripped.append(ln2)
                else:
                    stripped.append(ln)
            content = "\n".join(stripped).strip("\n")
        else:
            content = raw_zone.strip("\n")
        zones.setdefault(name, []).append(content)
    return zones
