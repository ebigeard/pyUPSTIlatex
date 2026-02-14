"""
Handlers de version pour les documents UPSTI.

Ce module implémente le pattern Strategy pour gérer les opérations
spécifiques à chaque version de document :
- Version de pyupstilatex (v1, v2) : format de stockage des métadonnées
- Version du package LaTeX (upsti-latex, UPSTI_Document, ...) : fonctionnalités LaTeX
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .accessibilite import VERSIONS_ACCESSIBLES_DISPONIBLES
from .file_helpers import read_json_config
from .file_latex_helpers import (
    find_tex_entity,
    parse_metadata_tex,
    parse_metadata_yaml,
    read_tex_zone,
    write_tex_zone,
)

if TYPE_CHECKING:
    from .document import UPSTILatexDocument


# =============================================================================
# HANDLERS POUR LES VERSIONS PYUPSTILATEX
# =============================================================================


class DocumentPyUpstiLatexVersionHandler(ABC):
    """Classe de base abstraite pour les handlers de version.

    Chaque version de document (v1, v2) doit implémenter cette interface
    pour définir ses propres méthodes de manipulation des métadonnées et
    de génération de contenu.
    """

    def __init__(self, document: "UPSTILatexDocument"):
        """Initialise le handler avec une référence au document parent.

        Paramètres
        ----------
        document : UPSTILatexDocument
            Le document parent qui utilise ce handler.
        """
        self.document = document

    @abstractmethod
    def parse_metadata(self) -> Tuple[Optional[Dict], List[List[str]]]:
        """Parse les métadonnées selon le format de la version.

        Retourne
        --------
        Tuple[Optional[Dict], List[List[str]]]
            (metadata_dict, messages) où metadata_dict contient les métadonnées
            brutes extraites du document, et messages contient les erreurs/warnings.
        """
        pass

    def set_metadata(self, key: str, value: any) -> Tuple[bool, List[List[str]]]:
        """Ajoute ou modifie une métadonnée dans le document.

        Paramètres
        ----------
        key : str
            La clé de la métadonnée.
        value : any
            La valeur de la métadonnée.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (success, messages) où success indique si l'opération a réussi.
        """
        return True, []

    def delete_metadata(self, key: str) -> Tuple[bool, List[List[str]]]:
        """Supprime une métadonnée du document.

        Paramètres
        ----------
        key : str
            La clé de la métadonnée à supprimer.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (success, messages) où success indique si l'opération a réussi.
        """
        return True, []


class HandlerPyUpstiLatexV1(DocumentPyUpstiLatexVersionHandler):
    """Handler pour les documents UPSTI_Document.

    Les documents v1 stockent leurs métadonnées directement dans le code LaTeX
    sous forme de commandes personnalisées (\\UPSTImetaXXX{...}).
    """

    def parse_metadata(self) -> Tuple[Optional[Dict], List[List[str]]]:
        """Parse les métadonnées depuis le contenu LaTeX.

        Utilise le parser LaTeX pour extraire les commandes \\UPSTImetaXXX.

        Retourne
        --------
        Tuple[Optional[Dict], List[List[str]]]
            Dictionnaire des métadonnées extraites et liste de messages.
        """
        return parse_metadata_tex(self.document.content)


class HandlerPyUpstiLatexV2(DocumentPyUpstiLatexVersionHandler):
    """Handler pour les documents upsti-latex.

    Les documents v2 stockent leurs métadonnées dans un bloc YAML
    (front-matter) au début du fichier.
    """

    def parse_metadata(self) -> Tuple[Optional[Dict], List[List[str]]]:
        """Parse les métadonnées depuis le front-matter YAML.

        Utilise le parser YAML pour extraire les métadonnées du bloc
        délimité par --- au début du fichier.

        Retourne
        --------
        Tuple[Optional[Dict], List[List[str]]]
            Dictionnaire des métadonnées extraites et liste de messages.
        """
        return parse_metadata_yaml(self.document.content)

    def set_metadata(self, key: str, value: any) -> Tuple[bool, List[List[str]]]:
        """Ajoute une métadonnée dans le bloc YAML.

        Paramètres
        ----------
        key : str
            Nom de la métadonnée.
        value : any
            Valeur de la métadonnée (doit être sérialisable en YAML).

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (True, []) si succès, (False, errors) sinon.
        """
        errors: List[List[str]] = []

        try:
            import yaml

            content = self.document.content

            # Extraire le bloc YAML avec read_tex_zone
            yaml_block = read_tex_zone(
                content, "metadonnees_yaml", remove_comment_char=True
            )
            if not yaml_block:
                errors.append(
                    [
                        "Le document ne contient pas de zone metadonnees_yaml valide.",
                        "error",
                    ]
                )
                return False, errors

            # Prétraiter le bloc YAML (comme dans parse_metadata_yaml)
            yaml_block = yaml_block.expandtabs(4)

            # Parser le YAML
            metadata = yaml.safe_load(yaml_block) or {}

            # Vérifier si la clé existe déjà
            if key in metadata:
                errors.append(
                    [
                        f"La métadonnée '{key}' existe déjà. "
                        "Utilisez modifier_metadonnee pour la changer.",
                        "error",
                    ]
                )
                return False, errors

            # Ajouter la nouvelle métadonnée
            metadata[key] = value

            # Reconstruire le YAML
            new_yaml = yaml.dump(metadata, allow_unicode=True, sort_keys=False)

            # Ajouter les commentaires LaTeX
            new_yaml_commented = "\n".join(
                f"% {line}" for line in new_yaml.strip().split("\n")
            )

            # Écrire dans la zone avec write_tex_zone
            new_content = write_tex_zone(
                content, "metadonnees_yaml", new_yaml_commented
            )

            # Écrire le nouveau contenu
            self.document.file.write(new_content)

            # Invalider le cache
            self.document._metadata = None

            errors.append([f"Métadonnée '{key}' ajoutée avec succès.", "info"])
            return True, errors

        except Exception as e:
            errors.append([f"Erreur lors de l'ajout de la métadonnée: {e}", "error"])
            return False, errors

    def delete_metadata(self, key: str) -> Tuple[bool, List[List[str]]]:
        """Supprime une métadonnée du bloc YAML.

        Paramètres
        ----------
        key : str
            Nom de la métadonnée à supprimer.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (True, []) si succès, (False, errors) sinon.
        """
        errors: List[List[str]] = []

        try:
            import yaml

            content = self.document.content

            # Extraire le bloc YAML avec read_tex_zone
            yaml_block = read_tex_zone(
                content, "metadonnees_yaml", remove_comment_char=True
            )
            if not yaml_block:
                errors.append(
                    [
                        "Le document ne contient pas de zone metadonnees_yaml valide.",
                        "error",
                    ]
                )
                return False, errors

            # Prétraiter le bloc YAML
            yaml_block = yaml_block.expandtabs(4)

            # Parser le YAML
            metadata = yaml.safe_load(yaml_block) or {}

            # Vérifier si la clé existe
            if key not in metadata:
                errors.append([f"La métadonnée '{key}' n'existe pas.", "error"])
                return False, errors

            # Supprimer la métadonnée
            del metadata[key]

            # Reconstruire le YAML
            new_yaml = yaml.dump(metadata, allow_unicode=True, sort_keys=False)

            # Ajouter les commentaires LaTeX
            new_yaml_commented = "\n".join(
                f"% {line}" for line in new_yaml.strip().split("\n")
            )

            # Écrire dans la zone avec write_tex_zone
            new_content = write_tex_zone(
                content, "metadonnees_yaml", new_yaml_commented
            )

            # Écrire le nouveau contenu
            self.document.file.write(new_content)

            # Invalider le cache
            self.document._metadata = None

            errors.append([f"Métadonnée '{key}' supprimée avec succès.", "info"])
            return True, errors

        except Exception as e:
            errors.append(
                [f"Erreur lors de la suppression de la métadonnée: {e}", "error"]
            )
            return False, errors


# =============================================================================
# HANDLERS POUR LES PACKAGES LATEX
# =============================================================================


class DocumentLatexVersionHandler(ABC):
    """Classe de base abstraite pour les handlers de package LaTeX.

    Gère les opérations spécifiques à chaque package LaTeX utilisé
    (upsti-latex, UPSTI_Document, EPB_Cours).
    """

    def __init__(self, document: "UPSTILatexDocument"):
        """Initialise le handler avec une référence au document parent.

        Paramètres
        ----------
        document : UPSTILatexDocument
            Le document parent qui utilise ce handler.
        """
        self.document = document

    @abstractmethod
    def get_package_name(self) -> str:
        """Retourne le nom du package LaTeX.

        Retourne
        --------
        str
            Nom du package (ex: "upsti-latex", "UPSTI_Document").
        """
        pass

    def get_logo(self) -> Optional[str]:
        """Retourne le chemin ou la valeur du logo d'un cours, par exemple.

        Retourne
        --------
        Optional[str]
            Le chemin ou la valeur du logo, ou None si non défini.
        """
        return None

    def get_metadata_tex_declaration(self) -> str:
        """Génère les déclarations LaTeX des métadonnées du document.

        Pour UPSTI_Document, génère les commandes \\newcommand correspondant
        à chaque métadonnée (en fonction de tex_type et tex_key définis dans
        la configuration JSON).
        Pour upsti-latex, les métadonnées sont déjà dans le front-matter YAML,
        donc retourne une chaîne vide.

        Retourne
        --------
        str
            Les déclarations LaTeX (une par ligne), ou chaîne vide.
        """
        return None

    def set_metadata(self, key: str, value: any) -> Tuple[bool, List[List[str]]]:
        """Ajoute ou modifie une métadonnée dans le document.

        Paramètres
        ----------
        key : str
            La clé de la métadonnée.
        value : any
            La valeur de la métadonnée.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (success, messages) où success indique si l'opération a réussi.
        """
        return True, []

    def delete_metadata(self, key: str) -> Tuple[bool, List[List[str]]]:
        """Supprime une métadonnée du document.

        Paramètres
        ----------
        key : str
            La clé de la métadonnée à supprimer.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (success, messages) où success indique si l'opération a réussi.
        """
        return True, []

    def set_version_accessible(
        self, version_accessible: str
    ) -> Tuple[str, List[List[str]]]:
        """Génère le fichier modifié pour être rendu accessible

        Paramètres
        ----------
        version_accessible : str
            La version désirée (ex: "dys", "dv").

        Retourne
        --------
        Tuple[str, List[List[str]]]
            (content, messages) où content est le contenu modifié du document
            et messages contient les informations ou erreurs.
        """
        return self.document.content, []


class HandlerLatexUpstiLatex(DocumentLatexVersionHandler):
    """Handler pour le package LaTeX upsti-latex."""

    def get_package_name(self) -> str:
        return "upsti-latex"


class HandlerLatexUPSTIDocument(DocumentLatexVersionHandler):
    """Handler pour le package LaTeX UPSTI_Document."""

    def get_package_name(self) -> str:
        return "UPSTI_Document"

    def get_logo(self) -> Optional[str]:
        """Retourne le contenu de \\UPSTIlogoPageDeGarde.

        Retourne
        --------
        Optional[str]
            Le contenu de la commande \\UPSTIlogoPageDeGarde, ou None si non définie.
        """
        try:
            content = self.document.content
            parsed = find_tex_entity(content, "UPSTIlogoPageDeGarde", kind="command")

            # parsed est une liste...
            if parsed and len(parsed) > 0:
                first_occurrence = parsed[0]
                args = first_occurrence.get("args", [])
                if args and len(args) > 0:
                    return args[0].get("value")

            return None
        except Exception:
            return None

    def get_metadata_tex_declaration(self) -> str:
        """Génère les déclarations LaTeX des métadonnées pour UPSTI_Document.

        Parcourt toutes les métadonnées du document et génère les commandes
        LaTeX correspondantes en fonction de tex_type et tex_key définis
        dans pyUPSTIlatex.json.

        - tex_type == "command_declaration" : génère \\newcommand{\\<tex_key>}{<valeur>}
          où <valeur> est l'id_upsti_document pour les champs relationnels (join_key),
          ou la raw_value pour les champs simples.
        - tex_type == "package_option_programme" : ignoré (géré par \\usepackage).

        Retourne
        --------
        str
            Bloc de déclarations \\newcommand, une par ligne.
        """
        from .config import load_config

        cfg_generale = load_config()
        cfg_default_meta = cfg_generale.meta

        # Charger la config JSON
        cfg, cfg_errors = read_json_config()
        if cfg is None:
            return ""

        cfg_meta = cfg.get("metadonnee", {})

        # Récupérer les métadonnées du document
        metadata, _ = self.document.get_metadata()
        if metadata is None:
            return ""

        declarations = []

        for key, meta_config in cfg_meta.items():
            params = meta_config.get("parametres", {})
            tex_key = params.get("tex_key")
            tex_type = params.get("tex_type", "")
            tex_command_override = params.get("tex_command_override", False)

            if not tex_key or tex_type != "command_declaration":
                continue

            # Récupérer les données de la métadonnée dans le document
            meta_data = metadata.get(key)
            if meta_data is None:
                continue

            raw_value = meta_data.get("raw_value", "")
            if raw_value == "" or raw_value is None:
                continue

            # Si la meta n'appartient pas à une liste prédéfinie, on vérifie que sa
            # valeur n'est pas la valeur par défaut
            required_meta_data = ["id_unique", "version", "variante", "classe", "titre"]
            if key not in required_meta_data:
                default_value = None
                if cfg_default_meta is not None:
                    default_value = getattr(cfg_default_meta, key, None)

                if raw_value == default_value:
                    continue

            # Déterminer la valeur à utiliser pour la déclaration
            join_key = params.get("join_key", "")

            if join_key and not isinstance(raw_value, dict):
                # Valeur relationnelle : récupérer id_upsti_document depuis la config
                cfg_section = cfg.get(key, {})
                entry = cfg_section.get(str(raw_value), {})
                tex_value = entry.get("id_upsti_document", raw_value)
            elif isinstance(raw_value, dict):
                # Valeur custom (dict) : utiliser 0 comme marqueur
                tex_value = 0
            elif isinstance(raw_value, bool):
                tex_value = "1" if raw_value else "0"
            else:
                tex_value = raw_value

            if tex_command_override:
                declarations.append(
                    f"\\ifdef{{\\{tex_key}}}{{\\renewcommand{{\\{tex_key}}}{{{tex_value}}}}}"
                    f"{{\\newcommand{{\\{tex_key}}}{{{tex_value}}}}}"
                )
            else:
                declarations.append(f"\\newcommand{{\\{tex_key}}}{{{tex_value}}}")

            # Gérer les custom_tex_keys pour les valeurs custom (dict)
            custom_tex_keys = params.get("custom_tex_keys", [])
            if isinstance(raw_value, dict) and custom_tex_keys:
                for custom_entry in custom_tex_keys:
                    champ = custom_entry.get("champ", "")
                    custom_key = custom_entry.get("tex_key", "")
                    if custom_key and champ in raw_value:
                        declarations.append(
                            f"\\newcommand{{\\{custom_key}}}{{{raw_value[champ]}}}"
                        )

        return "\n".join(declarations)

    def set_metadata(self, key: str, value: any) -> Tuple[bool, List[List[str]]]:
        """Ajoute ou modifie une métadonnée en insérant/modifiant une commande LaTeX.

        Pour les documents v1, recherche la commande correspondant à `key` via
        la configuration JSON (metadonnee[key]["parametres"]["tex_key"]).
        Si la commande existe déjà (ligne non commentée), elle est modifiée.
        Sinon, elle est ajoutée en haut du fichier.

        Paramètres
        ----------
        key : str
            Nom de la métadonnée (ex: "titre", "auteur").
        value : any
            Valeur de la métadonnée (sera convertie en string).

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (True, messages) si succès, (False, errors) sinon.
        """
        errors: List[List[str]] = []

        try:
            # 1. Charger la config pour obtenir tex_key
            cfg, cfg_errors = read_json_config()
            if cfg_errors:
                return False, cfg_errors
            if cfg is None:
                errors.append(
                    ["Configuration JSON introuvable ou invalide.", "fatal_error"]
                )
                return False, errors

            cfg_meta = cfg.get("metadonnee", {})
            meta_config = cfg_meta.get(key)
            if not meta_config:
                errors.append(
                    [
                        f"La métadonnée '{key}' n'est pas définie "
                        "dans la configuration.",
                        "error",
                    ]
                )
                return False, errors

            params = meta_config.get("parametres", {})
            tex_key = params.get("tex_key")
            if not tex_key:
                errors.append(
                    [
                        f"La métadonnée '{key}' n'a pas de 'tex_key' défini dans "
                        "la configuration.",
                        "error",
                    ]
                )
                return False, errors

            # 2. Vérifier si la commande existe déjà
            content = self.document.content
            existing = find_tex_entity(content, tex_key, kind="command_declaration")

            # 3. Construire la nouvelle déclaration
            new_declaration = f"\\newcommand{{\\{tex_key}}}{{{value}}}\n"

            if existing:
                # La commande existe : on la remplace
                # Trouver la ligne contenant cette déclaration
                lines = content.splitlines(keepends=True)
                new_lines = []
                replaced = False

                for line in lines:
                    # Ignorer les lignes commentées
                    stripped = line.lstrip()
                    if stripped.startswith("%"):
                        new_lines.append(line)
                        continue

                    # Vérifier si la ligne contient la déclaration
                    line_parsed = find_tex_entity(
                        line, tex_key, kind="command_declaration"
                    )
                    if line_parsed and not replaced:
                        # Remplacer cette ligne
                        new_lines.append(new_declaration)
                        replaced = True
                    else:
                        new_lines.append(line)

                new_content = "".join(new_lines)
                message = f"Métadonnée '{key}' (\\{tex_key}) modifiée avec succès."

            else:
                # La commande n'existe pas : on l'insère après \usepackage{...}}
                lines = content.splitlines(keepends=True)
                new_lines = []
                inserted = False

                for line in lines:
                    new_lines.append(line)

                    # Chercher \usepackage ou \RequirePackage{UPSTI_Document}
                    if not inserted and not line.lstrip().startswith("%"):
                        if "\\usepackage" in line or "\\RequirePackage" in line:
                            if "UPSTI_Document" in line:
                                # Insérer la nouvelle commande juste après
                                new_lines.append(new_declaration)
                                inserted = True

                if not inserted:
                    # Si on n'a pas trouvé le package, on insère en haut du fichier
                    new_lines.insert(0, new_declaration)

                new_content = "".join(new_lines)
                message = f"Métadonnée '{key}' (\\{tex_key}) ajoutée avec succès."

            # 4. Écrire le nouveau contenu
            self.document.file.write(new_content)

            # 5. Invalider le cache des métadonnées
            self.document._metadata = None

            errors.append([message, "info"])
            return True, errors

        except Exception as e:
            errors.append(
                [f"Erreur lors de l'ajout/modification de la métadonnée: {e}", "error"]
            )
            return False, errors

    def delete_metadata(self, key: str) -> Tuple[bool, List[List[str]]]:
        """Supprime une métadonnée en retirant la commande LaTeX.

        Paramètres
        ----------
        key : str
            Nom de la métadonnée à supprimer.

        Retourne
        --------
        Tuple[bool, List[List[str]]]
            (True, []) si succès, (False, errors) sinon.
        """
        errors: List[List[str]] = []

        try:
            import re

            content = self.document.content

            # Pattern pour trouver la ligne complète avec \UPSTImeta<key>{valeur}
            pattern = rf"\\UPSTImeta{re.escape(key)}\{{[^}}]*\}}\n?"

            if not re.search(pattern, content):
                errors.append([f"La métadonnée '{key}' n'existe pas.", "error"])
                return False, errors

            # Supprimer la ligne
            new_content = re.sub(pattern, "", content)

            # Écrire le nouveau contenu
            self.document.file.write(new_content)

            # Invalider le cache
            self.document._metadata = None

            errors.append([f"Métadonnée '{key}' supprimée avec succès.", "info"])
            return True, errors

        except Exception as e:
            errors.append(
                [f"Erreur lors de la suppression de la métadonnée: {e}", "error"]
            )
            return False, errors

    def set_version_accessible(
        self, version_accessible: str
    ) -> Tuple[str, List[List[str]]]:
        """Génère le fichier modifié pour être rendu accessible

        Paramètres
        ----------
        version_accessible : str
            La version désirée (ex: "dys", "dv").

        Retourne
        --------
        Tuple[str, List[List[str]]]
            (content, messages) où content est le contenu modifié du document
            et messages contient les informations ou erreurs.
        """
        messages: List[List[str]] = []

        # Contenu initial du document
        modified_content = self.document.content

        if version_accessible not in VERSIONS_ACCESSIBLES_DISPONIBLES:
            return modified_content, [
                [
                    f"Version accessible '{version_accessible}' non reconnue.",
                    "warning",
                ]
            ]

        # Définir les substitutions selon la version
        chaines_a_substituer = []
        chaines_de_substitution = []

        # Pour chaque version accessible, on applique les modifications spécifiques
        if version_accessible == "dys":
            chaines_a_substituer = ['\\documentclass[11pt]{article}']
            chaines_de_substitution = [
                (
                    "\\documentclass[12pt]{article}\n\n"
                    "% Version dys\n"
                    "\\usepackage{tgheros}\n"
                    "\\renewcommand{\\familydefault}{\\sfdefault}\n"
                    "\\usepackage[bitstream-charter]{mathdesign}\n"
                    "\\let\\circledS\\relax\n"
                )
            ]

        # Version pour déficients visuels
        elif version_accessible == "dv":
            chaines_a_substituer = [
                '\\documentclass[11pt]{article}',
                '\\begin{document}',
            ]
            chaines_de_substitution = [
                (
                    "\\documentclass[12pt]{article}\n"
                    "\\usepackage{helvet}\n"
                    "\\renewcommand{\\familydefault}{\\sfdefault}"
                ),
                "\\begin{document}\n\\LARGE",
            ]

        # Appliquer les substitutions
        if len(chaines_a_substituer) != len(chaines_de_substitution):
            messages.append(
                [
                    "Erreur interne: nombre de substitutions incohérent.",
                    "error",
                ]
            )
            return modified_content, messages

        for chaine_originale, chaine_remplacante in zip(
            chaines_a_substituer, chaines_de_substitution
        ):
            if chaine_originale in modified_content:
                modified_content = modified_content.replace(
                    chaine_originale, chaine_remplacante
                )

        return modified_content, messages


class HandlerLatexEPBCours(DocumentLatexVersionHandler):
    """Handler pour le package LaTeX EPB_Cours (ancien format, non supporté)."""

    def get_package_name(self) -> str:
        return "EPB_Cours"
