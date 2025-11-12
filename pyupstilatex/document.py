import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from .exceptions import DocumentParseError
from .filesystem import check_path_readable, check_path_writable
from .parsers import (
    parse_metadonnees_tex,
    parse_metadonnees_yaml,
    parse_package_imports,
)
from .storage import FileSystemStorage, StorageProtocol
from .utils import check_types, read_json_config


@dataclass
class UPSTILatexDocument:
    source: str
    storage: StorageProtocol = field(default_factory=FileSystemStorage)
    strict: bool = False
    require_writable: bool = False
    _raw: Optional[str] = field(default=None, init=False)
    _metadata: Optional[Dict] = field(default=None, init=False)
    _commands: Optional[Dict] = field(default=None, init=False)
    _zones: Optional[Dict] = field(default=None, init=False)
    _version: Optional[str] = field(default=None, init=False)
    _file_exists: Optional[bool] = field(default=None, init=False)
    _file_readable: Optional[bool] = field(default=None, init=False)
    _file_readable_reason: Optional[str] = field(default=None, init=False)
    _file_readable_flag: Optional[str] = field(default=None, init=False)
    _file_writable: Optional[bool] = field(default=None, init=False)
    _file_writable_reason: Optional[str] = field(default=None, init=False)
    _read_encoding: Optional[str] = field(default=None, init=False)

    def __post_init__(self):
        """Initialise les états du fichier selon le type de stockage."""
        try:
            # Cas 1 : stockage local — on peut faire des tests système explicites
            if isinstance(self.storage, FileSystemStorage):
                p = Path(self.source)
                self._file_exists = p.is_file()

                # Refuse explicitement tout fichier qui n'est pas un .tex ou un .ltx
                if p.suffix.lower() not in [".tex", ".ltx"]:
                    self._file_readable = False
                    self._file_readable_reason = "Le fichier n'est pas un fichier tex"
                    self._file_readable_flag = "fatal_error"
                    # Écriture : si le fichier existe on indique l'état,
                    # sinon on signale inexistant
                    if self._file_exists:
                        ok_w, reason_w, _ = check_path_writable(self.source)
                        self._file_writable = bool(ok_w)
                        self._file_writable_reason = reason_w
                    else:
                        self._file_writable = False
                        self._file_writable_reason = "Fichier inexistant"
                else:
                    # Petit test heuristique pour repérer les binaires
                    try:
                        with p.open("rb") as f:
                            sample = f.read(4096)
                    except Exception as e:
                        # Impossible d'ouvrir en binaire -> on considèrera illisible
                        self._file_readable = False
                        self._file_readable_reason = f"Lecture binaire impossible: {e}"
                        self._file_readable_flag = "fatal_error"
                        self._file_writable = None
                        self._file_writable_reason = None
                    else:
                        if not sample:
                            # Fichier vide -> considérer lisible (UTF-8)
                            is_binary = False
                        elif b"\x00" in sample:
                            is_binary = True
                        else:
                            # Heuristique : ratio d'octets imprimables
                            printable = 0
                            for b in sample:
                                if b in (9, 10, 13) or 32 <= b <= 126:
                                    printable += 1
                            non_printable_ratio = 1 - (printable / len(sample))
                            is_binary = non_printable_ratio > 0.30

                        if is_binary:
                            self._file_readable = False
                            self._file_readable_reason = "Fichier binaire détecté"
                            self._file_readable_flag = "fatal_error"
                            # Écriture : on laisse l'état vérifié si possible
                            if self._file_exists:
                                ok_w, reason_w, _ = check_path_writable(self.source)
                                self._file_writable = bool(ok_w)
                                self._file_writable_reason = reason_w
                            else:
                                self._file_writable = False
                                self._file_writable_reason = "Fichier inexistant"
                        else:
                            # Texte plausible -> faire la vérification d'encodage
                            ok_r, reason_r, flag_r = check_path_readable(self.source)
                            self._file_readable = bool(ok_r)
                            self._file_readable_reason = reason_r
                            self._file_readable_flag = flag_r
                            if flag_r == "warning":
                                # mémoriser l'encodage fallback pour read()
                                self._read_encoding = "latin-1"
                            # Écriture
                            self._file_writable, self._file_writable_reason, _ = (
                                check_path_writable(self.source)
                                if self._file_exists
                                else (False, "Fichier inexistant", "fatal_error")
                            )

            # Cas 2 : stockage distant — on ne peut que tester par lecture réelle
            else:
                try:
                    _ = self.storage.read_text(self.source)
                    self._file_exists = True
                    self._file_readable = True
                    self._file_readable_reason = None
                    self._file_readable_flag = None
                except UnicodeDecodeError as e:
                    self._file_exists = True
                    self._file_readable = False
                    self._file_readable_reason = f"Encodage illisible: {e}"
                    self._file_readable_flag = "fatal_error"
                except Exception as e:
                    self._file_exists = False
                    self._file_readable = False
                    self._file_readable_reason = f"Lecture impossible: {e}"
                    self._file_readable_flag = "fatal_error"

                # Écriture non testable pour les storages distants
                self._file_writable = None
                self._file_writable_reason = None

            # Pré-détection de la version si lisible
            if self._file_readable:
                try:
                    v, _msg, _flag = self.get_version()
                    # _version est déjà mis à jour par get_version()
                except Exception:
                    pass

            # Mode strict : on lève des erreurs précises si accès impossible
            if self.strict:
                if not self._file_exists:
                    raise DocumentParseError(
                        f"Fichier introuvable ou non fichier: {self.source}"
                    )
                if not self._file_readable:
                    raise DocumentParseError(
                        f"Fichier illisible: {self.source} — "
                        f"{self._file_readable_reason or 'raison inconnue'}"
                    )
                if self.require_writable:
                    if self._file_writable is True:
                        pass
                    elif self._file_writable is False:
                        raise DocumentParseError(
                            f"Fichier non ouvrable en écriture: {self.source} "
                            f"— {self._file_writable_reason or 'raison inconnue'}"
                        )
                    else:
                        raise DocumentParseError(
                            f"Capacité d'écriture non vérifiable pour ce stockage: "
                            f"{self.source}"
                        )
        except Exception:
            # Ne bloque jamais l’instanciation en cas d’erreur inattendue
            pass

    # Propriétés d'accès simples
    @property
    def exists(self) -> bool:
        return bool(self._file_exists)

    @property
    def is_readable(self) -> bool:
        return bool(self._file_readable)

    @property
    def is_writable(self) -> bool:
        return bool(self._file_writable)

    @property
    def readable_reason(self) -> Optional[str]:
        return self._file_readable_reason

    @property
    def readable_flag(self) -> Optional[str]:
        return self._file_readable_flag

    @property
    def writable_reason(self) -> Optional[str]:
        return self._file_writable_reason

    @property
    def version(self):
        if self._version is not None:
            return self._version
        return self.get_version()[0]

    @property
    def metadata(self) -> Dict:
        if self._metadata is not None:
            return self._metadata
        return self.get_metadata()[0]

    def check_file(self, mode: str = "read") -> tuple[bool, List[List[str]]]:
        """Vérifie rapidement l'état du fichier selon le mode demandé.

        Retourne (ok, raison, flag) où:
        - ok: True si tout est OK pour le mode demandé
        - liste de messages d'erreurs (msg, flag).

        Modes supportés:
        - 'read'  : existence + readable (UTF-8) ; si fallback latin-1 => warning
        - 'write' : existence + writable (test non destructif pour FileSystemStorage)
        - 'exists': existence seulement
        """
        mode = (mode or "read").lower()
        if mode not in ("read", "write", "exists"):
            return False, [
                ["Mode doit être 'read', 'write' ou 'exists'.", "fatal_error"]
            ]

        # Existence
        if not self._file_exists:
            return False, [["Fichier introuvable", "fatal_error"]]

        if mode == "exists":
            return True, []

        # Mode lecture
        if mode == "read":
            # readable_flag may be 'warning' when latin-1 fallback used
            if self._file_readable:
                if self._file_readable_flag == "warning":
                    return (
                        True,
                        [
                            [
                                self._file_readable_reason
                                or "Fichier lu avec fallback d'encodage",
                                "warning",
                            ]
                        ],
                    )
                return True, []
            return False, [
                [
                    self._file_readable_reason or "Impossible de lire",
                    self._file_readable_flag or "error",
                ]
            ]

        # Mode écriture
        if self._file_writable is True:
            return True, []
        if self._file_writable is False:
            return (
                False,
                [
                    [
                        self._file_writable_reason or "Impossible d'ouvrir en écriture",
                        "fatal_error",
                    ]
                ],
            )
        # None => inconnu pour les storages non locaux
        return (
            False,
            [
                [
                    self._file_writable_reason
                    or "Capacité d'écriture non vérifiable pour ce stockage",
                    "warning",
                ]
            ],
        )

    def get_yaml_metadata(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Extrait les métadonnées depuis le front matter YAML.

        Retourne (metadata, [message, flag]).
        """
        try:
            data, errors = parse_metadonnees_yaml(self.read()) or {}
            return data, errors
        except Exception as e:
            return None, [[f"Erreur de lecture des métadonnées YAML: {e}", "error"]]

    def get_tex_metadata(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Extrait les métadonnées depuis les commandes LaTeX (v1).

        Retourne (metadata, [message, flag]).
        """
        try:
            data, parsing_errors = parse_metadonnees_tex(self.read()) or {}
            version_warning = [
                [
                    "Ce document utilise une ancienne version de UPSTI_Document (v1). "
                    "Mettre à jour UPSTI_Document: pyupstilatex upgrade",
                    "info",
                ]
            ]
            return data, version_warning + parsing_errors
        except Exception as e:
            return None, [[f"Erreur de lecture des métadonnées LaTeX: {e}", "error"]]

    def get_metadata(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Retourne (metadata, message, flag) en fonction de la version du document."""
        # Réutiliser le cache si les métadonnées ont déjà été extraites
        if self._metadata is not None:
            return self._metadata, []

        # On reprend la version détectée, et on exécute le parser qui correspond
        version = self._version or self.version
        if version == "EPB_Document":
            return (
                None,
                [
                    [
                        "Les fichiers EPB_Document ne sont pas pris en charge "
                        "par pyUPSTIlatex.",
                        "error",
                    ],
                ],
            )

        # Associer chaque version à sa fonction de récupération
        sources = {
            "UPSTI_Document_v1": self.get_tex_metadata,
            "UPSTI_Document_v2": self.get_yaml_metadata,
        }

        if version in sources:
            metadata, errors = sources[version]()

            formatted, formatted_errors = self._format_metadata(
                metadata, source=version
            )
            if formatted is not None:
                self._metadata = formatted
            return formatted, errors + formatted_errors

        # Version non reconnue
        return (
            None,
            [["Type de document non pris en charge par pyUPSTIlatex", "error"]],
        )

    def get_version(self) -> tuple[Optional[str], List[List[str]]]:
        """Détecte la version du document UPSTI/EPB et retourne (version, erreurs)."""

        if self._version is not None:
            # Version déjà détectée (cache)
            return self._version, []

        try:
            content = self.read()
            packages = parse_package_imports(content)

            if "UPSTI_Document" in packages:
                self._version = "UPSTI_Document_v1"
                return self._version, []
            if "EPB_Document" in packages:
                self._version = "EPB_Document"
                return self._version, []

        except Exception as e:
            return None, [[f"Impossible de lire le fichier: {e}", "error"]]

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # UPSTI_Document v2 (ligne commençant par % mais pas %%)
            if stripped.startswith("%") and not stripped.startswith("%%"):
                if "%### BEGIN metadonnees_yaml ###" in stripped:
                    self._version = "UPSTI_Document_v2"
                    return self._version, []

            # Ignorer lignes commentées pour EPB/v1
            if stripped.startswith("%"):
                continue

        self._version = None
        return None, [["Version non reconnue", "warning"]]

    def _format_metadata(
        self, data: Dict, *, source: str
    ) -> Tuple[Dict, List[List[str]]]:
        """Nettoie/normalise les métadonnées parsées avant mise en cache et retour.

        Retourne (dict Python, liste de messages d'erreurs (msg, flag)).
        """
        if data is None:
            data = {}

        meta_ok: Dict[str, Dict] = {}
        errors: List[Tuple[str, str]] = []
        cfg = read_json_config()
        cfg_meta = cfg.get("metadonnee") or {}

        # On prépare toutes les valeurs par défaut globales
        epoch = int(time.time())
        prefixe_id = os.getenv("META_DEFAULT_ID_DOCUMENT_PREFIXE", "EB")
        separateur_id = os.getenv("META_DEFAULT_SEPARATEUR_ID_DOCUMENT", ":")

        valeurs_par_defaut = {
            "id_unique": f"{prefixe_id}{separateur_id}{epoch}",
            "variante": os.getenv("META_DEFAULT_VARIANTE", "upsti"),
            "matiere": os.getenv("META_DEFAULT_MATIERE", "S2I"),
            "classe": os.getenv("META_DEFAULT_CLASSE", "PT"),
            "type_document": os.getenv("META_DEFAULT_TYPE_DOCUMENT", "cours"),
            "titre": os.getenv("META_DEFAULT_TITRE", "Titre par défaut"),
            "version": os.getenv("META_DEFAULT_VERSION", "0.1"),
            "auteur": os.getenv("META_DEFAULT_AUTEUR", "Emmanuel BIGEARD"),
        }

        # Préparation des champs déclarés et par défaut
        for key, meta in cfg_meta.items():
            params = meta.get("parametres", {})
            if key not in data and not params.get("default"):
                continue

            meta_ok[key] = {
                "label": meta.get("label", "Erreur"),
                "description": meta.get("description", "Erreur"),
                "valeur": "",
                "affichage": "",
                "initiales": "",
                "raw_value": data.get(key, "") if data else "",
                "initial_value": data.get(key, "") if data else "",
                "parametres": params,
                **(
                    {"type_meta": "default"}
                    if params.get("default") and key not in data
                    else {}
                ),
            }

        # 1. On vérifie s'il y a des champs surnuméraires définis par mégarde
        for key in data:
            if key not in cfg_meta:
                errors.append(
                    [
                        f"Clé de métadonnée inconnue dans le fichier tex: '{key}'.",
                        "warning",
                    ]
                )

        # 2. On verifie la correspondance des types de données
        for key, meta in meta_ok.items():
            params = meta.get("parametres", {})
            types_to_check = params.get("accepted_types", [])
            raw_value = meta.get("raw_value", "")

            if check_types(raw_value, types_to_check):
                continue

            use_default = bool(params.get("default"))
            self._handle_invalid_meta(
                meta,
                key,
                f"'{key}' devrait être de type {types_to_check}.",
                use_default,
                errors,
                suffix="wrong_type",
            )

        # 3. On vérifie les contraintes spécifiques à certains champs
        for key, meta in meta_ok.items():
            params = meta.get("parametres", {})
            rules = params.get("validate_rules", {})
            raw_value = meta.get("raw_value", {})

            if not rules:
                continue

            use_default = bool(params.get("default"))

            # Règle : dict_keys - les clés doivent être dans une liste définie
            if "dict_keys" in rules and isinstance(raw_value, dict):
                allowed_keys = set(rules["dict_keys"])
                actual_keys = set(raw_value.keys())
                invalid_keys = actual_keys - allowed_keys
                if invalid_keys:
                    self._handle_invalid_meta(
                        meta,
                        key,
                        f"Clé(s) non autorisée(s) pour '{key}': {list(invalid_keys)}.",
                        use_default,
                        errors,
                        suffix="validate_rules",
                    )

            # Règle : keys_in - les clés doivent appartenir aux clés d'un modèle
            if "keys_in" in rules and isinstance(raw_value, dict):
                path = str(rules["keys_in"]).split(".")
                source = cfg
                for p in path:
                    source = source.get(p, {})
                allowed_keys = set(source.keys())
                actual_keys = set(raw_value.keys())

                invalid_keys = actual_keys - allowed_keys
                if invalid_keys:
                    self._handle_invalid_meta(
                        meta,
                        key,
                        f"Clé(s) non autorisée(s) pour '{key}': {list(invalid_keys)}.",
                        use_default,
                        errors,
                        suffix="validate_rules",
                    )

            # Règle : value_type - les valeurs des différentes clés doivent être typées
            if "value_type" in rules and isinstance(raw_value, dict):
                types_to_check = rules["value_type"]
                if not isinstance(types_to_check, list):
                    types_to_check = [types_to_check]

                invalid_values = [
                    v for v in raw_value.values() if not check_types(v, types_to_check)
                ]

                if invalid_values:
                    reason = (
                        f"Les valeurs de '{key}' doivent être de type "
                        f"{types_to_check}."
                    )
                    self._handle_invalid_meta(
                        meta,
                        key,
                        reason,
                        use_default,
                        errors,
                        suffix="validate_rules",
                    )

            # Règle : extended_types - vérifie les types d'un dictionnaire hétérogène
            if "extended_types" in rules and isinstance(raw_value, dict):
                type_schema = rules["extended_types"]
                for sub_key, expected_type in type_schema.items():
                    if sub_key in raw_value:
                        sub_value = raw_value[sub_key]
                        if not check_types(sub_value, [expected_type]):
                            self._handle_invalid_meta(
                                meta,
                                key,
                                f"La clé '{sub_key}' dans '{key}' a un type invalide. "
                                f"Attendu: {expected_type}, "
                                f"Reçu: {type(sub_value).__name__}.",
                                use_default,
                                errors,
                                suffix="validate_rules",
                            )

            # Règle : sum - valeurs numériques doivent sommer à une valeur donnée
            if "sum" in rules and isinstance(raw_value, dict):
                total = sum(int(v) for v in raw_value.values())
                expected_total = rules["sum"]
                if total != expected_total:
                    self._handle_invalid_meta(
                        meta,
                        key,
                        f"Le total des valeurs de '{key}' doit faire {expected_total}.",
                        use_default,
                        errors,
                        suffix="validate_rules",
                    )

            # Règle : valeur_max - valeurs doivent être inférieures à une valeur donnée
            if "valeur_max" in rules and isinstance(raw_value, int):
                max_value = rules["valeur_max"]
                if raw_value > max_value:
                    self._handle_invalid_meta(
                        meta,
                        key,
                        f"'{key}' doit être inférieur ou égal à : {max_value}.",
                        use_default,
                        errors,
                        suffix="validate_rules",
                    )

            # Règle : in - les valeurs doivent être dans une liste définie
            if "in" in rules and isinstance(raw_value, list):
                path = str(rules["in"]).split(".")
                source = cfg.get(path[0], {})

                if len(path) == 1:
                    invalid = [v for v in raw_value if v not in source]
                elif len(path) == 2:
                    sub_key = path[1]
                    valid_values = {
                        item.get(sub_key)
                        for item in source.values()
                        if isinstance(item, dict)
                    }
                    invalid = [v for v in raw_value if v not in valid_values]
                else:
                    invalid = raw_value  # fallback total

                if invalid:
                    self._handle_invalid_meta(
                        meta,
                        key,
                        f"Valeur(s) non autorisée(s) pour '{key}': {invalid}.",
                        use_default,
                        errors,
                        suffix="validate_rules",
                    )

        # 4. Gestion des valeurs custom sous forme de dict.
        for key, meta in meta_ok.items():
            params = meta.get("parametres", {})
            custom_declaration = params.get("custom_declaration", {})

            if custom_declaration:
                raw_value = meta.get("raw_value", {})

                if isinstance(raw_value, dict):
                    use_default = bool(params.get("default"))

                    try:
                        custom_declaration_parsed = yaml.safe_load(custom_declaration)

                        # a. Vérifier que les clés sont identiques
                        expected_keys = set(custom_declaration_parsed.keys())
                        actual_keys = set(raw_value.keys())

                        if actual_keys != expected_keys:
                            self._handle_invalid_meta(
                                meta,
                                key,
                                f"Les clés pour '{key}' sont invalides. "
                                f"(attendu: {list(expected_keys)})",
                                use_default,
                                errors,
                                suffix="validate_rules",
                            )
                        else:
                            # b. Vérifier le type de chaque valeur
                            type_errors = []
                            for k, expected_type in custom_declaration_parsed.items():
                                actual_value = raw_value.get(k)
                                if not check_types(actual_value, [expected_type]):
                                    type_errors.append(
                                        f"'{k}' (attendu: {expected_type}, "
                                        f"obtenu: {type(actual_value).__name__})"
                                    )

                            if type_errors:
                                self._handle_invalid_meta(
                                    meta,
                                    key,
                                    f"Type(s) invalide(s) pour '{key}': "
                                    f"{', '.join(type_errors)}.",
                                    use_default,
                                    errors,
                                    suffix="validate_rules",
                                )

                    except yaml.YAMLError:
                        self._handle_invalid_meta(
                            meta,
                            key,
                            f"'custom_declaration' invalide pour '{key}' "
                            "dans pyUPSTIlatex.json.",
                            use_default,
                            errors,
                            suffix="bad_custom_declaration_definition",
                        )

        # 5. Gestion des valeurs avec des relations de clé
        for key, meta in meta_ok.items():
            params = meta.get("parametres", {})
            join_key = params.get("join_key", "")

            if join_key:
                raw_value = meta.get("raw_value", "")
                if (
                    not isinstance(raw_value, dict)
                    and raw_value != ""
                    and raw_value not in (cfg.get(key) or {})
                    and not params.get("custom_can_be_not_related", "")
                ):
                    use_default = bool(params.get("default"))
                    self._handle_invalid_meta(
                        meta,
                        key,
                        f"Valeur inconnue pour '{key}': '{raw_value}'.",
                        use_default,
                        errors,
                        suffix="bad_key",
                    )

        # 6. Application des valeurs par défaut (pour les champs required mais vides)
        for key, meta in meta_ok.items():
            if "type_meta" not in meta:
                continue

            default_mode = meta.get("parametres", {}).get("default", "")
            if default_mode == ".env":
                meta["raw_value"] = valeurs_par_defaut.get(key, "")

            elif default_mode == "calc":
                meta["raw_value"] = valeurs_par_defaut.get(key, "")

            elif default_mode == "batch_pedagogie":
                # Gestion groupée
                if not meta_ok["classe"].get("raw_value", ""):
                    meta_ok["classe"]["raw_value"] = valeurs_par_defaut["classe"]

                if not meta_ok["matiere"].get("raw_value", ""):
                    meta_ok["matiere"]["raw_value"] = valeurs_par_defaut["matiere"]

                if not meta_ok["filiere"].get("raw_value", ""):
                    cfg_classe = cfg.get("classe") or {}
                    classe_used_for_filiere = meta_ok["classe"]["raw_value"]
                    classe_predefinie = cfg_classe.get(classe_used_for_filiere, {})
                    if not classe_predefinie:
                        classe_used_for_filiere = valeurs_par_defaut["classe"]
                    meta_ok["filiere"]["raw_value"] = cfg_classe.get(
                        classe_used_for_filiere, {}
                    ).get("filiere", "")

                    if not meta_ok["filiere"].get("type_meta"):
                        meta_ok["filiere"]["type_meta"] = (
                            "deducted"
                            if meta_ok["classe"].get("type_meta", "") == ""
                            and classe_predefinie
                            else "default"
                        )

                if not meta_ok["programme"].get("raw_value", ""):
                    cfg_filiere = cfg.get("filiere") or {}
                    meta_ok["programme"]["raw_value"] = cfg_filiere.get(
                        meta_ok["filiere"]["raw_value"], {}
                    ).get("dernier_programme", "")

                    meta_ok["programme"]["type_meta"] = (
                        "deducted"
                        if meta_ok["filiere"].get("type_meta", "") in ["", "deducted"]
                        else "default"
                    )

        # 7. Finalisation des métadonnées
        for key, meta in meta_ok.items():
            raw_value = meta.get("raw_value")

            if meta.get("parametres", {}).get("join_key", False):

                # Si c'est une valeur custom
                if isinstance(raw_value, dict):
                    meta["valeur"] = raw_value.get("nom")
                    meta["affichage"] = raw_value.get("affichage", meta["valeur"])
                    meta["initiales"] = raw_value.get("initiales", meta["valeur"])
                    continue

                obj = (cfg.get(key) or {}).get(raw_value, {})
                meta["valeur"] = obj.get("nom", "")
                meta["affichage"] = obj.get("affichage", "")
                meta["initiales"] = obj.get("initiales", "")

            # Valeurs de repli
            meta["valeur"] = meta.get("valeur") or raw_value
            meta["affichage"] = meta.get("affichage") or meta["valeur"]
            meta["initiales"] = meta.get("initiales") or meta["affichage"]

        return meta_ok, errors

    def _handle_invalid_meta(
        self,
        meta: dict,
        key: str,
        reason: str,
        use_default: bool,
        errors: list,
        suffix: str = "wrong_type",
        flag: str = "",
    ):
        """
        Gère les erreurs de métadonnées : type invalide, valeur manquante, vide, etc.
        - suffix : "wrong_type", "missing", "empty", etc.
        - use_default : True → fallback, False → valeur ignorée
        """
        meta["type_meta"] = f"{'default' if use_default else 'ignored'}:{suffix}"
        meta["raw_value"] = ""
        flag = "warning" if use_default else "error"
        msg = (
            "On va utiliser la valeur par défaut."
            if use_default
            else "Métadonnée ignorée."
        )
        errors.append(
            [
                f"{reason} {msg}",
                flag,
            ]
        )

    # ================================================================================
    # TOCHECK Tout ce qui suit est généré par IA, à vérifier et comprendre
    # ================================================================================

    def read(self) -> str:
        if self._raw is None:
            try:
                # Si on détecte un encoding fallback pour le stockage local, l'utiliser
                if isinstance(self.storage, FileSystemStorage) and self._read_encoding:
                    p = Path(self.source)
                    self._raw = p.read_text(
                        encoding=self._read_encoding, errors="strict"
                    )
                else:
                    self._raw = self.storage.read_text(self.source)
            except Exception as e:
                raise DocumentParseError(f"Unable to read source {self.source}: {e}")
        return self._raw

    # def refresh(self):
    #     """Invalidate les caches internes et relire la source."""
    #     self._raw = None
    #     self._metadata = None
    #     self._commands = None
    #     self._zones = None
    #     self._version = None
    #     return self.read()

    # def get_commands(
    #     self, names: Optional[List[str]] = None
    # ) -> Dict[str, List[Optional[str]]]:
    #     if self._commands is None:
    #         self._commands = parse_tex_commands(self.read(), names=names)
    #     return self._commands

    # def list_zones(self) -> List[str]:
    #     if self._zones is None:
    #         self._zones = parse_named_zones(self.read())
    #     return list(self._zones.keys())

    # def get_zone(self, name: str):
    #     if self._zones is None:
    #         self._zones = parse_named_zones(self.read())
    #     vals = self._zones.get(name)
    #     if not vals:
    #         return None
    #     return vals if len(vals) > 1 else vals[0]

    # def to_dict(self):
    #     return {
    #         "source": self.source,
    #         "metadata": self.metadata,
    #         "commands": self.get_commands(),
    #         "zones": self._zones or parse_named_zones(self.read()),
    #     }

    @classmethod
    def from_path(
        cls,
        path: str,
        storage: Optional[StorageProtocol] = None,
        *,
        strict: bool = False,
        require_writable: bool = False,
    ):
        return cls(
            source=path,
            storage=(storage or FileSystemStorage()),
            strict=strict,
            require_writable=require_writable,
        )

    @classmethod
    def from_string(cls, content: str, *, strict: bool = False):
        inst = cls(source="<string>", storage=FileSystemStorage(), strict=strict)
        inst._raw = content
        return inst
