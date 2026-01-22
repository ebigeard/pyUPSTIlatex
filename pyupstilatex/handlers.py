"""
Handlers de version pour les documents UPSTI.

Ce module implémente le pattern Strategy pour gérer les opérations
spécifiques à chaque version de document (v1, v2) sans dupliquer
le code dans la classe principale UPSTILatexDocument.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .parsers import find_tex_entity, parse_metadata_tex, parse_metadata_yaml
from .utils import read_json_config

if TYPE_CHECKING:
    from .document import UPSTILatexDocument


class DocumentVersionHandler(ABC):
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

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass


class HandlerUPSTIDocumentV1(DocumentVersionHandler):
    """Handler pour les documents UPSTI_Document_v1.

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
            self.document.storage.write_text(self.document.source, new_content)

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


class HandlerUPSTIDocumentV2(DocumentVersionHandler):
    """Handler pour les documents UPSTI_Document_v2.

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

            # Extraire le bloc YAML
            if not content.startswith("---"):
                errors.append(
                    [
                        "Le document ne contient pas de front-matter YAML valide.",
                        "error",
                    ]
                )
                return False, errors

            # Trouver la fin du bloc YAML
            parts = content.split("---", 2)
            if len(parts) < 3:
                errors.append(
                    ["Format YAML invalide (manque le délimiteur de fin ---).", "error"]
                )
                return False, errors

            yaml_content = parts[1]
            rest_content = parts[2]

            # Parser le YAML
            metadata = yaml.safe_load(yaml_content) or {}

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

            # Reconstruire le fichier
            new_yaml = yaml.dump(metadata, allow_unicode=True, sort_keys=False)
            new_content = f"---\n{new_yaml}---{rest_content}"

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

            # Extraire et parser le YAML
            if not content.startswith("---"):
                errors.append(
                    [
                        "Le document ne contient pas de front-matter YAML valide.",
                        "error",
                    ]
                )
                return False, errors

            parts = content.split("---", 2)
            if len(parts) < 3:
                errors.append(
                    ["Format YAML invalide (manque le délimiteur de fin ---).", "error"]
                )
                return False, errors

            yaml_content = parts[1]
            rest_content = parts[2]

            metadata = yaml.safe_load(yaml_content) or {}

            # Vérifier si la clé existe
            if key not in metadata:
                errors.append([f"La métadonnée '{key}' n'existe pas.", "error"])
                return False, errors

            # Supprimer la métadonnée
            del metadata[key]

            # Reconstruire le fichier
            new_yaml = yaml.dump(metadata, allow_unicode=True, sort_keys=False)
            new_content = f"---\n{new_yaml}---{rest_content}"

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
