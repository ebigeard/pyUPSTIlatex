import glob
import inspect
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import yaml
from slugify import slugify

from .accessibilite import VERSIONS_ACCESSIBLES_DISPONIBLES
from .config import load_config
from .exceptions import CompilationStepError
from .filesystem import DocumentFile
from .handlers import (
    DocumentVersionHandler,
    HandlerUPSTIDocumentV1,
    HandlerUPSTIDocumentV2,
)
from .logger import MessageHandler, NoOpMessageHandler
from .parsers import parse_package_imports
from .storage import FileSystemStorage, StorageProtocol
from .utils import (
    check_types,
    read_json_config,
)


@dataclass
class UPSTILatexDocument:
    """Représente un document LaTeX UPSTI.

    Cette classe gère l'ensemble du cycle de vie d'un document LaTeX UPSTI :
    - Détection automatique de la version (v1/v2/EPB)
    - Extraction et validation des métadonnées
    - Compilation avec gestion des versions élève/prof/accessibles
    - Post-traitements (copie, upload)

    Attributs
    ---------
    source : str
        Chemin vers le fichier source .tex
    storage : StorageProtocol
        Backend de stockage (par défaut : système de fichiers local)
    strict : bool
        Si True, lève des exceptions en cas d'erreur de lecture
    require_writable : bool
        Si True, exige que le fichier soit modifiable
    msg : MessageHandler
        Gestionnaire de messages pour l'affichage console/log
    """

    # === CHAMPS PUBLICS ===
    source: str
    storage: StorageProtocol = field(default_factory=FileSystemStorage)
    strict: bool = False
    require_writable: bool = False
    msg: MessageHandler = field(default_factory=NoOpMessageHandler)

    # === CHAMPS PRIVÉS (CACHE) ===
    _metadata: Optional[Dict] = field(default=None, init=False)
    _compilation_parameters: Optional[Dict] = field(default=None, init=False)
    _version: Optional[str] = field(default=None, init=False)
    _file: Optional[DocumentFile] = field(default=None, init=False)
    _handler: Optional[DocumentVersionHandler] = field(default=None, init=False)
    _liste_fichiers: Dict[str, List[Path]] = field(
        default_factory=lambda: {"compiled": [], "autres": []}, init=False
    )

    # =========================================================================
    # MÉTHODES SPÉCIALES
    # =========================================================================

    def __post_init__(self):
        """Initialise l'accès fichier via DocumentFile."""
        self._file = DocumentFile(
            source=self.source,
            storage=self.storage,
            strict=self.strict,
            require_writable=self.require_writable,
        )

    # =========================================================================
    # MÉTHODES DE CLASSE
    # =========================================================================

    @classmethod
    def from_path(
        cls,
        path: str,
        storage: Optional[StorageProtocol] = None,
        *,
        strict: bool = False,
        require_writable: bool = False,
        msg: Optional[MessageHandler] = None,
    ) -> tuple["UPSTILatexDocument", List[List[str]]]:
        errors: List[List[str]] = []
        try:
            doc = cls(
                source=path,
                storage=(storage or FileSystemStorage()),
                strict=strict,
                require_writable=require_writable,
                msg=(msg or NoOpMessageHandler()),
            )
            return doc, errors
        except Exception as e:
            errors.append(
                [
                    f"Erreur lors de l'initialisation du document '{path}': {e}",
                    "error",
                ]
            )
            return None, errors

    # =========================================================================
    # PROPERTIES (ACCÈS AUX ATTRIBUTS CACHED)
    # =========================================================================

    @property
    def file(self) -> DocumentFile:
        """Accès direct à l'objet système de fichiers (DocumentFile)."""
        if self._file is None:
            raise RuntimeError("DocumentFile non initialisé")
        return self._file

    # --- Properties déléguées à DocumentFile ---

    @property
    def exists(self) -> bool:
        """Indique si le fichier existe."""
        return self.file.exists

    @property
    def is_readable(self) -> bool:
        return self.file.is_readable

    @property
    def is_writable(self) -> bool:
        return self.file.is_writable

    @property
    def readable_reason(self) -> Optional[str]:
        return self.file.readable_reason

    @property
    def readable_flag(self) -> Optional[str]:
        return self.file.readable_flag

    @property
    def writable_reason(self) -> Optional[str]:
        return self.file.writable_reason

    @property
    def content(self) -> str:
        """Retourne le contenu textuel du fichier."""
        return self.file.read()

    # --- Properties avec cache automatique ---

    @property
    def version(self):
        """Retourne la version du document (UPSTI_Document_v1/v2, EPB_Cours)."""
        if self._version is not None:
            return self._version
        return self.get_version()[0]

    @property
    def metadata(self) -> Dict:
        if self._metadata is not None:
            return self._metadata
        return self.get_metadata()[0]

    @property
    def compilation_parameters(self) -> Dict:
        if self._compilation_parameters is not None:
            return self._compilation_parameters
        return self.get_compilation_parameters()[0]

    # =========================================================================
    # MÉTHODES PUBLIQUES PRINCIPALES
    # =========================================================================

    def compile(
        self, mode: str = "normal", verbose: str = "normal", dry_run: bool = False
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Compile le document LaTeX.

        Paramètres
        ----------
        mode : str, optional
            Mode de compilation. Valeurs acceptées :
            - "deep"  : génère le fichier LaTeX complet à partir des métadonnées
                         (utile pour les documents `UPSTI_Document_v2`).
            - "normal": compilation suivie d'un upload si configuré.
            - "quick" : seulement génération des PDF.
        verbose : str, optional
            Niveau de verbosité pour les messages renvoyés par la méthode.
            Valeurs acceptées :
            - "normal" : affiche tout.
            - "messages" : affiche juste les erreurs et warning.
            - "silent" : n'affiche rien.
        dry_run : bool, optional
            Si True, exécute un "dry run" où les actions sont affichées sans être
            réellement effectuées.

        Retour
        -----
        tuple[Optional[Dict], List[List[str]]]
            Renvoie un tuple `(result, messages)` où `result` est un dictionnaire
            optionnel contenant des informations sur la compilation (p.ex. chemins,
            statuts), et `messages` est une liste de paires `[message, flag]` où
            `flag` est l'un de `info`, `warning`, `error`.
        """

        # Initialisation des retours
        messages_compilation: List[List[str]] = []

        # Normaliser le niveau de verbosité et le mode
        valid_modes = {"deep", "normal", "quick"}
        valid_verbose = {"normal", "messages", "silent"}

        # Pour éviter de toujours passer ces éléments en paramètre
        compilation_cli_options = {
            "mode": mode if mode in valid_modes else "normal",
            "verbose": verbose if verbose in valid_verbose else "normal",
            "dry_run": dry_run,
        }

        # Initialisation du statut global
        statut_compilation: str = "success"

        try:

            # Titre
            if compilation_cli_options["verbose"] in ["normal"]:
                self.msg.titre2("Préparation de la compilation")

            # 1- Vérification de l'intégrité du fichier
            resultat, messages = self._cp_step(
                mode_ok=["deep", "normal", "quick"],
                affichage="Vérification de l'intégrité du fichier",
                fonction=lambda: self.file.check_file("read"),
                compilation_options=compilation_cli_options,
            )
            messages_compilation.extend(messages)

            # 2- Vérification de la version
            resultat, messages = self._cp_step(
                mode_ok=["deep", "normal", "quick"],
                affichage="Détection de la version du document",
                fonction=lambda: self.get_version(check_compatibilite=True),
                compilation_options=compilation_cli_options,
            )
            messages_compilation.extend(messages)

            # 3- Lecture des paramètres de compilation
            resultat, messages = self._cp_step(
                mode_ok=["deep", "normal", "quick"],
                affichage="Lecture des paramètres de compilation",
                fonction=self._cp_get_compilation_parameters,
                compilation_options=compilation_cli_options,
            )
            messages_compilation.extend(messages)

            # 4- Lecture des métadonnées
            resultat, messages = self._cp_step(
                affichage="Lecture des métadonnées du fichier tex",
                fonction=self.get_metadata,
                compilation_options=compilation_cli_options,
            )
            messages_compilation.extend(messages)

            # 5- Vérification et changement de l'id unique du document
            resultat, messages = self._cp_step(
                affichage="Vérification de l'id unique du document",
                fonction=self._cp_check_id_unique,
                compilation_options=compilation_cli_options,
            )
            messages_compilation.extend(messages)

            # 6- Vérification et changement du nom du fichier
            if self.compilation_parameters.get("renommer_automatiquement", False):
                resultat, messages = self._cp_step(
                    mode_ok=["deep"],
                    affichage="Vérification du nom de fichier",
                    fonction=self._cp_rename_file,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

            # 7- Générer le QRCode
            resultat, messages = self._cp_step(
                mode_ok=["deep"],
                affichage="Génération du QR code du document",
                fonction=self._cp_generate_qrcode,
                compilation_options=compilation_cli_options,
            )
            messages_compilation.extend(messages)

            # 8- Générer le code latex à partir des métadonnées (si UPSTI_Document v2)
            if self.version == "UPSTI_Document_v2":
                resultat, messages = self._cp_step(
                    mode_ok=["deep"],
                    affichage="Génération du code latex à partir des métadonnées",
                    fonction=self._cp_generate_latex_template,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

            # 9- Générer le fichier UPSTI_Document_v1 (si UPSTI_Document v2)
            if self.version == "UPSTI_Document_v2":
                resultat, messages = self._cp_step(
                    affichage=(
                        "Création du fichier tex UPSTI_Document_v1 "
                        "(pour la rétrocompatibilité)"
                    ),
                    fonction=self._cp_generate_UPSTI_Document_v1_tex_file,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

            # Titre intermédiaire
            if compilation_cli_options["verbose"] in ["normal"]:
                self.msg.titre2("Compilation du document LaTeX")

            # 10- Compilation Latex (voir aussi pour bibtex, si on le gère ici)
            if compilation_cli_options["mode"] in ["deep", "normal", "quick"]:
                resultat_compilation, messages_compilation_tex = (
                    self._cp_compile_tex_file(
                        compilation_options=compilation_cli_options
                    )
                )
                messages_compilation.extend(messages_compilation_tex)

                if resultat_compilation == "error":
                    raise CompilationStepError(messages_compilation)

                # Mémoriser le statut de la compilation LaTeX
                if resultat_compilation == "warning":
                    statut_compilation = "warning"

            # Post-traitements
            if self.compilation_parameters.get(
                "copier_pdf_dans_dossier_cible", False
            ) or self.compilation_parameters.get("upload", False):
                if compilation_cli_options["verbose"] in [
                    "normal"
                ] and compilation_cli_options["mode"] in ["deep", "normal"]:
                    self.msg.titre2("Post-traitements après compilation")

            # 11- Copie des fichiers dans le dossier cible
            if self.compilation_parameters.get("copier_pdf_dans_dossier_cible", False):
                resultat, messages = self._cp_step(
                    affichage="Copie des fichiers compilés dans le dossier cible",
                    fonction=self._cp_copy_files,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

            # 12- Fin du post traitement
            # DEBUG
            # compilation_cli_options["dry_run"] = False

            if self.compilation_parameters.get("upload", False):

                # 12a- Création du fichier zip des fichiers
                resultat, messages = self._cp_step(
                    affichage="Création du fichier zip",
                    fonction=self._cp_create_zip,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

                # 12b- Création du fichier meta à uploader
                fichier_meta_created, messages = self._cp_step(
                    affichage="Création du fichier de synthèse JSON à uploader",
                    fonction=self._cp_create_info_file,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

                # 12c- Upload des fichiers sur le FTP
                if fichier_meta_created:
                    resultat_upload, messages = self._cp_step(
                        affichage="Upload des fichiers sur le FTP",
                        fonction=self._cp_upload,
                        compilation_options=compilation_cli_options,
                    )
                    messages_compilation.extend(messages)

                # 12d- Webhook
                if fichier_meta_created and resultat_upload:
                    resultat, messages = self._cp_step(
                        affichage="Déclenchement du webhook",
                        fonction=self._cp_webhook_call,
                        compilation_options=compilation_cli_options,
                    )
                    messages_compilation.extend(messages)

                # 12e- Nettoyage de fin de compilation
                resultat, messages = self._cp_step(
                    affichage="Nettoyage des fichiers temporaires",
                    fonction=self._cp_clean_temp_after_compilation,
                    compilation_options=compilation_cli_options,
                )
                messages_compilation.extend(messages)

        # On gère ici les étapes qui intterrompent la compilation
        except CompilationStepError:
            return "error", messages_compilation

        # Déterminer le statut final : vérifier à la fois le statut de
        # _cp_compile_tex_file et les flags dans tous les messages
        has_warning = any(
            isinstance(m, (list, tuple)) and len(m) >= 2 and m[1] == "warning"
            for m in messages_compilation
        )
        if statut_compilation == "warning" or has_warning:
            return "warning", messages_compilation
        return "success", messages_compilation

    # --- Gestion des métadonnées ---

    def set_metadata(self, key: str, value: any) -> Tuple[bool, List[List[str]]]:
        """Ajoute ou modifie une métadonnée dans le document.

        Délègue l'opération au handler spécifique à la version du document.
        Pour UPSTI_Document_v1 : commande LaTeX \\UPSTImeta<key>{value}
        Pour UPSTI_Document_v2 : entrée dans le bloc YAML

        Paramètres
        ----------
        key : str
            Nom de la métadonnée à ajouter.
        value : any
            Valeur de la métadonnée.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (success, messages) où success indique si l'ajout a réussi,
            et messages contient les infos/erreurs.

        Exemples
        --------
        >>> doc.ajouter_metadonnee("titre", "Mon nouveau titre")
        (True, [["Métadonnée 'titre' ajoutée avec succès.", "info"]])
        """
        return self._get_handler().set_metadata(key, value)

    def delete_metadata(self, key: str) -> Tuple[bool, List[List[str]]]:
        """Supprime une métadonnée existante.

        Délègue l'opération au handler spécifique à la version du document.

        Paramètres
        ----------
        key : str
            Nom de la métadonnée à modifier.
        value : any
            Nouvelle valeur de la métadonnée.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (success, messages) où success indique si la modification a réussi.

        Exemples
        --------
        >>> doc.modifier_metadonnee("auteur", "Nouveau nom")
        (True, [["Métadonnée 'auteur' modifiée avec succès.", "info"]])
        """
        return self._get_handler().delete_metadata(key)

    # --- Récupération des données ---

    def get_metadata(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Récupère et normalise les métadonnées du document.

        Détecte automatiquement la version (v1/v2/EPB), applique le parser approprié,
        normalise les données via _format_metadata et met en cache le résultat.

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (metadata_dict, messages) où metadata_dict contient les métadonnées
            normalisées avec structure {key: {valeur, affichage, initiales, ...}},
            et messages est une liste de [message, flag] (info/warning/error).
            Ne lève jamais d'exception.
        """
        # Réutiliser le cache si les métadonnées ont déjà été extraites
        if self._metadata is not None:
            return self._metadata, []

        # Déléguer le parsing au handler approprié selon la version
        try:
            metadata, errors = self._get_handler().parse_metadata()
        except ValueError as e:
            # Version non supportée
            return None, [[str(e), "fatal_error"]]

        if metadata is None:
            return None, errors

        # Lire le fichier de paramètres de compilation pour override
        custom_params, custom_errors = self._read_fichier_parametres_compilation()
        if custom_errors:
            # Ne garder que les erreurs réelles (pas les "info")
            errors.extend([e for e in custom_errors if e[1] != "info"])

        # Override des métadonnées si présentes dans le fichier de paramètres
        if custom_params and "surcharge_metadonnees" in custom_params:
            override_meta = custom_params["surcharge_metadonnees"]
            if isinstance(override_meta, dict):
                # Si metadata est None, initialiser un dict vide
                if metadata is None:
                    metadata = {}

                # Merger : ajouter nouvelles clés et remplacer existantes
                metadata.update(override_meta)
                errors.append(
                    [
                        f"Métadonnées overridées depuis le fichier de paramètres "
                        "(Métadonnée(s) changée(s) : "
                        f"{', '.join(list(override_meta.keys()))})",
                        "info",
                    ]
                )

        # Récupérer la version pour _format_metadata
        version = self._version or self.version
        formatted, formatted_errors = self._format_metadata(metadata, source=version)
        if formatted is not None:
            self._metadata = formatted
        return formatted, errors + formatted_errors

    def get_compilation_parameters(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Récupère les paramètres de compilation du document.

        Charge la configuration centralisée depuis .env, puis fusionne les paramètres
        locaux si un fichier de paramètres existe dans le même répertoire que le
        document. Résultat mis en cache.

        Retourne
        --------
        tuple[Dict, List[List[str]]]
            (parametres, messages) où parametres contient les clés :
            - compiler: bool
            - versions_a_compiler: list[str]
            - versions_accessibles_a_compiler: list[str]
            - est_un_document_a_trous: bool
            - copier_pdf_dans_dossier_cible: bool
            - upload: bool
            - dossier_ftp: str
            Messages contient warnings/erreurs si fichier local invalide.
        """
        # Réutiliser le cache si déjà récupéré
        if self._compilation_parameters is not None:
            return self._compilation_parameters, []

        errors: List[List[str]] = []

        # Lire la configuration centralisée
        cfg = load_config()
        comp = cfg.compilation

        parametres_compilation = {
            "compiler": bool(comp.compiler),
            "renommer_automatiquement": bool(comp.renommer_automatiquement),
            "versions_a_compiler": list(comp.versions_a_compiler),
            "versions_accessibles_a_compiler": list(
                comp.versions_accessibles_a_compiler
            ),
            "est_un_document_a_trous": bool(comp.est_un_document_a_trous),
            "copier_pdf_dans_dossier_cible": bool(comp.copier_pdf_dans_dossier_cible),
            "upload": bool(comp.upload),
            "dossier_ftp": str(comp.dossier_ftp),
        }

        # Vérifier si un fichier de paramètres existe dans le même dossier
        custom_params, custom_errors = self._read_fichier_parametres_compilation()
        if custom_errors:
            errors.extend(custom_errors)
        if custom_params:
            parametres_compilation.update(custom_params)

        # Mettre en cache
        self._compilation_parameters = parametres_compilation
        return parametres_compilation, errors

    def get_version(
        self, check_compatibilite: bool = False
    ) -> tuple[Optional[str], List[List[str]]]:
        """Retourne la version du document (avec cache).

        Détecte automatiquement le format du document parmi :
        - UPSTI_Document_v2 (métadonnées YAML)
        - UPSTI_Document_v1 (métadonnées LaTeX)
        - EPB_Cours (format non supporté)

        Retourne
        --------
        tuple[Optional[str], List[List[str]]]
            (version, messages) où version est le nom du format détecté ou None.
            Résultat mis en cache dans self._version.
        """
        if self._version is not None:
            # Version déjà détectée (cache)
            return self._version, []

        version, errors = self._detect_version()

        if version is None:
            return None, errors

        # Si demandé, vérifier explicitement la compatibilité de la version
        if check_compatibilite:
            if version not in ("UPSTI_Document_v1", "UPSTI_Document_v2"):
                return None, [
                    [
                        f"Les documents {version} ne sont pas pris en charge par "
                        "pyUPSTIlatex. Il est néanmoins possible de les convertir en "
                        "utilisant : pyupstilatex migrate.",
                        "fatal_error",
                    ]
                ]

        self._version = version
        return version, errors

    def _get_handler(self) -> DocumentVersionHandler:
        """Retourne le handler approprié selon la version (lazy initialization).

        Le handler est créé la première fois que cette méthode est appelée,
        après détection de la version du document. Les appels suivants
        retournent l'instance en cache.

        Retourne
        --------
        DocumentVersionHandler
            L'instance du handler (HandlerUPSTIDocumentV1 ou HandlerUPSTIDocumentV2).

        Raises
        ------
        ValueError
            Si la version du document n'est pas supportée.
        """
        if self._handler is None:
            version = self.version  # Détecte la version si pas encore fait

            if version == "UPSTI_Document_v1":
                self._handler = HandlerUPSTIDocumentV1(self)
            elif version == "UPSTI_Document_v2":
                self._handler = HandlerUPSTIDocumentV2(self)
            else:
                raise ValueError(
                    f"Version non supportée: {version}. "
                    "Les versions supportées sont : "
                    "UPSTI_Document_v1, UPSTI_Document_v2"
                )

        return self._handler

    # =========================================================================
    # MÉTHODES PRIVÉES : ORCHESTRATION DE LA COMPILATION
    # =========================================================================

    def _cp_step(
        self,
        fonction: Callable,
        compilation_options: dict,
        mode_ok: list = ["deep", "normal"],
        affichage: str = "Étape de compilation",
    ) -> List[str]:
        """Exécute une étape de compilation en gérant l'affichage et les erreurs.

        Cette méthode centralise l'exécution des différentes étapes de compilation
        en gérant automatiquement :
        - Le filtrage par mode (deep, normal, quick)
        - L'affichage des messages selon le niveau de verbosité
        - L'ajout d'un message de succès si aucun message n'est renvoyé
        - La levée d'une exception si l'étape échoue (résultat None)

        Paramètres
        ----------
        fonction : Callable
            Fonction à exécuter pour cette étape. Doit retourner un tuple
            (resultat, messages) où resultat peut être None en cas d'erreur.
        mode : Optional[str], optional
            Mode de compilation pour cette étape. Si None, utilise
                `compilation_cli_options["mode"]`.
            Défaut : None.
        mode_ok : list, optional
            Liste des modes autorisés pour exécuter cette étape.
            Défaut : ["deep", "normal"].
        verbose : Optional[str], optional
            Niveau de verbosité pour l'affichage. Si None, utilise
                `compilation_cli_options["verbose"]`.
            Valeurs acceptées : "normal", "messages", "silent".
            Défaut : None.
        affichage : str, optional
            Message à afficher avant l'exécution de l'étape.
            Défaut : "Étape de compilation".

        Retourne
        --------
        tuple[Any, List[List[str]]]
            Tuple (resultat, messages) où :
            - resultat : valeur retournée par la fonction (ou None)
            - messages : liste de [message, flag] générés durant l'exécution

        Raises
        ------
        CompilationStepError
            Levée si la fonction retourne None comme résultat, indiquant un échec
            de l'étape. L'exception contient la liste des messages d'erreur.
        """
        format_last_message = bool(compilation_options["verbose"] != "messages")

        # On récupère la config pour gérer le niveau de verbosité
        cfg = load_config()
        affiche_details = cfg.compilation.affichage_detaille_dans_console

        messages: List[List[str]] = []
        resultat = None
        if compilation_options["mode"] in mode_ok:
            if compilation_options["verbose"] in ["normal"]:
                self.msg.info(affichage)

            # Inspecter la signature pour savoir si on doit passer les options
            try:
                sig = inspect.signature(fonction)
                if "compilation_options" in sig.parameters:
                    resultat, messages = fonction(
                        compilation_options=compilation_options
                    )
                else:
                    resultat, messages = fonction()
            except (ValueError, TypeError):
                # Fallback si l'inspection échoue (ex: lambda, built-in)
                resultat, messages = fonction()

            if (
                affiche_details
                and compilation_options["verbose"] in ["normal"]
                and len(messages) == 0
            ):
                messages.append(["OK !", "success"])

            if compilation_options["verbose"] in ["normal"]:
                self.msg.affiche_messages(
                    messages, "resultat_item", format_last=format_last_message
                )

            # Si resultat est None, c'est une erreur fatale
            if resultat is None:
                raise CompilationStepError(messages)

        return resultat, messages

    def _cp_get_compilation_parameters(
        self,
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Récupère les paramètres de compilation adaptés pour la compilation
        (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (compilation_parameters, messages) où messages est une liste de
            [message, flag].
        """
        # On utilise la méthode interne
        comp_params, comp_params_messages = self.get_compilation_parameters()

        if comp_params is None:
            return None, comp_params_messages

        # On va prendre en compte le paramètre "compiler"
        if not comp_params.get("compiler", True):
            cfg = load_config()
            nom_fichier_comp = cfg.compilation.nom_fichier_parametres_compilation
            comp_params_messages.append(
                [
                    "La compilation est désactivée pour ce document "
                    "(paramètre 'compiler' à false dans le fichier "
                    f"{nom_fichier_comp}).",
                    "fatal_error",
                ]
            )
            return None, comp_params_messages

        return comp_params, []

    def _cp_rename_file(
        self, compilation_options: dict
    ) -> tuple[Optional[str], List[List[str]]]:
        """Renomme le fichier source selon les métadonnées (méthode interne).

        Retourne
        --------
        tuple[Optional[str], List[List[str]]]
            (nouveau_chemin, messages) où messages est une liste de [message, flag].
        """
        import re

        def _apply_filters(value: str, filters: List[str]) -> str:
            """Applique successivement une liste de filtres à une valeur.

            Filtres disponibles:
                - upper: convertit en majuscules
                - lower: convertit en minuscules
                - capitalize: première lettre en majuscule
                - title: convertit en format titre
                - slug: convertit en slug (Django slugify)

            Paramètres
            ----------
            value : str
                La valeur à filtrer
            filters : List[str]
                Liste des filtres à appliquer dans l'ordre

            Retourne
            --------
            str
                La valeur filtrée
            """
            result = str(value)
            for f in filters:
                f = f.strip().lower()
                if f == "upper":
                    result = result.upper()
                elif f == "lower":
                    result = result.lower()
                elif f == "capitalize":
                    result = result.capitalize()
                elif f == "title":
                    result = result.title()
                elif f == "slug":
                    result = slugify(result, separator="_")
            return result

        # 1. Récupérer le format depuis la config
        chemin_actuel = self.file.path
        cfg = load_config()
        format_nom_fichier = cfg.compilation.format_nom_fichier

        if not format_nom_fichier:
            return chemin_actuel.name, [
                [
                    "Format de nom de fichier non configuré."
                    "On conserve le nom de fichier initial.",
                    "warning",
                ]
            ]

        # 2. Extraire les zones entre crochets
        pattern = r'\[([^\]]+)\]'
        placeholders = re.findall(pattern, format_nom_fichier)

        if not placeholders:
            return chemin_actuel.name, [
                [
                    "Aucun placeholder trouvé dans le format de nom."
                    "On conserve le nom de fichier initial.",
                    "warning",
                ]
            ]

        # 3. Récupérer les métadonnées et la config JSON
        metadata = self.metadata
        cfg_json, cfg_json_errors = read_json_config()
        if cfg_json_errors:
            return chemin_actuel.name, cfg_json_errors
        cfg_json = cfg_json or {}

        # 4. Remplacer chaque placeholder par sa valeur dans les métadonnées
        nouveau_nom = format_nom_fichier
        for placeholder in placeholders:
            # Analyser le placeholder : peut contenir des filtres après |
            # Exemple: [thematique.code|upper,slug] ou [titre|slug]
            if "|" in placeholder:
                placeholder_base, filters_str = placeholder.split("|", 1)
                filters = [f.strip() for f in filters_str.split(",") if f.strip()]
            else:
                placeholder_base = placeholder
                filters = []

            # Analyser le placeholder_base : peut contenir plusieurs parties séparées
            # par "."
            parts = placeholder_base.split(".")
            meta_key = parts[0]  # Première partie = clé de métadonnée

            special_meta_keys = ["titre_ou_titre_activite"]
            if meta_key not in metadata and meta_key not in special_meta_keys:
                return chemin_actuel.name, [
                    [
                        f"Métadonnée '{meta_key}' introuvable. "
                        "On conserve le nom de fichier initial.",
                        "warning",
                    ]
                ]

            # Si le placeholder est simple (une seule clé)
            if len(parts) == 1:
                if meta_key == "titre_ou_titre_activite":
                    # Cas spécial : privilégier `titre_activite` si présent,
                    # sinon utiliser `titre`.
                    if "titre_activite" in metadata:
                        valeur = metadata["titre_activite"].get("valeur", "")
                    else:
                        valeur = metadata["titre"].get("valeur", "")
                else:
                    valeur = metadata[meta_key].get("valeur", "")
                if valeur:
                    # Appliquer les filtres si présents
                    valeur_finale = _apply_filters(str(valeur), filters)
                    nouveau_nom = nouveau_nom.replace(f"[{placeholder}]", valeur_finale)
                else:
                    return chemin_actuel.name, [
                        [
                            f"Métadonnée '{meta_key}' vide. On conserve le nom de "
                            "fichier initial.",
                            "warning",
                        ]
                    ]
            else:
                # Placeholder composé : [classe.niveau] ou autre
                # Récupérer la raw_value de la métadonnée
                raw_value = metadata[meta_key].get("raw_value", "")

                if not raw_value:
                    return chemin_actuel.name, [
                        [
                            f"Métadonnée '{meta_key}' vide. On conserve le nom de "
                            "fichier initial.",
                            "warning",
                        ]
                    ]

                # Chercher dans la config JSON la définition de cette métadonnée
                # puis naviguer dans la structure pour trouver la propriété demandée
                meta_cfg = cfg_json.get(meta_key, {})

                # raw_value peut être une clé vers un objet dans la config
                if isinstance(raw_value, str) and raw_value in meta_cfg:
                    obj = meta_cfg[raw_value]

                    # Parcourir les parts restantes pour accéder à la propriété
                    valeur = obj
                    for part in parts[1:]:
                        if isinstance(valeur, dict) and part in valeur:
                            valeur = valeur[part]
                        else:
                            valeur = None
                            break

                    if valeur:
                        # Appliquer les filtres si présents
                        valeur_finale = _apply_filters(str(valeur), filters)
                        nouveau_nom = nouveau_nom.replace(
                            f"[{placeholder}]", valeur_finale
                        )
                    else:
                        return chemin_actuel.name, [
                            [
                                f"Propriété '{'.'.join(parts[1:])}' introuvable pour "
                                f"'{meta_key}'. On conserve le nom de fichier initial.",
                                "warning",
                            ]
                        ]
                else:
                    return chemin_actuel.name, [
                        [
                            f"Impossible de résoudre '{placeholder}'. "
                            "On conserve le nom de fichier initial.",
                            "warning",
                        ]
                    ]

        # 5. Construire le nouveau chemin complet
        nouveau_chemin = self.file.parent / f"{nouveau_nom}{self.file.suffix}"

        # 6. Vérifier si le nom a changé
        if nouveau_chemin == chemin_actuel:
            return chemin_actuel.name, []

        # 7. Pré-vérifications : existence du fichier source et droit en écriture
        if not chemin_actuel.exists() or not chemin_actuel.is_file():
            return chemin_actuel.name, [
                [f"Fichier source introuvable: {chemin_actuel}", "warning"]
            ]
        # Utiliser l'objet DocumentFile pour vérifier l'accessibilité en écriture
        try:
            if not self.file.is_writable:
                return chemin_actuel.name, [
                    [f"Fichier non accessible en écriture: {chemin_actuel}", "warning"]
                ]
        except Exception:
            # En cas d'erreur d'accès à l'objet file, on tente quand même le renommage
            pass

        # Ne pas écraser un fichier existant
        if nouveau_chemin.exists():
            return chemin_actuel.name, [
                [
                    f"Le fichier cible existe déjà: {nouveau_chemin}. "
                    "On conserve le nom de fichier initial.",
                    "warning",
                ]
            ]

        # 8. Tenter le renommage physique
        if not compilation_options["dry_run"]:
            try:
                chemin_actuel.rename(nouveau_chemin)
            except PermissionError as e:
                return chemin_actuel.name, [
                    [
                        f"Permission refusée lors du renommage: {e}. "
                        "On conserve le nom de fichier initial.",
                        "warning",
                    ]
                ]
            except FileExistsError as e:
                return chemin_actuel.name, [
                    [
                        f"Le fichier cible existe déjà: {e}. On conserve le nom de "
                        "fichier initial.",
                        "warning",
                    ]
                ]
            except Exception as e:
                return chemin_actuel.name, [
                    [
                        f"Erreur lors du renommage: {e}. On conserve le nom de fichier "
                        "initial.",
                        "warning",
                    ]
                ]

        # 9. Mise à jour de l'objet Document pour pointer vers le nouveau chemin
        try:
            self.source = str(nouveau_chemin)
            self._file = DocumentFile(
                source=self.source,
                storage=self.storage,
                strict=self.strict,
                require_writable=self.require_writable,
            )
        except Exception:
            # Si la reconstruction de l'objet DocumentFile échoue, signaler une erreur
            return chemin_actuel.name, [
                [
                    "Renommage effectué mais impossible d'initialiser l'objet fichier.",
                    "warning",
                ]
            ]

        # 10. Suppression de tous les vieux fichiers liés (cache, compilés, etc.)
        messages: List[List[str]] = []
        deleted_files: List[str] = []
        failed_deletions: List[List[str]] = []

        parent = chemin_actuel.parent
        build_dir = parent / cfg.compilation.dossier_compilation_latex

        if build_dir.exists() and build_dir.is_dir():
            try:
                if not compilation_options.get("dry_run", False):
                    shutil.rmtree(build_dir)
                deleted_files.append(str(build_dir.name))
            except Exception as e:
                failed_deletions.append(
                    [
                        "Erreur lors de la tentative de suppression du dossier "
                        f"{build_dir} : {e}",
                        "warning",
                    ]
                )

        pattern = glob.escape(chemin_actuel.stem) + "*"
        for p in parent.glob(pattern):
            # éviter de toucher le nouveau fichier
            try:
                if p.resolve() == self.file.path.resolve():
                    continue
            except Exception:
                pass

            if p.is_file():
                try:
                    if not compilation_options["dry_run"]:
                        p.unlink()
                    deleted_files.append(str(p.name))
                except Exception as e:
                    failed_deletions.append(
                        [f"Échec suppression {p.name}: {e}", "warning"]
                    )

        messages.extend(failed_deletions)

        # 11. Renommer tous les pdf du dossier cible si besoin
        if self.compilation_parameters.get("copier_pdf_dans_dossier_cible", False):
            try:
                dossier_cible = (
                    self.file.parent
                    / cfg.compilation.dossier_cible_par_rapport_au_fichier_tex
                )
                prefix_old, prefix_new = chemin_actuel.stem, nouveau_chemin.stem

                for fichier in dossier_cible.iterdir():
                    if fichier.is_file() and fichier.name.startswith(prefix_old):
                        nouveau_nom = prefix_new + fichier.name[len(prefix_old) :]
                        nouveau_fichier = dossier_cible / nouveau_nom

                        if not nouveau_fichier.exists():
                            if not compilation_options.get("dry_run", False):
                                fichier.rename(nouveau_fichier)

            except Exception as e:
                messages.append(
                    [
                        "Erreur lors du renommage des fichiers dans le dossier "
                        f"cible : {e}",
                        "warning",
                    ]
                )

        messages.append([f"Le fichier a été renommé : {nouveau_chemin.name}", "info"])
        return str(nouveau_chemin), messages

    # --- Génération de fichiers annexes ---

    def _cp_generate_qrcode(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Génère un qrcode vers la page d'un document, à partir de l'id_unique
        (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur le fichier
            généré, et messages est une liste de [message, flag].
        """
        # Récupération de la configuration
        cfg = load_config()
        pattern = cfg.site.document_url_pattern or ""

        if not pattern:
            return None, [
                [
                    "Pattern d'URL de document non configuré. "
                    "Le QRcode n'a pas été créé.",
                    "fatal_error",
                ]
            ]

        # Récupérer les métadonnées
        metadata, metadata_messages = self.get_metadata()
        if metadata is None:
            metadata_messages.append(
                [
                    "Pattern d'URL de document non configuré. "
                    "Le QRcode n'a pas été créé.",
                    "fatal_error",
                ]
            )
            return None, metadata_messages

        id_unique = metadata.get("id_unique", {}).get("valeur", "")

        # Construction de l'url
        url = pattern.replace("{id_unique}", id_unique)

        # Création du chemin du fichier QRcode
        comp = cfg.compilation
        images_dir = (
            self.file.parent
            / str(comp.dossier_sources_latex)
            / str(comp.dossier_sources_latex_images)
        )
        if not compilation_options["dry_run"]:
            try:
                images_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        # qrcode_filename = f"{self.file.stem}{comp.suffixe_nom_qrcode}.png"
        qrcode_filename = f"{comp.fichier_qrcode}.png"
        qrcode_path = images_dir / qrcode_filename

        # Génération du QRcode
        import qrcode

        if not compilation_options["dry_run"]:
            try:
                # TODO : ici on pourrait faire un plus joli QRcode avec logo,couleurs...
                qrcode.make(url).save(qrcode_path)
            except Exception:
                return None, [
                    ["Erreur lors de la génération du QRcode.", "fatal_error"]
                ]

        return str(qrcode_path), []

    def _cp_check_id_unique(
        self, compilation_options: dict
    ) -> tuple[Optional[str], List[List[str]]]:
        """Vérifie si l'id_unique est présent dans le fichier et est bien dans la bonne
        forme. Sinon, on écrit la nouvelle valeur (méthode interne).

        Retourne
        --------
        tuple[Optional[str], List[List[str]]]
            (nouveau_chemin, messages) où messages est une liste de [message, flag].
        """
        cfg = load_config()
        prefixe_id_unique: str = cfg.meta.id_document_prefixe
        valeur_id_unique: Optional[str] = None
        etat_id_unique: str = "unchanged"
        message: Optional[str] = None
        flag: Optional[str] = None

        metadata, metadata_messages = self.get_metadata()
        if metadata is None:
            return None, metadata_messages

        id_unique = metadata.get("id_unique", {}).get("valeur", "")
        id_unique_initiale = metadata.get("id_unique", {}).get("initial_value", "")

        if id_unique != id_unique_initiale:

            if not compilation_options["dry_run"]:
                success, change_id_unique_messages = self.set_metadata(
                    "id_unique", id_unique
                )

                if not success:
                    return None, change_id_unique_messages

            if id_unique_initiale is None or id_unique_initiale == "":
                message = f"L'id unique ({id_unique}) a été créé et ajouté au fichier."
                flag = "info"
                etat_id_unique = "new"
                valeur_id_unique = id_unique
            else:
                message = (
                    "L'id unique a été modifié dans le fichier : "
                    f"{id_unique_initiale} -> {id_unique}"
                )
                flag = "info"
                etat_id_unique = "changed"
                valeur_id_unique = id_unique

        else:
            # L'id n'a pas été changé, il faut vérifier qu'il est bien formé.
            import re

            # Valide un id_unique formé du préfixe + un entier
            pattern = re.compile(rf"^{re.escape(prefixe_id_unique)}[0-9]+$")

            if not pattern.match(id_unique):
                # Mauvais format, il faut en générer un nouveau
                epoch = int(time.time())
                nouvel_id_unique = f"{prefixe_id_unique}{epoch}"

                # Mise à jour du cache des métadonnées
                if self._metadata is not None:
                    self._metadata["id_unique"]["valeur"] = nouvel_id_unique

                # Il faut écrire le nouvel id dans le fichier tex
                if not compilation_options["dry_run"]:
                    success, change_id_unique_messages = self.set_metadata(
                        "id_unique", nouvel_id_unique
                    )

                    if not success:
                        return None, change_id_unique_messages

                message = (
                    f"L'id unique n'était pas dans le bon format ({id_unique}). "
                    f"Il a été corrigé: {nouvel_id_unique}"
                )
                flag = "info"
                etat_id_unique = "changed"
                valeur_id_unique = nouvel_id_unique

            # On va ajouter un paramètre pour donner l'état de l'id_unique
            #
            # TODEL
            # Pour la première création des documents sur le site, je vais forcer
            # l'état à "new" pour tous les documents, afin de faciliter la migration.
            #
            etat_id_unique = "new"
            #
            comp_params, comp_params_messages = self.get_compilation_parameters()
            if comp_params is not None:
                self._compilation_parameters["etat_id_unique"] = etat_id_unique

        valeur_id_unique = valeur_id_unique or id_unique
        return valeur_id_unique, [[message, flag]] if message and flag else []

    def _cp_generate_latex_template(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Génère le code LaTeX complet à partir des métadonnées (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur le fichier
            généré, et messages est une liste de [message, flag].
        """
        # On génère le code LaTeX complet à partir des métadonnées
        return None, [["Non implémenté.", "info"]]

    def _cp_generate_UPSTI_Document_v1_tex_file(
        self,
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Génère un fichier LaTeX v1 pour rétrocompatibilité (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur le fichier
            généré, et messages est une liste de [message, flag].
        """
        # On génère un fichier LaTeX v1 à partir des métadonnées
        return "N.I", [["Non implémenté.", "info"]]

    def _cp_create_accessible_version(
        self, code: str, compilation_options: dict
    ) -> tuple[Optional[str], List[List[str]]]:
        """Crée un fichier tex pour une version accessible.

        Retourne
        --------
        tuple[Optional[str], List[List[str]]]
            (result, messages) où result contient le nom du fichier tex
            généré, et messages est une liste de [message, flag].
        """

        if code not in VERSIONS_ACCESSIBLES_DISPONIBLES:
            return None, [[f"Version accessible inconnue : {code}", "warning"]]
        else:
            nom_fichier_accessible = (
                self.file.stem + VERSIONS_ACCESSIBLES_DISPONIBLES[code]["suffixe"]
            )
            fichier_accessible = {
                "nom": nom_fichier_accessible,
                "suffixe_affichage": VERSIONS_ACCESSIBLES_DISPONIBLES[code][
                    "affichage"
                ],
            }

            # Créer physiquement le fichier .tex pour la version accessible
            nouveau_fichier = self.file.parent / f"{nom_fichier_accessible}.tex"

            #
            # TODO : modifier le fichier en dur ! En passant par le handler ?
            # Ou par accessibilite.py ?
            #

            if not compilation_options["dry_run"]:
                try:
                    shutil.copy(self.file.path, nouveau_fichier)
                except Exception as e:
                    return None, [
                        [
                            f"Erreur lors de la création de {nom_fichier_accessible}"
                            ".tex : "
                            f"{e}",
                            "warning",
                        ]
                    ]

            return fichier_accessible, []

    # --- Compilation LaTeX ---

    def _cp_compile_tex_file(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Compile le fichier LaTeX (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur la compilation,
            et messages est une liste de [message, flag].
        """

        if compilation_options["verbose"] in ["normal"]:
            self.msg.info(
                "Préparation de la compilation (environnement et fichiers à compiler)"
            )

        import subprocess

        try:
            subprocess.run(
                ["pdflatex", "--version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return None, [
                ["pdflatex n'est pas installé ou introuvable.", "fatal_error"]
            ]

        liste_fichiers_a_compiler: List[Dict[str]] = [
            {"nom": self.file.stem, "suffixe_affichage": ""}
        ]
        compilation_job_list: List[Dict] = []
        messages: List[List[str]] = []

        # Récupération de la config et des paramètres de compilation
        cfg = load_config()
        affiche_details = cfg.compilation.affichage_detaille_dans_console

        versions_a_compiler = self._compilation_parameters.get(
            "versions_a_compiler", []
        )
        versions_accessibles_a_compiler = self._compilation_parameters.get(
            "versions_accessibles_a_compiler", []
        )
        est_un_document_a_trous = self._compilation_parameters.get(
            "est_un_document_a_trous", False
        )

        # Il faut d'abord créer les sources tex des fichiers accessibles
        for version in versions_accessibles_a_compiler:
            # Créer le fichier
            fichier_accessible, messages_fichiers_accessibles = (
                self._cp_create_accessible_version(
                    version, compilation_options=compilation_options
                )
            )
            if fichier_accessible is None:
                messages.extend(messages_fichiers_accessibles)
            else:
                liste_fichiers_a_compiler.append(fichier_accessible)

        # Création de la liste des tâches de compilation
        if "eleve" in versions_a_compiler:
            for fichier_a_compiler in liste_fichiers_a_compiler:

                # Affichage
                suffixe_affichage = fichier_a_compiler.get("suffixe_affichage", "")
                if suffixe_affichage != "":
                    suffixe_affichage = f" [{suffixe_affichage}]"

                if est_un_document_a_trous:
                    # Version à publier
                    compilation_job_list.append(
                        {
                            "affichage_nom_version": f"à publier{suffixe_affichage}",
                            "fichier_tex": fichier_a_compiler["nom"],
                            "job_name": fichier_a_compiler["nom"],
                            "option": "Pub",
                        }
                    )
                    # Version élève (doc à trous)
                    compilation_job_list.append(
                        {
                            "affichage_nom_version": (
                                f"élève (doc à trous){suffixe_affichage}"
                            ),
                            "fichier_tex": fichier_a_compiler["nom"],
                            "job_name": (
                                f"{fichier_a_compiler['nom']}{cfg.compilation.suffixe_nom_fichier_a_trous}"
                            ),
                            "option": "E",
                        }
                    )
                else:
                    # Version élève
                    compilation_job_list.append(
                        {
                            "affichage_nom_version": f"élève{suffixe_affichage}",
                            "fichier_tex": fichier_a_compiler["nom"],
                            "job_name": fichier_a_compiler["nom"],
                            "option": "E",
                        }
                    )

        if "prof" in versions_a_compiler:
            compilation_job_list.append(
                {
                    "affichage_nom_version": "prof",
                    "fichier_tex": self.file.stem,
                    "job_name": (
                        f"{self.file.stem}{cfg.compilation.suffixe_nom_fichier_prof}"
                    ),
                    "option": "P",
                }
            )

        # Fin de la préparation des tâches de compilation
        if (
            affiche_details
            and compilation_options["verbose"] in ["normal"]
            and len(messages) == 0
        ):
            messages.append(["OK !", "success"])
        self.msg.affiche_messages(messages, "resultat_item")

        # Compilation des différents fichiers
        nombre_compilations = cfg.compilation.nombre_compilations_latex
        build_dir = cfg.compilation.dossier_compilation_latex
        output_dir = self.file.parent

        # Pour savoir si on doit faire une compilation bibtex
        has_bibliographie = bool(
            self._metadata.get("bibliographie", {}).get("valeur", [])
        )

        compilation_messages: List[List[str]] = []
        for i, fic in enumerate(compilation_job_list):

            # Dossiers de sorties
            nom_fichier_tex_path = output_dir / f"{fic['fichier_tex']}.tex"
            build_dir_path = output_dir / build_dir

            # Pour savoir si on doit faire une compilation bibtex
            compile_bibtex = (
                has_bibliographie
                and i == 0
                and compilation_options.get("mode") == "deep"
            )
            nombre_compilations_corrige = (
                nombre_compilations + 2
                if (compile_bibtex and i == 0)
                else nombre_compilations
            )

            # Démarrage de la compilation
            compilation_OK: bool = True
            passe_compilation = 1
            while compilation_OK and passe_compilation <= nombre_compilations_corrige:

                # Affichage de la passe de compilation
                affiche_passe = (
                    passe_compilation - 1
                    if compile_bibtex and passe_compilation > 2
                    else passe_compilation
                )
                if compilation_options["verbose"] in ["normal"]:
                    if compile_bibtex and passe_compilation == 2:
                        affichage_nom_fichier_dans_message = (
                            "Compilation de la bibliographie (passe bibtex)"
                        )
                    else:
                        affichage_nom_fichier_dans_message = (
                            f"Compilation de la version {fic['affichage_nom_version']}"
                        )
                        if nombre_compilations > 1:
                            affichage_nom_fichier_dans_message += (
                                f" (passe n°{affiche_passe})"
                            )
                    self.msg.info(affichage_nom_fichier_dans_message)

                if compile_bibtex and passe_compilation == 2:
                    cwd_dir = build_dir_path
                    command = [
                        "bibtex",
                        "-quiet",
                        nom_fichier_tex_path.stem,
                    ]
                else:
                    cwd_dir = output_dir
                    command = [
                        "pdflatex",
                        "-quiet",
                        "-synctex=1",
                        "-interaction=nonstopmode",
                        f"-job-name={fic['job_name']}",
                        f"-output-directory={build_dir_path}",
                        f"\\def\\ChoixDeVersion{{{fic['option']}}}\\input{{{nom_fichier_tex_path.as_posix()}}}",
                    ]
                try:
                    if not compilation_options["dry_run"]:
                        subprocess.run(
                            command,
                            check=True,
                            cwd=cwd_dir,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )

                    # Ajout du nom de fichier à la liste des fichiers compilés
                    if passe_compilation == 1:
                        pdf_compiled_path = build_dir_path / f"{fic['job_name']}.pdf"
                        self._liste_fichiers["compiled"].append(pdf_compiled_path)

                    # Affichage de la confirmation si nécessaire
                    if affiche_details and compilation_options["verbose"] in ["normal"]:
                        self.msg.affiche_messages(
                            [["OK !", "success"]], "resultat_item"
                        )

                except subprocess.CalledProcessError:
                    message_erreur_compilation = [
                        "Erreur lors de la compilation LaTeX de la version "
                        f"{fic['affichage_nom_version']}",
                        "error",
                    ]
                    if compilation_options["verbose"] in ["normal"]:
                        self.msg.affiche_messages(
                            [message_erreur_compilation], "resultat_item"
                        )
                    compilation_messages.append(message_erreur_compilation)
                    compilation_OK = False

                # On prépare la prochaine passe de compilation si nécessaire
                passe_compilation += 1

        # Conclusion de la phase de compilation
        nb_fichiers_compiles = len(self._liste_fichiers["compiled"])
        nb_fichiers_a_compiler = len(compilation_job_list)

        if nb_fichiers_compiles == 0:
            return "error", [["Échec de la compilation LaTeX", "fatal_error"]]
        if nb_fichiers_compiles < nb_fichiers_a_compiler:
            return "warning", [
                ["Certaines versions n'ont pas pu être compilées", "warning"]
            ]
        return "success", []

    # --- Post-traitements ---

    def _cp_copy_files(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Copie les fichiers compilés dans le dossier cible (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur la copie,
            et messages est une liste de [message, flag].
        """
        messages: List[List[str]] = []

        # Chargement de la configuration
        cfg = load_config()
        dest_folder = (
            self.file.parent / cfg.compilation.dossier_cible_par_rapport_au_fichier_tex
        )

        # On génère d'abord le fichier version si nécessaire
        if bool(cfg.compilation.copier_fichier_version):
            fichier_version_pattern = cfg.compilation.format_nom_fichier_version
            version = self._metadata.get("version", {}).get("valeur", "XXXX")
            nom_fichier_version = fichier_version_pattern.replace(
                "[numero_version]", version
            )

            # Nettoyage de l'ancien fichier version
            if not compilation_options["dry_run"]:
                try:
                    fichier_version_start, fichier_version_end = (
                        fichier_version_pattern.split("[numero_version]")
                    )
                    for fichier_path in dest_folder.iterdir():
                        if (
                            fichier_path.is_file()
                            and fichier_path.name.startswith(fichier_version_start)
                            and fichier_path.name.endswith(fichier_version_end)
                        ):
                            fichier_path.unlink()
                except Exception as e:
                    messages.append(
                        [
                            "Erreur lors du nettoyage des anciens fichiers de "
                            f"version : {e}",
                            "warning",
                        ]
                    )

            # Création du nouveau fichier version
            if not compilation_options["dry_run"]:
                try:
                    fichier_version = dest_folder / nom_fichier_version
                    if not fichier_version.exists():
                        fichier_version.touch()
                except Exception as e:
                    messages.append(
                        [
                            "Erreur lors de la création du fichier de version : "
                            f"{e}",
                            "warning",
                        ]
                    )

        # Copie des fichiers compilés
        if not compilation_options["dry_run"]:
            for fichier_path in self._liste_fichiers.get("compiled", []):
                try:
                    shutil.copy(fichier_path, dest_folder)
                except Exception as e:
                    messages.append(
                        [
                            f"Erreur lors de la copie de {fichier_path.name} : {e}",
                            "warning",
                        ]
                    )

        # On copie les fichiers compilés dans le dossier cible
        return "success", messages

    def _cp_create_zip(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Création du fichier zip

        Retourne
        --------
        tuple[Optional[Path], List[List[str]]]
            (result, messages) où result contient le Path du fichier zip créé,
            et messages est une liste de [message, flag].
        """
        # Chargement de la configuration
        cfg = load_config()
        zip_tmp_folder = self.file.parent / cfg.compilation.dossier_tmp_pour_zip

        try:
            # Création du dossier temporaire
            if not compilation_options["dry_run"]:
                zip_tmp_folder.mkdir(parents=True, exist_ok=True)

            # Copie du fichier tex dans le dossier temporaire
            fichier_source = self.file.path
            fichier_cible = zip_tmp_folder / fichier_source.name
            if not compilation_options["dry_run"]:
                shutil.copy2(fichier_source, fichier_cible)

            # Copie du dossier sources dans le dossier temporaire
            dossier_source = self.file.parent / cfg.compilation.dossier_sources_latex
            dossier_cible = zip_tmp_folder / cfg.compilation.dossier_sources_latex
            if not compilation_options["dry_run"]:
                shutil.copytree(dossier_source, dossier_cible, dirs_exist_ok=True)

            # Création du fichier zip
            nom_fichier_zip = self.file.parent / (
                str(self.file.stem) + cfg.compilation.suffixe_nom_sources
            )
            if not compilation_options["dry_run"]:
                fichier_zip = Path(
                    shutil.make_archive(
                        nom_fichier_zip.as_posix(), 'zip', zip_tmp_folder.as_posix()
                    )
                )
            else:
                fichier_zip = nom_fichier_zip.with_suffix('.zip')

            self._liste_fichiers["autres"].append(fichier_zip)

            # Suppression du dossier temporaire
            if not compilation_options["dry_run"]:
                shutil.rmtree(zip_tmp_folder.as_posix())

        except Exception as e:
            return None, [[f"Erreur lors de la création du zip : {e}.", "warning"]]

        return "success", []

    def _cp_create_info_file(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Création du fichier info

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur la création du
            fichier info,
            et messages est une liste de [message, flag].
        """
        messages: List[List[str]] = []

        # Chargement de la configuration
        cfg = load_config()

        # On vérifie d'abord si on doit aussi uploader un diaporama
        diaporama_folder = (
            self.file.parent / cfg.compilation.dossier_cible_par_rapport_au_fichier_tex
        )
        liste_extensions_diaporama = cfg.compilation.extensions_diaporama
        nom_fichier_diaporama = self.file.stem + cfg.compilation.suffixe_nom_diaporama

        # Chercher les fichiers correspondants
        try:
            fichiers_diaporama = [
                f
                for f in diaporama_folder.iterdir()
                if f.is_file()
                and f.name.startswith(nom_fichier_diaporama)
                and f.suffix in liste_extensions_diaporama
            ]
            for diaporama in fichiers_diaporama:
                self._liste_fichiers["autres"].append(Path(diaporama))

        except Exception as e:
            messages.append(
                [f"Erreur lors de la recherche des fichiers diaporama : {e}", "warning"]
            )

        # Création du fichier info
        info_file = self.file.parent / (
            str(self.file.stem) + cfg.compilation.extension_fichier_infos_upload
        )

        if cfg.compilation.copier_pdf_dans_dossier_cible:
            local_path = (
                self.file.parent
                / cfg.compilation.dossier_cible_par_rapport_au_fichier_tex
            )
        else:
            local_path = self.file.parent

        compiled_files = [str(f.name) for f in self._liste_fichiers.get("compiled", [])]

        self._liste_fichiers["autres"].append(info_file)
        other_files = [str(f.name) for f in self._liste_fichiers.get("autres", [])]

        # Ajout d'un hash pour la sécurité FTP
        import hashlib
        import hmac

        secret_key = bytes(cfg.ftp.secret_key, 'utf-8')
        passkey = f"{self._metadata.get('id_unique', {}).get('valeur', '')}".encode()
        hash_passkey = hmac.new(secret_key, passkey, hashlib.sha256).hexdigest()

        # Contenu du fichier info
        info_file_content = {
            "key_hash": hash_passkey,
            "metadata": self._metadata,
            "compilation_parameters": self._compilation_parameters,
            "compiled_files": compiled_files,
            "other_files": other_files,
            "local_path": local_path.resolve().as_posix(),
        }

        # Enregistrement du fichier info
        try:
            if not compilation_options["dry_run"]:
                import json

                with open(info_file, "w", encoding="utf-8") as f:
                    json.dump(info_file_content, f, ensure_ascii=False, indent=4)

        except Exception as e:
            messages.append(
                [
                    f"Erreur lors de la création du fichier info : {e}. Upload annulé.",
                    "warning",
                ]
            )
            return False, messages

        return True, messages

    def _cp_upload(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Upload les fichiers compilés via FTP.

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur l'upload,
            et messages est une liste de [message, flag].
        """

        # Fonction interne pour créer un dossier distant via FTP
        def _mkdir_upload(ftp, dest_dir: str, is_local: Optional[bool] = False):
            parts = Path(dest_dir).parts

            if is_local:
                # En local, il faut créer le chemin s'il n'existe pas
                Path(dest_dir).mkdir(parents=True, exist_ok=True)

            else:
                # En distant, on crée chaque partie du chemin
                for part in parts:
                    try:
                        ftp.mkd(part)
                    except Exception:
                        pass
                    ftp.cwd(part)

        # Chargement de la configuration
        cfg = load_config()
        is_local = cfg.ftp.mode_local

        # Liste des fichiers à uploader
        liste_fichiers_a_uploader = self._liste_fichiers.get(
            "compiled", []
        ) + self._liste_fichiers.get("autres", [])

        if not is_local:
            user = cfg.ftp.user
            password = cfg.ftp.password
            host = cfg.ftp.host
            port = cfg.ftp.port
            timeout = cfg.ftp.timeout
            passive = True

            # 1. Vérification de la connexion FTP
            from ftplib import FTP

            try:
                with FTP(host, timeout=timeout) as ftp:
                    ftp.login(user=user, passwd=password)
                    ftp.voidcmd("NOOP")  # commande neutre
            except Exception as e:
                return False, [
                    [
                        f"Impossible de se connecter au FTP : {e}. Upload annulé.",
                        "warning",
                    ]
                ]

            # 2. Upload des fichiers via FTP
            remote_dir = cfg.compilation.dossier_ftp

            try:
                if not compilation_options["dry_run"]:
                    with FTP() as ftp:
                        # Connexion
                        ftp.connect(host=host, port=port, timeout=timeout)
                        ftp.login(user=user, passwd=password)
                        ftp.set_pasv(passive)

                        # Aller dans le dossier distant (ou le créer)
                        try:
                            ftp.cwd(remote_dir)
                        except Exception:
                            _mkdir_upload(ftp, remote_dir)
                            ftp.cwd(remote_dir)

                        # Upload des fichiers
                        for path in liste_fichiers_a_uploader:
                            path = Path(path)
                            if not path.is_file():
                                raise FileNotFoundError(path)

                            with path.open("rb") as f:
                                ftp.storbinary(f"STOR {path.name}", f)

                        ftp.quit()

            except Exception as e:
                return None, [[f"Erreur lors de l'upload FTP : {e}.", "warning"]]

        else:
            local_dir = cfg.ftp.mode_local_dossier
            try:
                if not compilation_options["dry_run"]:
                    _mkdir_upload(None, local_dir, is_local=True)

                    for path in liste_fichiers_a_uploader:
                        path = Path(path)
                        if not path.is_file():
                            raise FileNotFoundError(path)
                        shutil.copy2(path, Path(local_dir) / path.name)

            except Exception as e:
                return None, [
                    [
                        f"Erreur lors de la copie locale des fichiers : {e}. "
                        "Upload annulé.",
                        "warning",
                    ]
                ]

        return True, []

    def _cp_webhook_call(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Upload les fichiers compilés via FTP/Webhook (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur l'upload,
            et messages est une liste de [message, flag].
        """
        # Chargement de la configuration
        cfg = load_config()
        secret_key = bytes(cfg.site.secret_key, 'utf-8')
        webhook_url = cfg.site.webhook_upload_url

        import hashlib
        import hmac

        import requests

        # Préparation de l'appel au webhook
        payload = '{"action": "run_script"}'
        signature = hmac.new(secret_key, payload.encode(), hashlib.sha256).hexdigest()
        headers = {"X-Signature": signature}

        if not compilation_options["dry_run"]:
            try:
                response = requests.post(webhook_url, data=payload, headers=headers)
                if response.status_code != 202:
                    raise Exception(
                        f"Code de statut inattendu : {response.status_code}"
                    )
            except Exception as e:
                return None, [[f"Erreur lors de l'appel au webhook : {e}.", "warning"]]

        return "success", []

    def _cp_clean_temp_after_compilation(
        self, compilation_options: dict
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Nettoie les fichiers temporaires après la compilation.

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur le nettoyage,
            et messages est une liste de [message, flag].
        """
        # Chargement de la configuration
        cfg = load_config()
        info_file = self.file.parent / (
            str(self.file.stem) + cfg.compilation.extension_fichier_infos_upload
        )
        zip_file = self.file.parent / (
            str(self.file.stem) + cfg.compilation.suffixe_nom_sources + ".zip"
        )

        # Suppression des fichiers
        try:
            if not compilation_options["dry_run"]:
                if info_file.is_file():
                    info_file.unlink()
                if zip_file.is_file():
                    zip_file.unlink()

        except Exception as e:
            return None, [[f"Erreur lors du nettoyage des fichiers : {e}", "warning"]]

        return "success", []

    # =========================================================================
    # MÉTHODES PRIVÉES : HELPERS ET UTILITAIRES
    # =========================================================================

    def _read_fichier_parametres_compilation(
        self, fichier_path: Optional[Path] = None
    ) -> tuple[Optional[Dict], List[List[str]]]:
        """Lit un fichier de paramètres de compilation YAML (méthode interne).

        Paramètres
        ----------
        fichier_path : Optional[Path]
            Chemin vers le fichier de paramètres. Si None, utilise le fichier
            par défaut dans le même dossier que le document source.

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (parametres, messages) où parametres est un dictionnaire contenant
            les paramètres de compilation lus depuis le fichier, ou None si
            le fichier n'existe pas ou est invalide.
        """
        # Déterminer le chemin du fichier
        if fichier_path is None:
            cfg = load_config()
            fichier_path = (
                self.file.parent / cfg.compilation.nom_fichier_parametres_compilation
            )

        # Vérifier l'existence du fichier
        if not fichier_path.exists() or not fichier_path.is_file():
            return None, [
                [f"Fichier de paramètres introuvable: {fichier_path}", "info"]
            ]

        # Lire et parser le fichier YAML
        try:
            with open(fichier_path, "r", encoding="utf-8") as f:
                custom_params = yaml.safe_load(f)
                if not isinstance(custom_params, dict):
                    return None, [
                        [
                            f"Le fichier {fichier_path.name} ne contient pas un "
                            "dictionnaire valide",
                            "fatal_error",
                        ]
                    ]
                return custom_params, []
        except yaml.YAMLError as e:
            return None, [[f"Erreur YAML dans {fichier_path.name}: {e}", "fatal_error"]]
        except Exception as e:
            return None, [
                [
                    f"Erreur lors de la lecture du fichier de paramètres: {e}",
                    "error",
                ]
            ]

    def _detect_version(self) -> tuple[Optional[str], List[List[str]]]:
        """Détecte la version du document en analysant le contenu (méthode interne).

        Retourne
        --------
        tuple[Optional[str], List[List[str]]]
            (version_string, messages) où version_string peut être :
            - "UPSTI_Document_v2" (front-matter YAML)
            - "UPSTI_Document_v1" (package LaTeX)
            - "EPB_Cours" (ancien format)
            - None (version non reconnue)
        """
        try:
            content = self.content

            for line in content.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                # UPSTI_Document v2 (ligne commençant par % mais pas %%)
                if stripped.startswith("%") and not stripped.startswith("%%"):
                    if "%### BEGIN metadonnees_yaml ###" in stripped:
                        return "UPSTI_Document_v2", []

            packages = parse_package_imports(content)
            if "UPSTI_Document" in packages:
                return "UPSTI_Document_v1", []
            if "EPB_Cours" in packages:
                return "EPB_Cours", []

        except Exception as e:
            return None, [[f"Impossible de lire le fichier: {e}", "error"]]

        return "Inconnue", []

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
        cfg, cfg_errors = read_json_config()
        if cfg_errors:
            return None, cfg_errors

        cfg_meta = cfg.get("metadonnee") or {}

        # On prépare toutes les valeurs par défaut globales (via config .env)
        epoch = int(time.time())
        cfg_env = load_config()
        meta_cfg = cfg_env.meta

        valeurs_par_defaut = {
            "id_unique": f"{meta_cfg.id_document_prefixe}{epoch}",
            "variante": meta_cfg.variante,
            "matiere": meta_cfg.matiere,
            "classe": meta_cfg.classe,
            "type_document": meta_cfg.type_document,
            "titre": meta_cfg.titre,
            "version": meta_cfg.version,
            "auteur": meta_cfg.auteur,
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

        # 3. On vérifie les contraintes spécifiques à certains champs TOCHK
        for key, meta in meta_ok.items():
            params = meta.get("parametres", {})
            rules = params.get("validate_rules", {})
            raw_value = meta.get("raw_value", {})

            if not rules:
                continue

            use_default = bool(params.get("default"))

            # Règle : dict_keys - les clés doivent être dans une liste définie TOCHK
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

            # Règle : keys_in - les clés doivent appartenir aux clés d'un modèle TOCHK
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

            # Règle : sum - valeurs numériques doivent sommer à une valeur donnée TOCHK
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

            # Règle : custom_rule - règles personnalisées complexes
            if "custom_rule" in rules and isinstance(raw_value, dict):
                custom_rule = rules["custom_rule"]

                # Compétences
                if custom_rule == "competences":
                    raw_value = meta.get("raw_value", {})
                    competence_cfg = cfg.get("competence") or {}
                    competence_errors: List[str] = []

                    for filiere, declaration in raw_value.items():
                        if not isinstance(declaration, dict):
                            competence_errors.append(
                                (
                                    "La déclaration des compétences pour "
                                    f"'{filiere}' est invalide."
                                )
                            )
                            continue

                        programme_value = declaration.get("pg")
                        if programme_value in (None, ""):
                            competence_errors.append(
                                (
                                    "La filière '"
                                    f"{filiere}"
                                    "' doit indiquer un programme (clé 'pg')."
                                )
                            )
                            continue

                        programme_key = str(programme_value)
                        filiere_cfg = competence_cfg.get(filiere)
                        if not isinstance(filiere_cfg, dict):
                            competence_errors.append(
                                (
                                    "La filière '"
                                    f"{filiere}"
                                    "' n'existe pas dans la configuration."
                                )
                            )
                            continue

                        programme_cfg = filiere_cfg.get(programme_key)
                        if not isinstance(programme_cfg, dict):
                            competence_errors.append(
                                (
                                    "Le programme "
                                    f"{programme_key}"
                                    " pour la filière "
                                    f"{filiere}"
                                    " n'existe pas."
                                )
                            )
                            continue

                        competences_codes = declaration.get("cp", [])
                        if not isinstance(competences_codes, list):
                            competence_errors.append(
                                (
                                    "Les compétences sélectionnées pour "
                                    f"'{filiere}'"
                                    " doivent être une liste (clé 'cp')."
                                )
                            )
                            continue

                        missing_codes = [
                            code
                            for code in competences_codes
                            if code not in programme_cfg
                        ]
                        if missing_codes:
                            competence_errors.append(
                                (
                                    "Compétence(s) inconnue(s) pour "
                                    f"{filiere}"
                                    " (programme "
                                    f"{programme_key}"
                                    f"): {missing_codes}."
                                )
                            )

                    if competence_errors:
                        self._handle_invalid_meta(
                            meta,
                            key,
                            " ".join(competence_errors),
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
            raw_value = meta.get("raw_value", "")

            if join_key:
                # Cas 1 : valeur inconnue et pas autorisée comme custom
                if (
                    not isinstance(raw_value, dict)
                    and raw_value != ""
                    and str(raw_value) not in (cfg.get(key) or {})
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
                # Cas 2 : valeur custom autorisée (custom_can_be_not_related = True)
                elif (
                    not isinstance(raw_value, dict)
                    and raw_value != ""
                    and str(raw_value) not in (cfg.get(key) or {})
                    and params.get("custom_can_be_not_related", "")
                ):
                    meta["display_flag"] = "info"
                    errors.append(
                        [
                            f"Valeur custom autorisée pour '{key}': '{raw_value}' "
                            "n'existe pas dans la configuration.",
                            "info",
                        ]
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
                # Gestion groupée pour classe, filière et programme
                cfg_classe = cfg.get("classe") or {}
                cfg_filiere = cfg.get("filiere") or {}

                # 1. Gestion de la CLASSE
                if not meta_ok["classe"].get("raw_value"):
                    meta_ok["classe"]["raw_value"] = valeurs_par_defaut["classe"]
                    meta_ok["classe"]["type_meta"] = "default"

                # 2. Gestion de la FILIERE (dépend de la classe)
                if not meta_ok["filiere"].get("raw_value"):
                    classe_value = meta_ok["classe"]["raw_value"]

                    # Essayer de déduire la filière depuis la classe
                    selected_filiere = cfg_classe.get(classe_value, {}).get("filiere")

                    if selected_filiere:
                        meta_ok["filiere"]["raw_value"] = selected_filiere
                        # La filière est déduite seulement si la classe
                        # n'a pas été définie par défaut
                        if meta_ok["classe"].get("type_meta") != "default":
                            meta_ok["filiere"]["type_meta"] = "deducted"
                        else:
                            meta_ok["filiere"]["type_meta"] = "default"
                    else:
                        # Sinon, utiliser la valeur de filière de la classe par défaut
                        meta_ok["filiere"]["raw_value"] = cfg_classe.get(
                            valeurs_par_defaut["classe"], {}
                        ).get("filiere")
                        meta_ok["filiere"]["type_meta"] = "default"

                # 3. Gestion du PROGRAMME (dépend de la filière)
                if not meta_ok["programme"].get("raw_value"):
                    filiere_value = meta_ok["filiere"]["raw_value"]

                    # Déduire le programme depuis la filière
                    dernier_programme = cfg_filiere.get(filiere_value, {}).get(
                        "dernier_programme"
                    )
                    meta_ok["programme"]["raw_value"] = dernier_programme or ""

                    # Le programme est déduit seulement si la filière
                    # n'a pas été définie par défaut
                    if meta_ok["filiere"].get("type_meta") != "default":
                        meta_ok["programme"]["type_meta"] = "deducted"
                    else:
                        meta_ok["programme"]["type_meta"] = "default"

                # 4. Gestion de la MATIERE (indépendant)
                if not meta_ok["matiere"].get("raw_value", ""):
                    meta_ok["matiere"]["raw_value"] = valeurs_par_defaut["matiere"]
                    meta_ok["matiere"]["type_meta"] = "default"

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
