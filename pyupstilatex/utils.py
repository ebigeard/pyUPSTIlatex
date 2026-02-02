from pathlib import Path
from typing import Any, List, Optional, Union

# VERIFIER SI CE FICHIER EST BIEN NECESSAIRE...


# TODEL ???
def check_path_readable(path: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Vérifie qu'un chemin existe, est un fichier et est lisible (texte).

    Retourne (ok, raison, flag) où:
    - ok: True si accessible, False sinon
    - raison: None si ok, sinon un message court expliquant l'erreur/avertissement
    - flag: None, 'warning' (fallback d'encodage), ou 'fatal_error'
    """
    p = Path(path)
    if not p.exists():
        return False, "Fichier introuvable", "fatal_error"
    if not p.is_file():
        return False, "N'est pas un fichier", "fatal_error"
    try:
        # Lecture d'un octet pour forcer le décodage (et déclencher UnicodeDecodeError
        # si l'encodage est incorrect). Lire 0 octet n'effectue pas de décodage.
        with p.open("r", encoding="utf-8") as f:
            f.read(1)
    except UnicodeDecodeError:
        # Tentative de fallback en latin-1 — ne lèvera pas d'UnicodeDecodeError
        try:
            with p.open("r", encoding="latin-1") as f:
                f.read(1)
        except Exception as e:
            return False, f"Impossible de lire: {e}", "fatal_error"
        else:
            return True, "Fichier lu en latin-1 (fallback d'encodage)", "warning"
    except Exception as e:
        return False, f"Impossible de lire: {e}", "fatal_error"
    return True, None, None


# TODEL ???
def check_path_writable(path: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Vérifie qu'un chemin de fichier existant est ouvrable en écriture.

    - Retourne (True, None, None) si le fichier existe et peut être ouvert en écriture.
    - Sinon (False, erreur). N'essaie PAS de créer le fichier s'il n'existe pas.
    """
    p = Path(path)
    if not p.exists():
        return False, "Fichier introuvable", "fatal_error"
    if not p.is_file():
        return False, "N'est pas un fichier", "fatal_error"
    try:
        # 'r+b' requiert que le fichier existe et autorise l'écriture sans le tronquer
        with p.open("r+b") as _:
            pass
    except PermissionError as e:
        return False, f"Permission refusée: {e}", "fatal_error"
    except Exception as e:
        return False, f"Impossible d'ouvrir en écriture: {e}", "fatal_error"
    return True, None, None


# TODEL ???
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
