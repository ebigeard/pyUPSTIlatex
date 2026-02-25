"""Configuration management from environment variables.

This module loads secrets from custom/.env (if it exists) and configuration
from TOML files. It provides structured access to all configuration via
dataclasses, as well as low-level helpers for direct access.

Primary Usage (recommended):
    from pyupstilatex.config import load_config

    cfg = load_config()
    print(cfg.meta.auteur)                    # Métadonnées par défaut
    print(cfg.compilation.latex_nombre_compilations)  # Paramètres de compilation
    print(cfg.os.dossier_latex)               # Configuration OS/fichiers
    print(cfg.ftp.host)                       # Configuration FTP

    # Les dataclasses sont immutables (frozen=True)

Direct Access (for custom needs):
    from pyupstilatex.config import get_str, get_int, get_bool, get_path, get_list

    ftp_user = get_str("FTP_USER", default="")
    latex_recto = get_bool("POLY_RECTO_VERSO", default=True)
    nb_compil = get_int("COMPILATION_LATEX_NOMBRE_COMPILATIONS", default=2)
    dossiers = get_list("TRAITEMENT_PAR_LOT_DOSSIERS_A_TRAITER", sep=";")

Configuration Sections:
- MetaConfig: Valeurs par défaut des métadonnées documents
- CompilationConfig: Paramètres de compilation LaTeX et PDF
- OSConfig: Noms de fichiers, extensions, arborescence des dossiers
- PolyConfig: Configuration des polys (pages par feuille, recto/verso)
- TraitementParLotConfig: Dossiers à traiter et fichiers à exclure
- FTPConfig: Paramètres de connexion FTP et mode local
- SiteConfig: Configuration du site web (webhooks, URLs)
- LegacyConfig: pour la compatibilité ascendante (à supprimer à terme)

Notes:
- All values are read from os.environ at call time (no persistent cache),
  so changing env at runtime is reflected on next call.
- For booleans, accepted values: 1, true, yes, y, on; falsy: 0, false, no, n, off.
- For paths, get_path returns a pathlib.Path (no existence check).
- For lists, get_list splits by separator (default ";") and filters empty strings.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

# Support TOML pour Python 3.11+ (tomllib) et versions antérieures (tomli)
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore

__all__ = [
    "get_str",
    "get_int",
    "get_bool",
    "get_path",
    "get_list",
    # Dataclasses
    "MetaConfig",
    "CompilationConfig",
    "OSConfig",
    "PolyConfig",
    "TraitementParLotConfig",
    "FTPConfig",
    "SiteConfig",
    "LegacyConfig",
    "AppConfig",
    "load_config",
]


def get_str(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return an environment variable as string, or default if missing."""
    return os.environ.get(key, default)


def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    """Return an environment variable parsed as int, or default if invalid/missing."""
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return default


_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}


def get_bool(key: str, default: bool = False) -> bool:
    """Return an environment variable parsed as bool, or default if invalid/missing."""
    val = os.environ.get(key)
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in _TRUTHY:
        return True
    if s in _FALSY:
        return False
    # Numeric fallbacks
    try:
        return bool(int(s))
    except ValueError:
        return default


def get_path(key: str, default: Optional[str | Path] = None) -> Path:
    """Return an environment variable as Path. Uses default if missing."""
    val = os.environ.get(key)
    if val is None:
        return Path(default) if default is not None else Path()
    return Path(val)


def get_list(
    key: str, default: Optional[Iterable[str]] = None, sep: str = ";"
) -> list[str]:
    """Return an environment variable as a list of strings, split by `sep`.

    - Trims whitespace around items
    - Filters out empty segments
    - If missing, returns list(default) or []
    """
    val = os.environ.get(key)
    if val is None:
        return list(default) if default is not None else []
    parts = [p.strip() for p in val.split(sep)]
    return [p for p in parts if p]


# =========================
# TOML Configuration Loading
# =========================


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override dict into base dict recursively.

    Lists in override replace lists in base (no concatenation).
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _flatten_toml_to_env(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Convert nested TOML dict to flat ENV-style dict.

    Example:
        {"meta": {"default": {"auteur": "John"}}}
        → {"META_DEFAULT_AUTEUR": "John"}
    """
    result = {}
    for key, value in data.items():
        env_key = f"{prefix}_{key}".upper() if prefix else key.upper()

        if isinstance(value, dict):
            result.update(_flatten_toml_to_env(value, env_key))
        elif isinstance(value, list):
            # Convert list to comma-separated string
            result[env_key] = ",".join(str(v) for v in value)
        elif isinstance(value, bool):
            result[env_key] = "true" if value else "false"
        else:
            result[env_key] = str(value)

    return result


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a TOML file and return its content as dict."""
    if not tomllib:
        return {}

    if not path.exists():
        return {}

    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        # Silently ignore TOML errors to not break existing installs
        return {}


def _inject_toml_to_environ(toml_data: dict[str, Any]) -> None:
    """Inject TOML configuration into os.environ.

    TOML values always override environment variables, EXCEPT for secrets:
    - FTP_SECRET_KEY, FTP_USER, FTP_PASSWORD, FTP_HOST, FTP_PORT
    - SITE_SECRET_KEY

    These secrets may be defined in custom/.env and are never overridden
    by TOML values. Si custom/.env n'existe pas, les valeurs par défaut
    de config.py sont utilisées.
    """
    # List of secret keys that must come from .env only
    SECRET_KEYS = {
        "FTP_SECRET_KEY",
        "FTP_USER",
        "FTP_PASSWORD",
        "FTP_HOST",
        "FTP_PORT",
        "SITE_SECRET_KEY",
    }

    flat = _flatten_toml_to_env(toml_data)
    for key, value in flat.items():
        # Never override secrets from .env with TOML values
        if key in SECRET_KEYS and key in os.environ:
            continue
        # All other values: TOML takes priority
        os.environ[key] = value


def _load_config_from_toml() -> None:
    """Load TOML configuration files and inject into os.environ.

    Loading order (later overrides earlier):
    1. custom/.env for secrets (FTP_*, SITE_SECRET_KEY) — si le fichier existe
    2. pyupstilatex/config/config.default.toml (versioned defaults)
    3. custom/config.toml (local overrides, not versioned)

    Si custom/.env n'existe pas, les valeurs par défaut de config.py sont utilisées.
    """
    # Paths
    package_dir = Path(__file__).resolve().parent
    default_config_path = package_dir / "config" / "config.default.toml"
    custom_config_path = package_dir.parent / "custom" / "config.toml"
    custom_env_path = package_dir.parent / "custom" / ".env"

    # Load custom/.env for secrets FIRST (so they take priority over TOML)
    # Si le fichier n'existe pas, on utilise les valeurs par défaut de config.py
    if custom_env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(custom_env_path, override=True)
        except Exception:
            pass

    # Load default config
    default_config = _load_toml_file(default_config_path)

    # Load and merge custom config
    custom_config = _load_toml_file(custom_config_path)
    merged_config = _deep_merge(default_config, custom_config)

    # Inject into environment
    _inject_toml_to_environ(merged_config)


# =========================
# Section-based dataclasses
# =========================
@dataclass(frozen=True)
class MetaConfig:
    """Valeurs par défaut des métadonnées documents (provenant du .env)."""

    id_document_prefixe: str
    variante: str
    matiere: str
    classe: str
    type_document: str
    titre: str
    version: str
    auteur: str

    @classmethod
    def from_env(cls) -> "MetaConfig":
        return cls(
            id_document_prefixe=get_str("META_DEFAULT_ID_DOCUMENT_PREFIXE", "EB:"),
            variante=get_str("META_DEFAULT_VARIANTE", "upsti"),
            matiere=get_str("META_DEFAULT_MATIERE", "S2I"),
            classe=get_str("META_DEFAULT_CLASSE", "PT"),
            type_document=get_str("META_DEFAULT_TYPE_DOCUMENT", "cours"),
            titre=get_str("META_DEFAULT_TITRE", "Titre par défaut"),
            version=get_str("META_DEFAULT_VERSION", "0.1"),
            auteur=get_str("META_DEFAULT_AUTEUR", "Emmanuel BIGEARD"),
        )


@dataclass(frozen=True)
class CompilationConfig:
    """Valeurs par défaut pour la compilation, provenant du .env"""

    # Valeurs par défaut des paramètres de compilation
    compiler: bool
    ignorer: bool
    renommer_automatiquement: bool
    versions_a_compiler: list[str]
    versions_accessibles_a_compiler: list[str]
    est_un_document_a_trous: bool
    copier_pdf_dans_dossier_cible: bool
    upload: bool
    creer_miniature: bool
    hauteur_miniature: int
    query_webhook_apres_upload: bool
    upload_diaporama: bool
    dossier_ftp: str

    # Paramètres de compilation LaTeX
    latex_nombre_compilations: int

    # Compilation
    latex_compilateur: str
    affichage_detaille_dans_console: bool
    copier_fichier_version: bool

    @classmethod
    def from_env(cls) -> "CompilationConfig":
        return cls(
            # Defaults (from COMPILATION_DEFAUT_* env vars)
            compiler=get_bool("COMPILATION_DEFAUT_COMPILER", True),
            ignorer=get_bool("COMPILATION_DEFAUT_IGNORER", False),
            renommer_automatiquement=get_bool(
                "COMPILATION_DEFAUT_RENOMMER_AUTOMATIQUEMENT", True
            ),
            versions_a_compiler=get_list(
                "COMPILATION_DEFAUT_VERSIONS_A_COMPILER",
                default=["prof", "eleve"],
                sep=",",
            ),
            versions_accessibles_a_compiler=get_list(
                "COMPILATION_DEFAUT_VERSIONS_ACCESSIBLES_A_COMPILER",
                default=[],
                sep=",",
            ),
            est_un_document_a_trous=get_bool(
                "COMPILATION_DEFAUT_EST_UN_DOCUMENT_A_TROUS", False
            ),
            copier_pdf_dans_dossier_cible=get_bool(
                "COMPILATION_DEFAUT_COPIER_PDF_DANS_DOSSIER_CIBLE", True
            ),
            upload=get_bool("COMPILATION_DEFAUT_UPLOAD", True),
            query_webhook_apres_upload=get_bool(
                "COMPILATION_DEFAUT_QUERY_WEBHOOK_APRES_UPLOAD", False
            ),
            creer_miniature=get_bool("COMPILATION_DEFAUT_CREER_MINIATURE", False),
            hauteur_miniature=get_int("COMPILATION_DEFAUT_HAUTEUR_MINIATURE", 600),
            upload_diaporama=get_bool("COMPILATION_DEFAUT_UPLOAD_DIAPORAMA", True),
            dossier_ftp=get_str("COMPILATION_DEFAUT_DOSSIER_FTP", "/"),
            # Paramètres de compilation LaTeX
            latex_nombre_compilations=get_int(
                "COMPILATION_LATEX_NOMBRE_COMPILATIONS", 2
            ),
            latex_compilateur=get_str(
                "COMPILATION_LATEX_COMPILATEUR", "pdflatex"
            ),
            # Compilation
            affichage_detaille_dans_console=get_bool(
                "COMPILATION_AFFICHAGE_DETAILLE_DANS_CONSOLE", False
            ),
            copier_fichier_version=get_bool("COMPILATION_COPIER_FICHIER_VERSION", True),
        )


@dataclass(frozen=True)
class OSConfig:
    """Valeurs par défaut pour l'OS, provenant du .env"""

    # Fichiers et extensions
    format_nom_fichier: str
    format_nom_fichier_version: str
    nom_fichier_parametres_compilation: str
    nom_fichier_qrcode: str
    nom_fichier_yaml_poly: str
    extension_fichier_infos_upload: str
    extensions_diaporama: list[str]
    suffixe_nom_fichier_prof: str
    suffixe_nom_fichier_a_trous: str
    suffixe_nom_fichier_diaporama: str
    suffixe_nom_fichier_sources: str
    suffixe_nom_thumbnail: str
    suffixe_nom_fichier_poly: str

    # Dossiers et arborescence
    dossier_cours: str
    dossier_td: str
    dossier_cible_par_rapport_au_fichier_tex: str
    dossier_latex: str
    dossier_latex_build: str
    dossier_latex_sources: str
    dossier_latex_sources_images: str
    dossier_tmp_pour_zip: str
    dossier_poly: str
    dossier_poly_backup_yaml: str
    dossier_poly_page_de_garde: str

    @classmethod
    def from_env(cls) -> "OSConfig":
        return cls(
            # Fichiers et extensions
            format_nom_fichier=get_str(
                "OS_FORMAT_NOM_FICHIER",
                "[thematiques.code|upper]-[classe.niveau|upper]-[type_document.initiales|upper]-[titre_ou_titre_activite|slug]",
            ),
            format_nom_fichier_version=get_str(
                "OS_FORMAT_NOM_FICHIER_VERSION", "@_v[numero_version].ver"
            ),
            nom_fichier_parametres_compilation=get_str(
                "OS_NOM_FICHIER_PARAMETRES_COMPILATION", "@parametres.pyUPSTIlatex.yaml"
            ),
            nom_fichier_qrcode=get_str("OS_NOM_FICHIER_QRCODE", "qrcode"),
            nom_fichier_yaml_poly=get_str("OS_NOM_FICHIER_YAML_POLY", "poly.yaml"),
            extension_fichier_infos_upload=get_str(
                "OS_EXTENSION_FICHIER_INFOS_UPLOAD", ".infos.json"
            ),
            extensions_diaporama=get_list(
                "OS_EXTENSIONS_DIAPORAMA",
                default=[".pptx", ".ppt", ".key", ".odp"],
                sep=",",
            ),
            suffixe_nom_fichier_prof=get_str("OS_SUFFIXE_NOM_FICHIER_PROF", "-prof"),
            suffixe_nom_fichier_a_trous=get_str(
                "OS_SUFFIXE_NOM_FICHIER_A_TROUS", "-eleve"
            ),
            suffixe_nom_fichier_diaporama=get_str(
                "OS_SUFFIXE_NOM_DIAPORAMA", "-diaporama"
            ),
            suffixe_nom_fichier_sources=get_str("OS_SUFFIXE_NOM_SOURCES", "-sources"),
            suffixe_nom_thumbnail=get_str("OS_SUFFIXE_NOM_THUMBNAIL", "-miniature"),
            suffixe_nom_fichier_poly=get_str("OS_SUFFIXE_NOM_POLY", "-poly"),
            # Dossiers et arborescence
            dossier_cours=get_str("OS_DOSSIER_COURS", "Cours"),
            dossier_td=get_str("OS_DOSSIER_TD", "TD"),
            dossier_cible_par_rapport_au_fichier_tex=get_str(
                "OS_DOSSIER_CIBLE_PAR_RAPPORT_AU_FICHIER_TEX", ".."
            ),
            dossier_latex=get_str("OS_DOSSIER_LATEX", "LaTeX"),
            dossier_latex_build=get_str("OS_DOSSIER_LATEX_BUILD", "build"),
            dossier_latex_sources=get_str("OS_DOSSIER_LATEX_SOURCES", "src"),
            dossier_latex_sources_images=get_str(
                "OS_DOSSIER_LATEX_SOURCES_IMAGES", "images"
            ),
            dossier_tmp_pour_zip=get_str("OS_DOSSIER_TMP_POUR_ZIP", "temp_zip"),
            dossier_poly=get_str("OS_DOSSIER_POLY", "_poly"),
            dossier_poly_backup_yaml=get_str("OS_DOSSIER_POLY_BACKUP_YAML", "_bak"),
            dossier_poly_page_de_garde=get_str(
                "OS_DOSSIER_POLY_PAGE_DE_GARDE", "page_de_garde"
            ),
        )


@dataclass(frozen=True)
class PolyConfig:
    nombre_de_pages_par_feuille: int
    recto_verso: bool

    @classmethod
    def from_env(cls) -> "PolyConfig":
        return cls(
            nombre_de_pages_par_feuille=get_int("POLY_NOMBRE_DE_PAGES_PAR_FEUILLE", 2),
            recto_verso=get_bool("POLY_RECTO_VERSO", True),
        )


@dataclass(frozen=True)
class TraitementParLotConfig:
    """Valeurs par défaut pour les traitements par lot, provenant du .env"""

    dossiers_a_traiter: list[str]
    fichiers_a_exclure: list[str]

    @classmethod
    def from_env(cls) -> "TraitementParLotConfig":
        return cls(
            dossiers_a_traiter=get_list(
                "TRAITEMENT_PAR_LOT_DOSSIERS_A_TRAITER", default=[], sep=","
            ),
            fichiers_a_exclure=get_list(
                "TRAITEMENT_PAR_LOT_FICHIERS_A_EXCLURE", default=[], sep=","
            ),
        )


@dataclass(frozen=True)
class FTPConfig:
    """Valeurs par défaut pour la gestion de l'upload, provenant du .env"""

    secret_key: str
    user: str
    password: str
    host: str
    port: int
    timeout: int
    # Mode local (on remplace le stockage FTP par un stockage local)
    mode_local: bool
    mode_local_dossier: str

    @classmethod
    def from_env(cls) -> "FTPConfig":
        return cls(
            secret_key=get_str("FTP_SECRET_KEY", "dummy_secret_key"),
            user=get_str("FTP_USER", "ftp_user"),
            password=get_str("FTP_PASSWORD", "ftp_pwd"),
            host=get_str("FTP_HOST", "ftp_host"),
            port=get_int("FTP_PORT", 21),
            timeout=get_int("FTP_TIMEOUT", 30),
            # Mode local (on remplace le stockage FTP par un stockage local)
            mode_local=get_bool("FTP_MODE_LOCAL", False),
            mode_local_dossier=get_str("FTP_MODE_LOCAL_DOSSIER", ""),
        )


@dataclass(frozen=True)
class SiteConfig:
    """Valeurs par défaut pour la gestion du site, provenant du .env"""

    secret_key: str
    endpoint_get_config: str
    webhook_upload_url: str
    document_url_pattern: str

    @classmethod
    def from_env(cls) -> "SiteConfig":
        return cls(
            secret_key=get_str("SITE_SECRET_KEY", "passkey"),
            endpoint_get_config=get_str(
                "SITE_ENDPOINT_GET_CONFIG", "endpoint_get_config"
            ),
            webhook_upload_url=get_str("SITE_WEBHOOK_UPLOAD_URL", "webhook_upload_url"),
            document_url_pattern=get_str(
                "SITE_DOCUMENT_URL_PATTERN", "document_url_pattern"
            ),
        )


@dataclass(frozen=True)
class LegacyConfig:
    """Valeurs par défaut pour le legacy, provenant du .env"""

    nom_fichier_parametres_compilation: str
    nom_fichier_xml_poly: str
    suffixe_nom_fichier_prof: str
    suffixe_nom_fichier_a_trous: str
    suffixe_nom_fichier_diaporama: str
    suffixe_nom_fichier_poly: str
    dossier_latex_sources: str
    dossier_latex_sources_images: str

    @classmethod
    def from_env(cls) -> "LegacyConfig":
        return cls(
            nom_fichier_parametres_compilation=get_str(
                "LEGACY_NOM_FICHIER_PARAMETRES_COMPILATION", "@parametres.upsti.ini"
            ),
            nom_fichier_xml_poly=get_str("LEGACY_NOM_FICHIER_XML_POLY", "poly.xml"),
            suffixe_nom_fichier_prof=get_str(
                "LEGACY_SUFFIXE_NOM_FICHIER_PROF", "-Prof"
            ),
            suffixe_nom_fichier_a_trous=get_str(
                "LEGACY_SUFFIXE_NOM_FICHIER_A_TROUS", "-Eleve"
            ),
            suffixe_nom_fichier_diaporama=get_str(
                "LEGACY_SUFFIXE_NOM_DIAPORAMA", "-Diaporama"
            ),
            suffixe_nom_fichier_poly=get_str("LEGACY_SUFFIXE_NOM_POLY", "-polyTD"),
            dossier_latex_sources=get_str("LEGACY_DOSSIER_LATEX_SOURCES", "Src"),
            dossier_latex_sources_images=get_str(
                "LEGACY_DOSSIER_LATEX_SOURCES_IMAGES", "Images"
            ),
        )


@dataclass(frozen=True)
class AppConfig:
    meta: MetaConfig
    compilation: CompilationConfig
    os: OSConfig
    poly: PolyConfig
    traitement_par_lot: TraitementParLotConfig
    ftp: FTPConfig
    site: SiteConfig
    legacy: LegacyConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            meta=MetaConfig.from_env(),
            compilation=CompilationConfig.from_env(),
            os=OSConfig.from_env(),
            poly=PolyConfig.from_env(),
            traitement_par_lot=TraitementParLotConfig.from_env(),
            ftp=FTPConfig.from_env(),
            site=SiteConfig.from_env(),
            legacy=LegacyConfig.from_env(),
        )


def load_config() -> AppConfig:
    """Load configuration from TOML files and environment variables.

    Loading order (later overrides earlier):
    1. custom/.env (SECRETS ONLY: FTP_*, SITE_SECRET_KEY) — si le fichier existe
    2. pyupstilatex/config/config.default.toml (versioned defaults)
    3. custom/config.toml (local overrides, not versioned)

    All configuration MUST be in TOML files.
    custom/.env is ONLY for secrets (credentials, API keys).
    Si custom/.env n'existe pas, les valeurs par défaut sont utilisées.
    TOML values always take priority over .env for non-secret keys.
    """
    # Load TOML configuration and inject into os.environ
    _load_config_from_toml()

    # Build and return AppConfig from environment
    return AppConfig.from_env()
