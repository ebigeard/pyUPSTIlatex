from typing import Any, List, Union


def check_types(obj: Any, expected_types: Union[str, List[str]]) -> bool:
    """Vérifie si un objet correspond à un ou plusieurs types attendus.

    Supporte des types standards et des types étendus (ex: "text" pour str/int/float).

    Paramètres
    ----------
    obj : Any
        L'objet à vérifier.
    expected_types : str | List[str]
        Type(s) attendu(s). Peut être une chaîne unique ou une liste de chaînes.
        Types supportés : 'str', 'int', 'float', 'dict', 'list', 'tuple', 'bool',
        'set', 'text' (str, int ou float).

    Retourne
    --------
    bool
        True si l'objet correspond à au moins un des types attendus, False sinon.

    Exemples
    --------
    >>> check_types("abc", "str")
    True
    >>> check_types(123, "text")
    True
    >>> check_types(3.14, ["str", "text"])
    True
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
