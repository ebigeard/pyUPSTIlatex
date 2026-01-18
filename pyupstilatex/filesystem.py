import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .config import load_config
from .exceptions import DocumentParseError
from .storage import FileSystemStorage, StorageProtocol
from .utils import check_path_readable, check_path_writable


@dataclass
class DocumentFile:
    """
    Gère les aspects système de fichiers d'un document :
    - Existence, lisibilité, écriture
    - Détection d'encodage et de fichiers binaires
    - Lecture avec fallback d'encodage
    """

    source: str
    storage: StorageProtocol = field(default_factory=FileSystemStorage)
    strict: bool = False
    require_writable: bool = False

    # États du fichier
    _file_exists: Optional[bool] = field(default=None, init=False)
    _file_readable: Optional[bool] = field(default=None, init=False)
    _file_readable_reason: Optional[str] = field(default=None, init=False)
    _file_readable_flag: Optional[str] = field(default=None, init=False)
    _file_writable: Optional[bool] = field(default=None, init=False)
    _file_writable_reason: Optional[str] = field(default=None, init=False)
    _read_encoding: Optional[str] = field(default=None, init=False)
    _raw: Optional[str] = field(default=None, init=False)

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
                        else:
                            # Seuil simple: présence d'un octet nul => binaire
                            is_binary = b"\x00" in sample

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
        except DocumentParseError:
            raise
        except Exception:
            # Ne bloque jamais l'instanciation en cas d'erreur inattendue
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
    def read_encoding(self) -> Optional[str]:
        return self._read_encoding

    @property
    def path(self) -> Path:
        """Retourne le Path du fichier source."""
        return Path(self.source)

    @property
    def parent(self) -> Path:
        """Retourne le dossier parent du fichier source."""
        return Path(self.source).parent

    @property
    def stem(self) -> str:
        """Retourne le nom du fichier sans extension."""
        return Path(self.source).stem

    @property
    def suffix(self) -> str:
        """Retourne l'extension du fichier (avec le point)."""
        return Path(self.source).suffix

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

    def read(self) -> str:
        """Lit et retourne le contenu du fichier."""
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


def scan_for_documents(
    root_paths: Optional[Union[str, List[str]]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Scanne un ouplusieurs dossiers à la recherche de fichiers tex compatibles.

    Args:
        root_paths: Le(s) chemin(s) du/des dossier(s) à scanner.
                    Si None, utilise TRAITEMENT_PAR_LOT_DOSSIERS_A_TRAITER du .env
        exclude_patterns: Motifs d'exclusion (glob).
                         Si None, utilise TRAITEMENT_PAR_LOT_FICHIERS_A_EXCLURE du .env

    Returns:
        Un tuple (found_documents, errors) où :
            - found_documents: liste de dicts avec :
                'name', 'filename', 'path', 'version', 'display_path'
            - errors: liste de messages d'erreurs
    """
    # Import ici pour éviter l'import circulaire
    from .document import UPSTILatexDocument

    errors: List[str] = []
    cfg = load_config()

    # Utiliser les valeurs du .env si non spécifiées
    if root_paths is None:
        roots = list(cfg.traitement_par_lot.dossiers_a_traiter)
    elif isinstance(root_paths, (str, Path)):
        roots = [str(root_paths)]
    else:
        roots = list(root_paths)

    if exclude_patterns is None:
        exclude_patterns = list(cfg.traitement_par_lot.fichiers_a_exclure)

    if not roots:
        errors.append(
            "Aucun dossier spécifié et aucune variable d'environnement définie."
        )
        return [], errors

    exclude_patterns = exclude_patterns or []

    found_documents: List[Dict[str, str]] = []

    for root in roots:
        if not os.path.isdir(root):
            message = f"Le dossier spécifié n'existe pas : {root}"
            errors.append(message)
            # skip this root and continue with others
            continue

        p = Path(root)
        tex_files = list(p.rglob("*.tex")) + list(p.rglob("*.ltx"))

        for file_path in tex_files:
            # Apply exclude patterns on filename and relative path
            rel = None
            try:
                rel = file_path.relative_to(p)
            except Exception:
                rel = file_path.name
            rel_str = str(rel)
            should_exclude = False
            for pat in exclude_patterns:
                if fnmatch.fnmatch(file_path.name, pat) or fnmatch.fnmatch(
                    rel_str, pat
                ):
                    should_exclude = True
                    break
            if should_exclude:
                continue

            # from_path now returns (doc, errors). Handle errors and missing doc.
            doc, doc_errors = UPSTILatexDocument.from_path(str(file_path))
            if doc_errors:
                for derr in doc_errors:
                    # derr is expected to be a [message, flag] pair
                    msg_text = f"Erreur lors de la lecture de {file_path}: {derr[0]}"
                    errors.append(msg_text)
                continue
            if doc is None:
                errors.append(f"Impossible d'initialiser le document: {file_path}")
                continue

            if not doc.is_readable:
                # Raison lisible depuis l'objet document
                reason = getattr(doc, "readable_reason", None) or ""
                flag = getattr(doc, "readable_flag", None) or ""
                msg_text = f"Fichier illisible : {file_path}"
                if reason:
                    msg_text = f"{msg_text} — {reason}"
                if flag:
                    msg_text = f"{msg_text} (flag: {flag})"
                errors.append(msg_text)
                continue

            version, local_errors = doc.get_version()

            if version in {"UPSTI_Document_v1", "UPSTI_Document_v2", "EPB_Cours"}:
                # Récupérer le paramètre de compilation
                a_compiler = False
                try:
                    params, _ = doc.get_compilation_parameters()
                    if params:
                        a_compiler = bool(params.get("compiler", False))
                except Exception:
                    pass  # En cas d'erreur, on garde False par défaut

                found_documents.append(
                    {
                        "name": file_path.stem,
                        "filename": file_path.name,
                        "path": str(file_path.resolve()),
                        "version": version,
                        "a_compiler": a_compiler,
                    }
                )

    # Ajouter les chemins tronqués
    _add_truncated_paths(found_documents)

    return found_documents, errors


def _add_truncated_paths(documents: List[Dict[str, str]], max_length: int = 88) -> None:
    """
    Ajoute une clé 'display_path' à chaque dict, contenant le chemin tronqué à
    max_length caractères.
    Modifie la liste en place.
    """
    if not documents:
        return

    for doc in documents:
        full_path = doc["path"]

        if len(full_path) <= max_length:
            doc["display_path"] = full_path
            continue

        # Récupérer le premier dossier et le nom du fichier
        parts = full_path.replace("/", "\\").split("\\")
        if len(parts) <= 2:
            doc["display_path"] = full_path
            continue

        first_part = parts[0]
        last_part = parts[-1]

        # Construire le chemin tronqué: "first_part\...\last_part"
        truncated = f"{first_part}\\...\\{last_part}"

        # Calculer l'espace disponible pour les chemins intermédiaires
        if len(truncated) <= max_length:
            # Ajouter progressivement des dossiers intermédiaires si nécessaire
            available = (
                max_length - len(first_part) - len(last_part) - 4
            )  # -4 pour "\...\\"
            if available > 0:
                # Ajouter des dossiers depuis la fin vers l'avant
                middle_parts = parts[1:-1]
                middle_str = ""
                for i in range(len(middle_parts) - 1, -1, -1):
                    test_str = f"{middle_parts[i]}\\" + middle_str
                    if len(test_str) <= available - 3:  # -3 pour "..."
                        middle_str = test_str
                    else:
                        break

                if middle_str:
                    truncated = f"{first_part}\\...\\{middle_str}{last_part}"

        doc["display_path"] = truncated


def add_display_paths(documents: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Ajoute une clé 'display_path' à chaque dict, contenant le chemin relatif
    par rapport au chemin commun de tous les documents.
    """
    if not documents:
        return documents

    # Extraire tous les chemins
    paths = [d["path"] for d in documents]

    # Trouver le chemin commun
    common = os.path.commonpath(paths)

    # Ajouter display_path
    for d in documents:
        d["display_path"] = os.path.relpath(d["path"], common)

    return documents
