import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from slugify import slugify

from .config import load_config
from .filesystem import DocumentFile
from .logger import MessageHandler, NoOpMessageHandler
from .parsers import (
    parse_metadonnees_tex,
    parse_metadonnees_yaml,
    parse_package_imports,
)
from .storage import FileSystemStorage, StorageProtocol
from .utils import (
    check_types,
    read_json_config,
)


@dataclass
class UPSTILatexDocument:
    source: str
    storage: StorageProtocol = field(default_factory=FileSystemStorage)
    strict: bool = False
    require_writable: bool = False
    msg: MessageHandler = field(default_factory=NoOpMessageHandler)
    _metadata: Optional[Dict] = field(default=None, init=False)
    _compilation_parameters: Optional[Dict] = field(default=None, init=False)
    _commands: Optional[Dict] = field(default=None, init=False)
    _zones: Optional[Dict] = field(default=None, init=False)
    _version: Optional[str] = field(default=None, init=False)
    _file: Optional[DocumentFile] = field(default=None, init=False)

    def __post_init__(self):
        """Initialise l'accès fichier via DocumentFile."""
        self._file = DocumentFile(
            source=self.source,
            storage=self.storage,
            strict=self.strict,
            require_writable=self.require_writable,
        )

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

    @property
    def file(self) -> DocumentFile:
        """Accès direct à l'objet système de fichiers (DocumentFile)."""
        if self._file is None:
            raise RuntimeError("DocumentFile non initialisé")
        return self._file

    # Propriétés d'accès simples (délèguent à DocumentFile)
    @property
    def exists(self) -> bool:
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
        return self.file.read()

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

    @property
    def compilation_parameters(self) -> Dict:
        if self._compilation_parameters is not None:
            return self._compilation_parameters
        return self.get_compilation_parameters()[0]

    def compile(
        self, mode: str = "normal", verbose: str = "complete"
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
            - "complete" : affiche tout.
            - "normal" : affiche tout sauf les messages intermédiaires de succès.
            - "errors" : affiche juste les erreurs et warning.
            - "silent" : n'affiche rien.

        Retour
        -----
        tuple[Optional[Dict], List[List[str]]]
            Renvoie un tuple `(result, messages)` où `result` est un dictionnaire
            optionnel contenant des informations sur la compilation (p.ex. chemins,
            statuts), et `messages` est une liste de paires `[message, flag]` où
            `flag` est l'un de `info`, `warning`, `error`.
        """

        # Initialisation des retours
        result: Optional[Dict] = None
        errors: List[List[str]] = []

        # Normaliser le niveau de verbosité
        if verbose not in ("complete", "normal", "messages", "silent"):
            verbose = "normal"

        # -------------------------------------------------------------
        # 1- Vérification de l'intégrité du fichier
        # -------------------------------------------------------------
        if verbose in ("complete", "normal"):
            self.msg.info("Vérification de l'intégrité du fichier")

        file_ok, file_errors = self.file.check_file("read")

        if file_ok is False:
            return None, file_errors

        if verbose in ("complete",):
            self.msg.resultat_item("OK !", flag="success", last=True)

        # -------------------------------------------------------------
        # 2- Vérification de la version
        # -------------------------------------------------------------
        if verbose in ("complete", "normal"):
            self.msg.info("Détection de la version du document")

        version, version_errors = self.get_version()

        if version is None:
            return None, version_errors
        elif version == "EPB_Cours":
            version_errors.append(
                [
                    "Les documents EPB ne sont pas pris en charge par pyUPSTIlatex. "
                    "Il est néanmoins possible de les convertir en utilisant : "
                    "pyupstilatex migrate.",
                    "fatal_error",
                ]
            )
            return None, version_errors

        if verbose in ("complete",):
            self.msg.resultat_item("OK !", flag="success", last=True)

        # -------------------------------------------------------------
        # 3- Lecture des paramètres de compilation
        # -------------------------------------------------------------
        if verbose in ("complete", "normal"):
            self.msg.info("Lecture des paramètres de compilation")

        comp_params, comp_params_errors = self.get_compilation_parameters()

        if comp_params is None:
            return None, comp_params_errors

        if not comp_params.get("compiler", True):
            cfg = load_config()
            nom_fichier_comp = cfg.compilation.nom_fichier_parametres_compilation
            comp_params_errors.append(
                [
                    "La compilation est désactivée pour ce document "
                    "(paramètre 'compiler' à false dans le fichier "
                    f"{nom_fichier_comp}).",
                    "fatal_error",
                ]
            )
            return None, comp_params_errors

        if verbose in ("complete",):
            self.msg.resultat_item("OK !", flag="success", last=True)

        # -------------------------------------------------------------
        # 4- Lecture des métadonnées
        # -------------------------------------------------------------
        if verbose in ("complete", "normal"):
            self.msg.info("Lecture des métadonnées du fichier tex")

        metadata, metadata_messages = self.get_metadata()

        if metadata is None:
            return None, metadata_messages

        if verbose in ("complete",) and len(metadata_messages) == 0:
            metadata_messages.append(["OK !", "success"])

        self.msg.affiche_messages(metadata_messages, "resultat_item")

        # -------------------------------------------------------------
        # 5- Vérification et changement du nom du fichier
        # -------------------------------------------------------------
        if mode in ["deep"] and self.compilation_parameters.get(
            "renommer_automatiquement", False
        ):
            if verbose in ("complete", "normal"):
                self.msg.info("Vérification du nom de fichier")

            chemin, chemin_messages = self._rename_file()

            if verbose in ("complete",) and len(chemin_messages) == 0:
                chemin_messages.append(["OK !", "success"])

            self.msg.affiche_messages(chemin_messages, "resultat_item")

        # -------------------------------------------------------------
        # 6- Générer le QRCode
        # -------------------------------------------------------------
        if mode in ["deep", "normal"] and self.version == "UPSTI_Document_v2":
            if verbose in ("complete", "normal"):
                self.msg.info("Génération du QR code du document")

            qrcode, qrcode_errors = self._generate_qrcode()

            #
            # JENSUISLA !
            # TODO : creer le QRCode et l'enregistrer dans le dossier images
            #

            if verbose in ("complete",):
                self.msg.resultat_item(
                    "Fonctionnalité en cours de développement", flag="info", last=True
                )

        # -------------------------------------------------------------
        # 8- Générer le code latex à partir des métadonnées (si UPSTI_Document v2)
        # -------------------------------------------------------------
        if mode in ["deep", "normal"] and self.version == "UPSTI_Document_v2":
            if verbose in ("complete", "normal"):
                self.msg.info("Génération du code latex à partir des métadonnées")

            # template, template_errors = self._generate_latex_template()

            if verbose in ("complete",):
                self.msg.resultat_item(
                    "Fonctionnalité en cours de développement", flag="info", last=True
                )

        # -------------------------------------------------------------
        # TO CONTINUE
        # -------------------------------------------------------------
        return None, [["Test de la méthode compile", "error"]]
        # -------------------------------------------------------------

        # 9- Fichier tex v1 pour la rétrocompatibilité (sera ajouté dans les sources)
        if mode in ["deep", "normal"] and self.version == "UPSTI_Document_v2":
            step_result, step_errors = self._generate_UPSTI_Document_v1_tex_file()
            if step_errors:
                errors.extend(step_errors)
            if step_result is not None:
                result = {**(result or {}), **step_result}

        # 4- Compilation Latex (voir aussi pour bibtex, si on le gère ici)
        step_result, step_errors = self._compile_tex()
        if step_errors:
            errors.extend(step_errors)
        if step_result is not None:
            result = {**(result or {}), **step_result}

        # 5- Copie des fichiers dans le dossier cible
        if self.compilation_parameters.get("copier_pdf_dans_dossier_cible", False):
            step_result, step_errors = self._copy_compiled_files()
            if step_errors:
                errors.extend(step_errors)
            if step_result is not None:
                result = {**(result or {}), **step_result}

        # 6- Upload (création du fichier meta, du zip, upload et webhook)
        # Dans le fichier meta, on stockera aussi le dossier local
        if mode in ["deep", "normal"] and self.compilation_parameters.get(
            "upload", False
        ):
            step_result, step_errors = self._upload()
            if step_errors:
                errors.extend(step_errors)
            if step_result is not None:
                result = {**(result or {}), **step_result}

        return result, errors

    def _rename_file(self) -> tuple[Optional[str], List[List[str]]]:
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
        cfg = load_config()
        format_nom_fichier = cfg.compilation.format_nom_fichier

        if not format_nom_fichier:
            return None, [
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
            return None, [
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
            return None, cfg_json_errors
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
                return None, [
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
                    return None, [
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
                    return None, [
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
                        return None, [
                            [
                                f"Propriété '{'.'.join(parts[1:])}' introuvable pour "
                                f"'{meta_key}'. On conserve le nom de fichier initial.",
                                "warning",
                            ]
                        ]
                else:
                    return None, [
                        [
                            f"Impossible de résoudre '{placeholder}'. "
                            "On conserve le nom de fichier initial.",
                            "warning",
                        ]
                    ]

        # 5. Construire le nouveau chemin complet
        chemin_actuel = Path(self.source)
        nouveau_chemin = chemin_actuel.parent / f"{nouveau_nom}{chemin_actuel.suffix}"

        # 6. Vérifier si le nom a changé
        if nouveau_chemin == chemin_actuel:
            return None, []

        # 7. Pré-vérifications : existence du fichier source et droit en écriture
        if not chemin_actuel.exists() or not chemin_actuel.is_file():
            return None, [[f"Fichier source introuvable: {chemin_actuel}", "warning"]]

        # Utiliser l'objet DocumentFile pour vérifier l'accessibilité en écriture
        try:
            if not self.file.is_writable:
                return None, [
                    [f"Fichier non accessible en écriture: {chemin_actuel}", "warning"]
                ]
        except Exception:
            # En cas d'erreur d'accès à l'objet file, on tente quand même le renommage
            pass

        # Ne pas écraser un fichier existant
        if nouveau_chemin.exists():
            return None, [
                [
                    f"Le fichier cible existe déjà: {nouveau_chemin}. "
                    "On conserve le nom de fichier initial.",
                    "warning",
                ]
            ]

        # 8. Tenter le renommage physique
        try:
            chemin_actuel.rename(nouveau_chemin)
        except PermissionError as e:
            return None, [
                [
                    f"Permission refusée lors du renommage: {e}. "
                    "On conserve le nom de fichier initial.",
                    "warning",
                ]
            ]
        except FileExistsError as e:
            return None, [
                [
                    f"Le fichier cible existe déjà: {e}. On conserve le nom de "
                    "fichier initial.",
                    "warning",
                ]
            ]
        except Exception as e:
            return None, [
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
            return None, [
                [
                    "Renommage effectué mais impossible d'initialiser l'objet fichier.",
                    "warning",
                ]
            ]

        # 10. Suppression de tous les vieux fichiers liés (cache, compilés, etc.)
        import glob

        deleted_files: List[str] = []
        failed_deletions: List[List[str]] = []
        try:
            parent = chemin_actuel.parent
            pattern = glob.escape(chemin_actuel.stem) + "*"

            print(f"\n{pattern}\n{list(parent.glob(pattern))}\n\n")

            for p in parent.glob(pattern):
                # éviter de toucher le nouveau fichier
                try:
                    if p.resolve() == Path(self.source).resolve():
                        continue
                except Exception:
                    pass

                if p.is_file():
                    try:
                        p.unlink()
                        deleted_files.append(str(p.name))
                    except Exception as e:
                        failed_deletions.append(
                            [f"Échec suppression {p.name}: {e}", "warning"]
                        )
        except Exception as e:
            failed_deletions.append(
                [
                    f"Erreur lors de la suppression des fichiers liés: {e}",
                    "warning",
                ]
            )

        messages: List[List[str]] = []
        messages.extend(failed_deletions)
        messages.append([f"Nouveau nom : {nouveau_chemin.name}", "success"])

        return str(nouveau_chemin), messages

    def _generate_qrcode(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Génère un qrcode vers la page d'un document, à partir de l'id_unique
        (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur le fichier
            généré, et messages est une liste de [message, flag].
        """
        # On génère le qrcode
        return None, []

    def _generate_latex_template(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Génère le code LaTeX complet à partir des métadonnées (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur le fichier
            généré, et messages est une liste de [message, flag].
        """
        # On génère le code LaTeX complet à partir des métadonnées
        return None, []

    def _generate_UPSTI_Document_v1_tex_file(
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
        return None, []

    def _compile_tex(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Compile le fichier LaTeX (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur la compilation,
            et messages est une liste de [message, flag].
        """
        # On compile le fichier LaTeX (pdflatex, xelatex, lualatex, etc.)
        return None, []

    def _copy_compiled_files(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Copie les fichiers compilés dans le dossier cible (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur la copie,
            et messages est une liste de [message, flag].
        """
        # On copie les fichiers compilés dans le dossier cible
        return None, []

    def _upload(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Upload les fichiers compilés via FTP/Webhook (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (result, messages) où result contient des informations sur l'upload,
            et messages est une liste de [message, flag].
        """
        # On crée le zip, le fichier meta, et on upload via FTP/Webhook
        # Il faut mettre les meta, les parametres de config et la liste
        # des fichiers uploadés dans le fichier json/yaml meta
        return None, []

    def _parse_yaml_metadata(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Extrait les métadonnées depuis le front matter YAML (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (metadata, messages) où messages est une liste de [message, flag].
            Ne lève jamais d'exception : erreurs converties en messages.
        """
        try:
            data, errors = parse_metadonnees_yaml(self.content) or {}
            return data, errors
        except Exception as e:
            return None, [
                [f"Erreur de lecture des métadonnées YAML: {e}", "fatal_error"]
            ]

    def _parse_tex_metadata(self) -> tuple[Optional[Dict], List[List[str]]]:
        """Extrait les métadonnées depuis les commandes LaTeX v1 (méthode interne).

        Retourne
        --------
        tuple[Optional[Dict], List[List[str]]]
            (metadata, messages) où messages inclut un avertissement de version.
            Ne lève jamais d'exception : erreurs converties en messages.
        """
        try:
            data, parsing_errors = parse_metadonnees_tex(self.content)
            # version_warning = [
            #     [
            #         "Ce document utilise une ancienne version de UPSTI_Document (v1)."
            #         "Mettre à jour UPSTI_Document: pyupstilatex upgrade",
            #         "info",
            #     ]
            # ]
            # return data, version_warning + parsing_errors
            return data, parsing_errors
        except Exception as e:
            return None, [
                [f"Erreur de lecture des métadonnées LaTeX: {e}", "fatal_error"]
            ]

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

        # On reprend la version détectée, et on exécute le parser qui correspond
        version = self._version or self.version

        # Associer chaque version à sa fonction de récupération
        sources = {
            "UPSTI_Document_v1": self._parse_tex_metadata,
            "UPSTI_Document_v2": self._parse_yaml_metadata,
        }

        if version in sources:
            metadata, errors = sources[version]()

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

            formatted, formatted_errors = self._format_metadata(
                metadata, source=version
            )
            if formatted is not None:
                self._metadata = formatted
            return formatted, errors + formatted_errors

        # Version non reconnue
        return (
            None,
            [["Type de document non pris en charge par pyUPSTIlatex", "fatal_error"]],
        )

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

    def get_version(self) -> tuple[Optional[str], List[List[str]]]:
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
        self._version = version
        return version, errors

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
            doc_dir = Path(self.source).parent
            fichier_path = doc_dir / cfg.compilation.nom_fichier_parametres_compilation

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

        return None, [["Version non reconnue ou non prise en charge.", "error"]]

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
