from pathlib import Path
from typing import List


def check_path_readable(path: str) -> tuple[bool, List[List[str]]]:
    """Vérifie qu'un chemin existe, est un fichier et est lisible.

    Retourne un triplet (ok, raison, flag) où:
    - ok: True si accessible, False sinon
    - raison: None si ok, sinon un message court expliquant l'erreur
    - flag: None si ok, sinon 'error'
    """
    p = Path(path)
    if not p.exists():
        return False, [["Fichier introuvable", "error"]]
    if not p.is_file():
        return False, [["N'est pas un fichier", "error"]]
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
            return False, [[f"Impossible de lire: {e}", "error"]]
        else:
            return True, [["Fichier lu en latin-1 (fallback d'encodage)", "warning"]]
    except Exception as e:
        return False, [[f"Impossible de lire: {e}", "error"]]
    return True, None, None


def check_path_writable(path: str) -> tuple[bool, List[List[str]]]:
    """Vérifie qu'un chemin de fichier existant est ouvrable en écriture.

    - Retourne (True, None, None) si le fichier existe et peut être ouvert en écriture.
    - Sinon (False, erreur). N'essaie PAS de créer le fichier s'il n'existe pas.
    """
    p = Path(path)
    if not p.exists():
        return False, [["Fichier introuvable", "error"]]
    if not p.is_file():
        return False, [["N'est pas un fichier", "error"]]
    try:
        # 'r+b' requiert que le fichier existe et autorise l'écriture sans le tronquer
        with p.open("r+b") as _:
            pass
    except PermissionError as e:
        return False, [[f"Permission refusée: {e}", "error"]]
    except Exception as e:
        return False, [[f"Impossible d'ouvrir en écriture: {e}", "error"]]
    return True, None, None
