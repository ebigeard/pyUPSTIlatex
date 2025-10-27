from typing import Iterable


def read_text_with_fallback(path, encoding="utf-8"):
    try:
        with open(path, "r", encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


def iter_lines(text: str):
    return text.splitlines(keepends=True)
