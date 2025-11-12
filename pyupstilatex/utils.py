import json
from pathlib import Path
from typing import Any, List, Optional, Union

from .exceptions import DocumentParseError


def check_types(obj: Any, expected_types: Union[str, List[str]]) -> bool:
    """
    Vérifie si `obj` est du type indiqué par `expected_types` (str ou liste de str).
    Exemple:
      check_types("abc", "str")         -> True
      check_types(123, "text")          -> True
      check_types(3.14, ["str", "text"]) -> True
    """
    type_map = {
        "str": str,
        "int": int,
        "float": float,
        "dict": dict,
        "list": list,
        "tuple": tuple,
        "bool": bool,
        "set": set,
        "text": (str, int, float),
    }

    if isinstance(expected_types, str):
        expected_types = [expected_types]

    for type_name in expected_types:
        cls = type_map.get(type_name)
        if cls and isinstance(obj, cls):
            return True

    return False


def read_json_config(path: Optional[Path | str] = None) -> dict:
    """Lit le fichier JSON de configuration et le retourne sous forme de dictionnaire.

    Si 'path' est None, résout le fichier JSON embarqué `pyUPSTIlatex.json` situé à la racine du package (un niveau au-dessus de ce module).
    """
    try:
        if path is None:
            json_path = Path(__file__).resolve().parents[1] / "pyUPSTIlatex.json"
        else:
            json_path = Path(path)
        with json_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise DocumentParseError(
            f"Impossible de lire le fichier JSON de config {json_path}: {e}"
        )
