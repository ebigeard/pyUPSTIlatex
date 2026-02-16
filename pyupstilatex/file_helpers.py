import fnmatch
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape

from .accessibilite import VERSIONS_ACCESSIBLES_DISPONIBLES
from .config import load_config

JSON_CONFIG_PATH = Path(__file__).resolve().parent / "pyUPSTIlatex.json"
JSON_CUSTOM_CONFIG_PATH = Path(__file__).resolve().parent / "custom/pyUPSTIlatex.json"


def read_json_config(
    path: Optional[Path | str] = None,
) -> tuple[Optional[dict], List[List[str]]]:
    """Lit le fichier JSON de configuration.

    Retourne un tuple `(data, messages)` où `data` est le dictionnaire lu
    (ou `None` en cas d'erreur) et `messages` est une liste de paires
    `[message, flag]` décrivant les erreurs/avertissements rencontrés.
    """
    messages: List[List[str]] = []

    # Fonction pour supprimer récursivement des clés selon la structure "remove"
    def apply_removals(data: dict, remove_spec: dict) -> None:
        """Supprime récursivement les clés spécifiées dans remove_spec."""
        for key, value in remove_spec.items():
            if key in data:
                if value == "remove":
                    # Supprimer cette clé
                    del data[key]
                elif isinstance(value, dict) and isinstance(data[key], dict):
                    # Descendre récursivement
                    apply_removals(data[key], value)

    # Fonction pour fusionner récursivement create_or_modify
    def deep_merge(base: dict, updates: dict) -> None:
        """Fusionne updates dans base de manière récursive."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                # Fusion récursive
                deep_merge(base[key], value)
            else:
                # Remplacement ou création
                base[key] = value

    try:
        # === 1. Lire le fichier JSON principal ===
        if path is None:
            json_path = JSON_CONFIG_PATH
        else:
            json_path = Path(path)

        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # === 2. Lire le fichier JSON custom s'il existe ===
        if path is None and JSON_CUSTOM_CONFIG_PATH.exists():
            try:
                with JSON_CUSTOM_CONFIG_PATH.open("r", encoding="utf-8") as f:
                    custom_data = json.load(f)

                # === 3. Appliquer les suppressions ===
                if "remove" in custom_data and isinstance(custom_data["remove"], dict):
                    apply_removals(data, custom_data["remove"])

                # === 4. Appliquer les créations/modifications ===
                if "create_or_modify" in custom_data and isinstance(
                    custom_data["create_or_modify"], dict
                ):
                    deep_merge(data, custom_data["create_or_modify"])

            except Exception as e:
                messages.append(
                    [
                        f"Erreur lors de la lecture du fichier custom : {e}",
                        "warning",
                    ]
                )

        return data, messages

    except Exception:
        msg = (
            "Impossible de lire le fichier pyUPSTIlatex.json. "
            "Vérifier s'il est bien présent à la racine du projet."
        )
        return None, [[msg, "error"]]


def scan_for_documents(
    root_paths: Optional[Union[str, List[str]]] = None,
    exclude_patterns: Optional[List[str]] = None,
    filter_mode: str = "compatible",
    compilable_filter: str = "all",
) -> Tuple[Optional[List[Dict[str, str]]], List[List[str]]]:
    """Scanne un ou plusieurs dossiers à la recherche de fichiers LaTeX.

    Analyse tous les fichiers .tex et .ltx trouvés et les classe selon leur
    compatibilité avec pyUPSTIlatex (UPSTI_Document ou upsti-latex).
    Retourne la liste filtrée selon le mode demandé.

    Paramètres
    ----------
    root_paths : Optional[Union[str, List[str]]], optional
        Le(s) chemin(s) du/des dossier(s) à scanner. Si None, utilise
        TRAITEMENT_PAR_LOT_DOSSIERS_A_TRAITER depuis le fichier .env.
        Défaut : None.
    exclude_patterns : Optional[List[str]], optional
        Motifs d'exclusion (glob) pour ignorer certains fichiers.
        Si None, utilise TRAITEMENT_PAR_LOT_FICHIERS_A_EXCLURE depuis .env.
        Défaut : None.
    filter_mode : str, optional
        Mode de filtrage des résultats :
        - "compatible" : retourne uniquement les fichiers UPSTI compatibles
        - "incompatible" : retourne uniquement les fichiers non compatibles
        - "all" : retourne tous les fichiers analysés
        Défaut : "compatible".
    compilable_filter : str, optional
        Filtre sur le statut de compilation des documents :
        - "compilable" : retourne uniquement les documents à compiler (a_compiler=True)
        - "non-compilable" : retourne uniquement les documents non compilables
        - "all" : retourne tous les documents sans filtrer sur ce critère
        Défaut : "all".

    Retourne
    --------
    tuple[Optional[List[Dict[str, str]]], List[List[str]]]
        Tuple (documents, messages) où :
        - documents : None si erreur fatale, sinon liste de dicts avec :
            - 'name' : nom du fichier sans extension
            - 'filename' : nom complet du fichier
            - 'path' : chemin absolu du fichier
            - 'version_pyupstilatex' : version détectée (ou "inconnue" si incompatible)
            - 'version_latex' : version détectée (ou "inconnue" si incompatible)
            - 'compatible' : bool indiquant la compatibilité
            - 'a_compiler' : bool (seulement si compatible)
        - messages : liste de [message, flag] générés durant le scan
    """
    # Import ici pour éviter l'import circulaire
    from .document import UPSTILatexDocument

    messages: List[List[str]] = []
    cfg = load_config()

    # Normalisation du mode de filtrage
    if filter_mode not in ("compatible", "incompatible", "all"):
        filter_mode = "compatible"

    # Normalisation du filtre compilable/non compilable
    if compilable_filter not in ("compilable", "non-compilable", "all"):
        compilable_filter = "all"

    # Utiliser les valeurs du .env si non spécifiées
    if root_paths is None:
        roots = list(cfg.traitement_par_lot.dossiers_a_traiter)
    elif isinstance(root_paths, (str, Path)):
        roots = [str(root_paths)]
    else:
        roots = list(root_paths)

    if not roots:
        return None, [
            [
                "Aucun dossier spécifié et aucune variable d'environnement définie.",
                "fatal_error",
            ]
        ]

    if exclude_patterns is None:
        exclude_patterns = list(cfg.traitement_par_lot.fichiers_a_exclure)
    exclude_patterns = exclude_patterns or []

    all_documents: List[Dict[str, str]] = []

    for root in roots:
        if not os.path.isdir(root):
            messages.append([f"Le dossier spécifié n'existe pas : {root}", "warning"])
            continue

        p = Path(root)
        tex_files = list(p.rglob("*.tex")) + list(p.rglob("*.ltx"))

        for file_path in tex_files:
            # Appliquer les motifs d'exclusion
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

            # Initialiser le document
            doc, doc_errors = UPSTILatexDocument.from_path(str(file_path))
            if doc_errors:
                for derr in doc_errors:
                    messages.append(
                        [
                            f"Erreur lors de la lecture de {file_path}: {derr[0]}",
                            derr[1],
                        ]
                    )
                continue
            if doc is None:
                messages.append(
                    [f"Impossible d'initialiser le document: {file_path}", "error"]
                )
                continue

            # Vérifier la lisibilité
            if not doc.is_readable:
                reason = doc.readable_reason or "Raison inconnue"
                flag = doc.readable_flag or "error"
                messages.append([f"Fichier illisible ({file_path}): {reason}", flag])
                continue

            # Vérifier si le fichier doit être ignoré (paramètre ignore=True)
            try:
                params, _ = doc.get_compilation_parameters()
                if params and params.get("ignore", False):
                    continue
            except Exception:
                # En cas d'erreur, on ne filtre pas le fichier
                pass

            # Détection de la version
            version, version_errors = doc.get_version()
            if version_errors:
                for verr in version_errors:
                    messages.append([f"{file_path}: {verr[0]}", verr[1]])

            # Déterminer la compatibilité
            compatible = version.get("pyupstilatex") is not None and version.get(
                "latex"
            ) in {
                "upsti-latex",
                "UPSTI_Document",
                "EPB_Cours",
            }

            # Préparer l'entrée du document
            doc_entry = {
                "name": file_path.stem,
                "filename": file_path.name,
                "path": str(file_path.resolve()),
                "version_pyupstilatex": version.get("pyupstilatex", "inconnue"),
                "version_latex": version.get("latex", "inconnue"),
                "compatible": compatible,
            }

            # Récupérer le paramètre de compilation pour les documents compatibles
            if compatible:
                # Les documents EPB_Cours ont toujours a_compiler = False
                if version.get("latex") == "EPB_Cours":
                    a_compiler = False
                else:
                    a_compiler = False
                    try:
                        params, _ = doc.get_compilation_parameters()
                        if params:
                            a_compiler = bool(params.get("compiler", False))
                    except Exception:
                        pass
                doc_entry["a_compiler"] = a_compiler

            all_documents.append(doc_entry)

    # Filtrer selon le mode demandé (compatible/incompatible/all)
    if filter_mode == "compatible":
        temp_documents = [d for d in all_documents if d["compatible"]]
    elif filter_mode == "incompatible":
        temp_documents = [d for d in all_documents if not d["compatible"]]
    else:  # "all"
        temp_documents = all_documents

    # Filtrer selon compilable_filter (compilable/non-compilable/all)
    # Pour les documents sans clé 'a_compiler', on considère False
    if compilable_filter == "compilable":
        filtered_documents = [
            d for d in temp_documents if bool(d.get("a_compiler", False))
        ]

    elif compilable_filter == "non-compilable":
        filtered_documents = [
            d for d in temp_documents if not bool(d.get("a_compiler", False))
        ]
    else:  # "all"
        filtered_documents = temp_documents

    # Exclure les fichiers qui correspondent aux suffixes d'accessibilité
    # Pattern: "*.{suffixe_accessibilite}.tex"
    accessibility_suffixes = [
        info.get("suffixe", "") for info in VERSIONS_ACCESSIBLES_DISPONIBLES.values()
    ]
    accessibility_patterns = [
        f"*{suffix}.tex" for suffix in accessibility_suffixes if suffix
    ]

    final_documents = []
    for doc in filtered_documents:
        filename = doc["filename"]
        # Vérifier si le nom du fichier correspond à un pattern d'accessibilité
        is_accessibility_file = any(
            fnmatch.fnmatch(filename, pattern) for pattern in accessibility_patterns
        )
        if not is_accessibility_file:
            final_documents.append(doc)

    return final_documents, messages


def create_compilation_parameter_file(
    chemin_dossier: Path, parametres: dict
) -> Tuple[bool, List[List[str]]]:
    """Crée un fichier de paramètres de compilation dans le dossier spécifié.

    Le fichier est nommé "@parametres.pyUPSTIlatex.yaml" et contient les
    paramètres de compilation au format YAML. Si le fichier existe déjà, il
    sera écrasé.

    Paramètres
    ----------
    chemin_dossier : Path
        Le chemin du dossier où créer le fichier de paramètres.
    parametres : dict
        Dictionnaire des paramètres à inclure dans le fichier YAML.

    Retourne
    --------
    Tuple[bool, List[List[str]]]
        - bool : True si le fichier a été créé avec succès, False sinon.
        - List[List[str]] : Liste de messages [message, flag] décrivant les
          erreurs ou succès rencontrés lors de la création du fichier.
    """
    cfg = load_config()
    messages: List[List[str]] = []
    nom_fichier = cfg.os.nom_fichier_parametres_compilation
    chemin_fichier = chemin_dossier / nom_fichier

    try:
        import yaml

        # Générer le code YAML
        code_yaml = yaml.dump(parametres, allow_unicode=True, sort_keys=False)

        # Charger le template
        env = get_template_env()
        template = env.get_template("yaml/parametres_compilation_rapide.yaml.j2")

        # Rendre le template avec les variables
        contenu_fichier = template.render(
            code_yaml=code_yaml, nom_fichier_yaml=nom_fichier
        )

        # Écrire le fichier
        with chemin_fichier.open("w", encoding="utf-8") as f:
            f.write(contenu_fichier)
        return True, []

    except Exception as e:
        messages.append([f"Erreur lors de la création du fichier : {e}", "error"])
        return False, messages


def create_yaml_for_poly(
    chemin_dossier: Path, poly_type: str, msg
) -> tuple[bool, List[List[str]]]:
    """Création du fichier YAML nécessaire à la génération d'un poly de TD"""

    # === 1. Préparation de la création du fichier YAML ===
    cfg = load_config()

    # Récupérer le display name (clé 'nom') correspondant au type de document
    cfg_json, cfg_json_errors = read_json_config()
    if cfg_json and isinstance(cfg_json, dict):
        type_mapping = cfg_json.get("type_document", {})
        type_entry = (
            type_mapping.get(poly_type) if isinstance(type_mapping, dict) else None
        )
        type_document_nom = (
            type_entry.get("nom")
            if isinstance(type_entry, dict) and "nom" in type_entry
            else poly_type
        )
    else:
        type_document_nom = "Inconnu"

    # Initialisation des données avec valeurs par défaut
    data_poly = {
        "version_latex": "UPSTI_Document",
        "metadonnees": {
            "type_document": poly_type,
            "titre": "[Impossible de trouver le titre]",
        },
        "parametres_compilation": {
            "versions_accessibles": [],
        },
        "logo": "[Impossible de trouver le fichier logo]",
        "fichiers": {},
    }

    # === 2. Récupération de la liste des fichiers tex dans le dossier ===
    msg.info("Récupération de la liste des fichiers tex dans le dossier", "info")
    messages_recup_liste_fichiers: List[List[str]] = []

    liste_fichiers, messages_liste_fichiers = scan_for_documents(
        chemin_dossier,
        filter_mode="compatible",
        compilable_filter="compilable",
    )
    messages_recup_liste_fichiers.extend(messages_liste_fichiers)

    # Gestion des erreurs fatales
    if liste_fichiers is None:
        return False, messages_recup_liste_fichiers

    # S'il n'y a aucun fichier
    if not liste_fichiers:
        messages_recup_liste_fichiers.append(
            ["Aucun fichier LaTeX trouvé dans le dossier spécifié.", "fatal_error"]
        )
        return False, messages_recup_liste_fichiers

    nb_fichiers = len(liste_fichiers)
    affichage_nb_fichiers = "fichier trouvé" if nb_fichiers == 1 else "fichiers trouvés"
    messages_recup_liste_fichiers.append(
        [f"{nb_fichiers} {affichage_nb_fichiers} dans le dossier.", "success"]
    )

    msg.affiche_messages(messages_recup_liste_fichiers, "resultat_item")

    # === 3. Récupération des infos du poly à partir du cours associé ===
    if poly_type in ["td"]:
        msg.info("Récupération des informations du cours associé", "info")
        messages_recuperation_cours: List[List[str]] = []

        # On remonte à la racine des TD pour déterminer le chemin du cours
        chemin_du_cours = chemin_dossier
        nb_parents = 0
        while chemin_du_cours.name != cfg.os.dossier_td:
            chemin_du_cours = chemin_du_cours.parents[0]
            nb_parents += 1
        chemin_du_cours = chemin_du_cours.parents[0] / cfg.os.dossier_cours

        # On cherche le fichier tex du cours (si plusieurs, on prend le 1er)
        liste_fichiers_cours, messages_liste_fichiers_cours = scan_for_documents(
            chemin_du_cours,
            filter_mode="compatible",
            compilable_filter="compilable",
        )
        messages_recuperation_cours.extend(messages_liste_fichiers_cours)

        if len(liste_fichiers_cours) == 0:
            if len(messages_liste_fichiers_cours) == 0:
                messages_recuperation_cours.append(
                    [
                        "Aucun fichier de cours trouvé dans le dossier "
                        f"{chemin_du_cours}",
                        "warning",
                    ]
                )

        else:
            fichier_cours = liste_fichiers_cours[0]
            from .document import UPSTILatexDocument

            doc_cours, doc_cours_errors = UPSTILatexDocument.from_path(
                fichier_cours["path"]
            )

            # Données principales du poly
            data_poly["version_latex"] = doc_cours.get_version()[0].get(
                "latex", "UPSTI_Document"
            )

            useful_metadata_keys = [
                "thematique",
                "titre",
                "matiere",
                "variante",
                "classe",
                "filiere",
                "programme",
                "auteur",
            ]

            for key in useful_metadata_keys:
                raw_status = doc_cours.get_metadata_value(key, "type_meta")
                status = (
                    raw_status.partition(":")[0] if isinstance(raw_status, str) else ""
                )
                if status not in ["default", "deducted"]:
                    value = doc_cours.get_metadata_value(key)
                    if value is not None:
                        data_poly["metadonnees"][key] = value

            # On cherche le logo
            chemin_logo = doc_cours.get_logo()
            if chemin_logo is not None:
                data_poly["logo"] = (
                    "../../../../"
                    + nb_parents * "../"
                    + cfg.os.dossier_cours
                    + "/"
                    + cfg.os.dossier_latex
                    + "/"
                    + chemin_logo
                )

            # On récupère les versions accessibles à compiler
            parametres_compilation = doc_cours.get_compilation_parameters()[0]
            data_poly["parametres_compilation"]["versions_accessibles"] = (
                parametres_compilation.get("versions_accessibles_a_compiler", [])
            )

            # Tout s'est bien passé
            messages_recuperation_cours.append(
                [
                    "Informations correctement récupérées depuis : "
                    f"{fichier_cours['path']}",
                    "success",
                ]
            )

        msg.affiche_messages(messages_recuperation_cours, "resultat_item")

    # === 4. Il faut filtrer les documents parmi les fichiers trouvés ===
    # On en profite pour récupérer les compétences couvertes
    msg.info(
        f"Filtrage des documents de type \"{type_document_nom}\" et "
        "récupération des infos nécessaires",
        "info",
    )
    messages_filtrage: List[List[str]] = []

    liste_competences: Dict = {}
    liste_filtree: List[Dict] = []
    for fichier in liste_fichiers:
        from .document import UPSTILatexDocument

        doc, doc_errors = UPSTILatexDocument.from_path(fichier["path"])
        messages_filtrage.extend(doc_errors)

        # On vérifie si c'est un TD et on récupère les infos utiles
        if doc.get_metadata_value("type_document") == poly_type:
            fichier["variante"] = doc.get_metadata_value("variante")
            fichier["programme"] = doc.get_metadata_value("programme")
            fichier["competences"] = doc.get_competences()
            liste_filtree.append(fichier)

            # Compétences - fusion des dictionnaires imbriqués
            competences = fichier.get("competences")
            if isinstance(competences, dict):
                # Parcourir les filières (ex: "PTSI-PT", "MPSI-MP")
                for filiere, programmes in competences.items():
                    if filiere not in liste_competences:
                        liste_competences[filiere] = {}

                    # Parcourir les programmes (ex: "2021", "2013")
                    if isinstance(programmes, dict):
                        for programme, codes in programmes.items():
                            if programme not in liste_competences[filiere]:
                                liste_competences[filiere][programme] = []

                            # Fusionner les codes de compétences
                            if isinstance(codes, list):
                                liste_competences[filiere][programme].extend(codes)

    # On classe par ordre alphabétique
    liste_filtree.sort(key=lambda x: x["name"])

    # Répartition des fichiers en catégories
    import hashlib

    fichiers_par_section = {}
    for fichier in liste_filtree:
        obj_fichier = Path(fichier["path"])
        nom_dossier = obj_fichier.parents[2].name
        key_dossier = hashlib.md5(nom_dossier.encode()).hexdigest()

        if key_dossier not in fichiers_par_section:
            fichiers_par_section[key_dossier] = {
                "dossier": nom_dossier,
                "liste": [obj_fichier.as_posix()],
            }
        else:
            fichiers_par_section[key_dossier]["liste"].append(obj_fichier.as_posix())

    # Transformer la structure en liste de dicts
    data_poly["fichiers"] = [
        {"section": section_data["dossier"], "liste": section_data["liste"]}
        for section_data in fichiers_par_section.values()
    ]

    # Pour chaque filière/programme, éliminer les doublons et trier
    for filiere in liste_competences:
        for programme in liste_competences[filiere]:
            # Éliminer les doublons et trier
            liste_competences[filiere][programme] = sorted(
                list(set(liste_competences[filiere][programme]))
            )

    # Génération du numéro de version
    # Pour l'instant, on va mettre une version 1.0 par défaut. On verra à l'usage
    data_poly["metadonnees"]["version"] = "1.0"

    # Affecter au dictionnaire de données
    data_poly["metadonnees"]["competences"] = liste_competences

    # Messages de filtrage
    nb_fichiers_filtres = len(liste_filtree)
    if nb_fichiers_filtres == 0:
        messages_filtrage.append(
            [f"Aucun fichier de type \"{type_document_nom}\" trouvé", "warning"]
        )
    elif nb_fichiers_filtres == 1:
        messages_filtrage.append(
            [f"1 fichier de type \"{type_document_nom}\" trouvé", "success"]
        )
    else:
        messages_filtrage.append(
            [
                f"{nb_fichiers_filtres} fichiers de type \"{type_document_nom}\" "
                "trouvés",
                "success",
            ]
        )

    msg.affiche_messages(messages_filtrage, "resultat_item")

    # === 5. Création d'une sauvegarde du fichier YAML s'il existe déjà ===
    chemin_fichier_yaml = (
        chemin_dossier / cfg.os.dossier_poly / cfg.os.nom_fichier_yaml_poly
    )

    # Si un fichier YAML déjà, on crée une copie de sauvegarde
    if chemin_fichier_yaml.exists() and chemin_fichier_yaml.is_file():
        msg.info("Création d'une sauvegarde du fichier YAML s'il existe déjà", "info")

        # Chemin de la sauvegarde (insérer la date YYYYMMDD avant l'extension)
        today = datetime.now().strftime("%Y%m%d")
        nom_fichier_backup = f"{today}-{chemin_fichier_yaml.name}.bak"

        chemin_fichier_backup = (
            chemin_fichier_yaml.parent
            / cfg.os.dossier_poly_backup_yaml
            / nom_fichier_backup
        )

        # Création du dossier de sauvegarde si nécessaire puis copie du fichier
        try:
            chemin_fichier_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(chemin_fichier_yaml, chemin_fichier_backup)
            msg.affiche_messages(
                [[f"Sauvegarde créée : {chemin_fichier_backup}", "success"]],
                "resultat_item",
            )
        except Exception as e:
            msg.affiche_messages(
                [[f"Impossible de créer la sauvegarde : {e}", "warning"]],
                "resultat_item",
            )

    # === 6. Génération du fichier YAML ===
    msg.info("Génération du fichier YAML", "info")
    messages_yaml: List[List[str]] = []

    # S'assurer que le dossier destination existe
    try:
        chemin_fichier_yaml.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        messages_yaml.append(
            [
                f"Impossible de créer le dossier {chemin_fichier_yaml.parent} : {e}",
                "error",
            ]
        )
        return False, messages_yaml

    # Écriture du YAML avec template Jinja2
    try:
        # Charger le template
        env = get_template_env()
        template = env.get_template("yaml/poly.yaml.j2")

        import yaml

        data_poly["poly_yaml"] = yaml.dump(
            data_poly, allow_unicode=True, sort_keys=False
        )

        # Ajouter une ligne vide entre chaque clé de niveau 1
        lines = data_poly["poly_yaml"].split('\n')
        formatted_lines = []
        for i, line in enumerate(lines):
            # Si c'est une clé de niveau 1 (pas d'indentation, commence par une
            # lettre/underscore) et pas la première ligne, ni un élément de liste (-)
            if (
                i > 0
                and line
                and not line[0].isspace()
                and ':' in line
                and (line[0].isalpha() or line[0] == '_')
            ):
                formatted_lines.append('')  # Ajouter une ligne vide avant
            formatted_lines.append(line)

        data_poly["poly_yaml"] = '\n'.join(formatted_lines)

        # Ajouter le nom d'affichage du type pour le template
        data_poly["poly_type_display"] = type_document_nom.upper()

        # Rendre le template
        yaml_content = template.render(**data_poly)

        # Écrire le fichier
        with chemin_fichier_yaml.open("w", encoding="utf-8") as yf:
            yf.write(yaml_content)

        msg.affiche_messages(
            [[f"Fichier YAML créé : {chemin_fichier_yaml}", "success"]],
            "resultat_item",
        )
    except Exception as e:
        messages_yaml.append(
            [
                f"Impossible d'écrire le fichier YAML : {e}",
                "error",
            ]
        )
        return False, messages_yaml

    return True, []


def create_poly(chemin_fichier_yaml: Path, msg) -> tuple[bool, List[List[str]]]:
    """Création d'un poly de TD à partir d'un fichier YAML"""

    # === 1. Lecture du fichier YAML et récupération des données ===
    msg.info("Lecture du fichier YAML et récupération des données", "info")

    try:
        import yaml

        with open(chemin_fichier_yaml, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

    except Exception as e:
        msg.affiche_messages(
            [[f"Impossible de lire le fichier YAML : {e}", "fatal_error"]],
            "resultat_item",
        )
        return False, []

    # Métadonnées et version
    metadata = yaml_data.get("metadonnees", {})
    version_latex = yaml_data.get("version_latex", "upsti-latex")

    msg.affiche_messages(
        [["Données YAML récupérées avec succès", "success"]],
        "resultat_item",
    )

    # On vérifie s'il y a bien des fichiers définis dans le YAML
    if not yaml_data.get("fichiers"):
        msg.info("Vérification de la présence de fichiers définis dans le YAML", "info")
        msg.affiche_messages(
            [["Aucun fichier défini dans le YAML", "error"]],
            "resultat_item",
        )
        return False, []

    # === 2. Création de la page de garde ===
    msg.info("Création du fichier de page de garde", "info")
    messages_creation_pdg: List[List[str]] = []

    cfg = load_config()
    chemin_dossier_pdg = chemin_fichier_yaml.parent / cfg.os.dossier_poly_page_de_garde
    chemin_fichier_pdg = chemin_dossier_pdg / cfg.os.dossier_latex / "pdg_tmp.tex"

    # Suppression du dossier (par précaution)
    if chemin_dossier_pdg.exists():
        shutil.rmtree(chemin_dossier_pdg)

    # Création du fichier tex
    from .document import UPSTILatexDocument

    pdg, messages_pdg = UPSTILatexDocument.create(
        chemin_fichier_pdg, metadata, erase=True, version=version_latex
    )
    messages_creation_pdg.extend(messages_pdg)

    # Préparation des données pour les templates
    logo = yaml_data.get("logo", "")
    liste_fichiers = yaml_data.get("fichiers", [])
    type_document_poly = pdg.get_metadata_value("type_document", "affichage")

    # Définition des templates
    template_pdg_preambule = (
        f"latex/{version_latex}/poly/page_de_garde-preambule_document.tex.j2"
    )
    template_pdg_contenu = (
        f"latex/{version_latex}/poly/page_de_garde-contenu_document.tex.j2"
    )

    # Préparer les données pour les templates
    competences_liste = metadata.get("competences", {})
    competences_codes = []
    if isinstance(competences_liste, dict):
        for filiere_data in competences_liste.values():
            if isinstance(filiere_data, dict):
                for programme_codes in filiere_data.values():
                    if isinstance(programme_codes, list):
                        competences_codes.extend(programme_codes)

    # Récupération du nom des fichiers en fonction de leur path
    fichiers_avec_titres = []
    for section_fichier in liste_fichiers:
        section_info = {"section": section_fichier.get("section", ""), "liste": []}

        for chemin_fichier in section_fichier.get("liste", []):
            # Créer une instance UPSTILatexDocument pour récupérer les métadonnées
            doc_fichier, _ = UPSTILatexDocument.from_path(chemin_fichier)

            if doc_fichier is not None:
                # Récupérer titre_activite en priorité, sinon titre
                titre_fichier = doc_fichier.get_metadata_value("titre_activite")
                if titre_fichier is None:
                    titre_fichier = doc_fichier.get_metadata_value("titre")

                # Ajouter le fichier avec son titre
                section_info["liste"].append(
                    {
                        "chemin": chemin_fichier,
                        "titre": (
                            titre_fichier if titre_fichier is not None else "Sans titre"
                        ),
                    }
                )

        fichiers_avec_titres.append(section_info)

    template_data = {
        "logo": logo,
        "fichiers": fichiers_avec_titres,
        "type_document_poly": type_document_poly,
        "competences": competences_codes,
        "parametres_UPSTI_Document": pdg.get_metadata_tex_declaration(),
    }

    # Rendre les templates
    try:
        env = get_template_env(use_latex_delimiters=True)

        # Template préambule
        template_preambule = env.get_template(template_pdg_preambule)
        contenu_preambule = template_preambule.render(**template_data).rstrip()

        # Template contenu
        template_contenu = env.get_template(template_pdg_contenu)
        contenu_contenu = template_contenu.render(**template_data).rstrip()

    except Exception as e:
        messages_creation_pdg.append(
            [f"Erreur lors du rendu des templates : {e}", "error"]
        )
        return False, messages_creation_pdg

    # Insérer les contenus dans les zones appropriées du fichier pdg
    success_preambule, messages_preambule = pdg.write_tex_zone(
        "preambule_document", contenu_preambule
    )
    if not success_preambule:
        messages_creation_pdg.extend(messages_preambule)
        return False, messages_creation_pdg

    success_contenu, messages_contenu = pdg.write_tex_zone(
        "contenu_document", contenu_contenu
    )
    if not success_contenu:
        messages_creation_pdg.extend(messages_contenu)
        return False, messages_creation_pdg

    # Écrire le fichier final sur le disque
    success_save, messages_save = pdg.save()
    if not success_save:
        messages_creation_pdg.extend(messages_save)
        return False, messages_creation_pdg

    # On va créer un fichier @parametres.pyUPSTIlatex.yaml avec compile=false
    # pour éviter que la page de garde soit re-compilée plus tard inutilement
    creation_parametres_compilation = {"ignore": True}
    success_creation_fichier, msg_cpc = create_compilation_parameter_file(
        chemin_fichier_pdg.parent, creation_parametres_compilation
    )
    if not success_creation_fichier:
        messages_creation_pdg.extend(msg_cpc)
        return False, messages_creation_pdg

    messages_creation_pdg.append(
        [f"Page de garde créée : {chemin_fichier_pdg}", "success"]
    )
    msg.affiche_messages(messages_creation_pdg, "resultat_item")

    # === 3. Compilation de la page de garde ===
    msg.info("Compilation de la page de garde", "info")
    messages_compilation_pdg: List[List[str]] = []

    # On définit les paramètres de compilation pour la page de garde
    parametres_compilation = yaml_data.get("parametres_compilation", {})
    parametres_compilation.update(
        {
            "compiler": True,
            "ignorer": False,
            "versions_a_compiler": ["prof", "eleve"],
            "renommer_automatiquement": True,
            "est_un_document_a_trous": False,
            "copier_pdf_dans_dossier_cible": True,
            "upload": False,
            "upload_diaporama": False,
        }
    )

    # Compilation avec verbosité normale pour voir les détails
    resultat_compilation, messages_compilation = pdg.compile(
        mode="deep",
        verbose="normal",
        override_compilation_params=parametres_compilation,
    )
    messages_compilation_pdg.extend(messages_compilation)

    # Récupération du chemin du fichier tex de la page de garde
    chemin_page_de_garde_tex = Path(pdg.source)

    msg.affiche_messages(messages_compilation_pdg, "resultat_item")

    # === 4. Préparation de la création des pdf  ===
    msg.info("Préparation de la création des PDF", "info")
    messages_creation_pdf: List[List[str]] = []

    try:
        # Liste des fichiers à compiler dans l'ordre
        # On garde une correspondance entre les templates et les sources
        liste_fichiers_a_combiner: List[dict] = []
        dossier_cible = cfg.os.dossier_cible_par_rapport_au_fichier_tex

        # Page de garde (pas de fichier source, pas à trous)
        liste_fichiers_a_combiner.append(
            {
                "template": (
                    chemin_page_de_garde_tex.parent
                    / dossier_cible
                    / (chemin_page_de_garde_tex.stem + "[suffixe].pdf")
                ),
                "source": None,
                "est_a_trous": False,
            }
        )

        # Fichiers du poly
        for section_fichier in liste_fichiers:
            for chemin_fichier in section_fichier.get("liste", []):
                liste_fichiers_a_combiner.append(
                    {
                        "template": (
                            Path(chemin_fichier).parent
                            / dossier_cible
                            / (Path(chemin_fichier).stem + "[suffixe].pdf")
                        ),
                        "source": chemin_fichier,
                        "est_a_trous": None,  # Sera déterminé plus tard
                    }
                )

        # On fait la liste des versions de documents à créer
        pages_par_feuille = parametres_compilation.get("nb_pages_par_feuille", 2)
        pdf_a_compiler = [
            {
                "suffixe_poly": "",
                "version": "eleve",
                "pages_par_feuille": pages_par_feuille,
                "affichage": "élève",
            },
            {
                "suffixe_poly": cfg.os.suffixe_nom_fichier_prof,
                "version": "prof",
                "pages_par_feuille": pages_par_feuille,
                "affichage": "prof",
            },
        ]

        # Versions accessibles
        versions_accessibles_a_creer = parametres_compilation.get(
            "versions_accessibles", []
        )

        if versions_accessibles_a_creer:
            for version_accessible in versions_accessibles_a_creer:
                if version_accessible in VERSIONS_ACCESSIBLES_DISPONIBLES:
                    infos_version_accessible = VERSIONS_ACCESSIBLES_DISPONIBLES[
                        version_accessible
                    ]
                    pdf_a_compiler.append(
                        {
                            "suffixe_poly": infos_version_accessible["suffixe"],
                            "version": version_accessible,
                            "pages_par_feuille": pages_par_feuille,
                            "affichage": infos_version_accessible.get(
                                "affichage", version_accessible
                            ),
                        }
                    )

    except Exception as e:
        messages_creation_pdf.append(
            [f"Erreur lors de la création du pdf : {e}", "error"]
        )
        return False, messages_creation_pdf

    messages_creation_pdf.append(
        [
            "Tout est prêt pour la création des fichiers PDF",
            "success",
        ]
    )
    msg.affiche_messages(messages_creation_pdf, "resultat_item")

    # === 5. Création des pdf  ===
    msg.titre2("Création des fichiers PDF à partir des fichiers sources", "info")
    for fichier_pdf in pdf_a_compiler:
        nom_fichier_poly = (
            f"{chemin_page_de_garde_tex.stem}{cfg.os.suffixe_nom_fichier_poly}"
            f"{fichier_pdf['suffixe_poly']}.pdf"
        )
        msg.info(f"Création du fichier PDF : {Path(nom_fichier_poly).name}", "info")
        chemin_fichier_poly = chemin_fichier_yaml.parent / nom_fichier_poly

        # Construire la liste avec les bons suffixes pour chaque fichier
        liste_fichiers_a_combiner_avec_suffixe = []

        for fichier_info in liste_fichiers_a_combiner:
            # Déterminer le suffixe approprié pour ce fichier
            if fichier_info["source"] is None:
                # Page de garde : utiliser le suffixe du poly
                suffixe = fichier_pdf["suffixe_poly"]
            else:
                # Fichier du poly : calculer le suffixe selon la version
                # et si c'est un document à trous

                # Charger le document si pas déjà fait
                if fichier_info["est_a_trous"] is None:
                    from .document import UPSTILatexDocument

                    doc, _ = UPSTILatexDocument.from_path(fichier_info["source"])
                    if doc:
                        params_doc, _ = doc.get_compilation_parameters()
                        if params_doc:
                            fichier_info["est_a_trous"] = params_doc.get(
                                "est_un_document_a_trous", False
                            )
                        else:
                            fichier_info["est_a_trous"] = False
                    else:
                        fichier_info["est_a_trous"] = False

                # Calculer le suffixe selon la version
                if fichier_pdf["version"] == "eleve":
                    # Version élève
                    if fichier_info["est_a_trous"]:
                        suffixe = cfg.os.suffixe_nom_fichier_a_trous
                    else:
                        suffixe = ""
                elif fichier_pdf["version"] == "prof":
                    # Version prof : toujours -prof
                    suffixe = cfg.os.suffixe_nom_fichier_prof
                elif fichier_pdf["version"] in VERSIONS_ACCESSIBLES_DISPONIBLES:
                    # Version accessible
                    if fichier_info["est_a_trous"]:
                        suffixe = (
                            cfg.os.suffixe_nom_fichier_a_trous
                            + VERSIONS_ACCESSIBLES_DISPONIBLES[fichier_pdf["version"]][
                                "suffixe"
                            ]
                        )
                    else:
                        suffixe = VERSIONS_ACCESSIBLES_DISPONIBLES[
                            fichier_pdf["version"]
                        ]["suffixe"]
                else:
                    suffixe = fichier_pdf["suffixe_poly"]

            # Remplacer le placeholder par le suffixe calculé
            chemin_pdf = str(fichier_info["template"]).replace("[suffixe]", suffixe)
            liste_fichiers_a_combiner_avec_suffixe.append(chemin_pdf)

        resultat_combinaison, messages_combinaison = combine_pdf(
            liste_fichiers_a_combiner_avec_suffixe,
            chemin_fichier_poly,
            fichier_pdf["pages_par_feuille"],
            parametres_compilation.get("recto_verso", True),
            parametres_compilation.get("fill_with_blank_pages", True),
        )

        msg.affiche_messages(messages_combinaison, "resultat_item")

    return True, []


def combine_pdf(
    liste_fichiers: List[Union[str, Path]],
    chemin_output_file: Union[str, Path],
    nb_pages_par_feuille: int = 2,
    recto_verso: bool = True,
    fill_with_blank_pages: bool = True,
) -> Tuple[bool, List[List[str]]]:
    """Combine plusieurs fichiers PDF en un seul avec gestion des pages blanches.

    Paramètres
    ----------
    liste_fichiers : List[Union[str, Path]]
        Liste des chemins des fichiers PDF à combiner dans l'ordre.
    chemin_output_file : Union[str, Path]
        Chemin du fichier PDF de sortie à créer.
    nb_pages_par_feuille : int, optional
        Nombre de pages par feuille (1, 2, 4, etc.). Défaut : 2.
    recto_verso : bool, optional
        Si True, impression recto-verso (multiplie par 2 le nombre de pages
        par feuille). Défaut : True.
    fill_with_blank_pages : bool, optional
        Si True, ajoute des pages blanches pour que chaque fichier soit un
        multiple du nombre de pages par feuille. Défaut : True.

    Retourne
    --------
    Tuple[bool, List[List[str]]]
        - bool : True si le fichier a été créé avec succès, False sinon.
        - List[List[str]] : Liste de messages [message, flag].

    Exemples
    --------
    Si nb_pages_par_feuille=2, recto_verso=True, fill_with_blank_pages=True :
    - Un fichier de 5 pages sera complété à 8 pages (multiple de 4)
    - Un fichier de 8 pages restera à 8 pages
    """
    messages: List[List[str]] = []

    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        messages.append(
            [
                "Le module pypdf n'est pas installé. "
                "Installez-le avec: pip install pypdf",
                "error",
            ]
        )
        return False, messages

    # Calculer le nombre de pages par bloc (tenant compte du recto-verso)
    pages_par_bloc = nb_pages_par_feuille * (2 if recto_verso else 1)

    # Créer l'objet PdfWriter pour le fichier de sortie
    pdf_writer = PdfWriter()
    total_pages_ajoutees = 0

    # Parcourir tous les fichiers de la liste
    for i, fichier in enumerate(liste_fichiers, 1):
        chemin_fichier = Path(fichier)

        # Vérifier que le fichier existe
        if not chemin_fichier.exists():
            messages.append(
                [
                    f"Fichier introuvable : {chemin_fichier}",
                    "warning",
                ]
            )
            continue

        if not chemin_fichier.is_file():
            messages.append(
                [
                    f"Le chemin n'est pas un fichier : {chemin_fichier}",
                    "warning",
                ]
            )
            continue

        # Lire le fichier PDF
        try:
            pdf_reader = PdfReader(chemin_fichier)
            nb_pages_originales = len(pdf_reader.pages)

            # Ajouter toutes les pages du fichier
            for page_num in range(nb_pages_originales):
                pdf_writer.add_page(pdf_reader.pages[page_num])

            total_pages_ajoutees += nb_pages_originales

            # Calculer le nombre de pages blanches à ajouter
            if fill_with_blank_pages and pages_par_bloc > 1:
                nb_pages_blanches = (
                    pages_par_bloc - (nb_pages_originales % pages_par_bloc)
                ) % pages_par_bloc

                # Ajouter les pages blanches
                for _ in range(nb_pages_blanches):
                    pdf_writer.add_blank_page()

                total_pages_ajoutees += nb_pages_blanches

        except Exception as e:
            messages.append(
                [
                    f"Erreur lors de la lecture de {chemin_fichier.name} : {e}",
                    "error",
                ]
            )
            continue

    # Vérifier qu'au moins une page a été ajoutée
    if total_pages_ajoutees == 0:
        messages.append(
            [
                "Aucune page n'a pu être ajoutée au PDF. "
                "Vérifiez que les fichiers sources existent et sont valides.",
                "error",
            ]
        )
        return False, messages

    # Créer le dossier de destination si nécessaire
    chemin_output = Path(chemin_output_file)
    try:
        chemin_output.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        messages.append(
            [
                f"Impossible de créer le dossier de destination : {e}",
                "error",
            ]
        )
        return False, messages

    # Écrire le fichier PDF final
    try:
        with chemin_output.open("wb") as f_out:
            pdf_writer.write(f_out)

        messages.append(
            [
                "PDF créé avec succès",
                "success",
            ]
        )
        return True, messages

    except Exception as e:
        messages.append(
            [
                f"Erreur lors de l'écriture du fichier PDF : {e}",
                "error",
            ]
        )
        return False, messages


def prepare_for_pyupstilatex_v2(
    infos_document: dict, thematique: str, msg
) -> tuple[bool, List[List[str]]]:

    cfg = load_config()
    messages: List[List[str]] = []

    # On récupère le dossier
    chemin_fichier = Path(infos_document["path"])
    dossier_document = chemin_fichier.parent

    fichier_config_yaml = dossier_document / cfg.os.nom_fichier_parametres_compilation
    if fichier_config_yaml.exists():
        return True, [
            [
                "Le fichier de configuration YAML existe déjà. Par précaution, on ne "
                "change rien.",
                "error",
            ]
        ]

    if not infos_document.get("a_ignorer", False):

        # === 1. Renommer le dossier latex sources ===
        ancien_dossier_latex = dossier_document / cfg.legacy.dossier_latex_sources
        nouveau_dossier_latex = dossier_document / cfg.os.dossier_latex_sources

        if ancien_dossier_latex.exists() and ancien_dossier_latex.is_dir():
            try:
                if nouveau_dossier_latex.exists():
                    # Vérifier si c'est le même dossier (changement de casse uniquement)
                    if (
                        ancien_dossier_latex.resolve()
                        == nouveau_dossier_latex.resolve()
                    ):
                        # Même dossier, on renomme pour changer la casse
                        ancien_dossier_latex.rename(nouveau_dossier_latex)
                    else:
                        # Dossier différent, conflit réel
                        messages.append(
                            [
                                f"Le dossier {nouveau_dossier_latex.name} existe déjà, "
                                f"impossible de renommer {ancien_dossier_latex.name}",
                                "warning",
                            ]
                        )
                else:
                    ancien_dossier_latex.rename(nouveau_dossier_latex)
            except Exception as e:
                messages.append(
                    [
                        f"Erreur lors du renommage du dossier "
                        f"{ancien_dossier_latex.name} : {e}",
                        "warning",
                    ]
                )

        # === 2. Renommer le sous-dossier images ===
        if nouveau_dossier_latex.exists():
            dossier_latex_actuel = nouveau_dossier_latex
        else:
            dossier_latex_actuel = ancien_dossier_latex

        if dossier_latex_actuel.exists() and dossier_latex_actuel.is_dir():
            ancien_dossier_images = (
                dossier_latex_actuel / cfg.legacy.dossier_latex_sources_images
            )
            nouveau_dossier_images = (
                dossier_latex_actuel / cfg.os.dossier_latex_sources_images
            )

            if ancien_dossier_images.exists() and ancien_dossier_images.is_dir():
                try:
                    if nouveau_dossier_images.exists():
                        # Vérifier si c'est le même dossier
                        if (
                            ancien_dossier_images.resolve()
                            == nouveau_dossier_images.resolve()
                        ):
                            # Même dossier, on renomme pour changer la casse
                            ancien_dossier_images.rename(nouveau_dossier_images)
                        else:
                            # Dossier différent, conflit réel
                            messages.append(
                                [
                                    f"Le dossier {nouveau_dossier_images.name} existe "
                                    "déjà, impossible de renommer "
                                    f"{ancien_dossier_images.name}",
                                    "warning",
                                ]
                            )
                    else:
                        ancien_dossier_images.rename(nouveau_dossier_images)

                except Exception as e:
                    messages.append(
                        [
                            f"Erreur lors du renommage du sous-dossier "
                            f"{ancien_dossier_images.name} : {e}",
                            "warning",
                        ]
                    )

        # === 3. Modifier les fichiers tex pour modifier src et images ===
        from .document import UPSTILatexDocument

        doc, doc_errors = UPSTILatexDocument.from_path(str(chemin_fichier))
        if doc_errors:
            messages.extend(doc_errors)

        if doc is None or not doc.is_readable:
            messages.append(
                [
                    f"Impossible de lire le fichier {chemin_fichier.name} "
                    "pour effectuer les remplacements",
                    "error",
                ]
            )
            return False, messages

        # Récupérer le contenu actuel du document
        contenu_fichier = doc.content
        if contenu_fichier is None:
            messages.append(
                [
                    f"Impossible de récupérer le contenu du fichier "
                    f"{chemin_fichier.name}",
                    "error",
                ]
            )
            return False, messages

        # Effectuer les remplacements
        contenu_modifie = contenu_fichier.replace(
            cfg.legacy.dossier_latex_sources + "/", cfg.os.dossier_latex_sources + "/"
        ).replace(
            cfg.legacy.dossier_latex_sources_images + "/",
            cfg.os.dossier_latex_sources_images + "/",
        )

        # Sauvegarder si le contenu a changé
        if contenu_modifie != contenu_fichier:
            doc.content = contenu_modifie
            success_save, messages_save = doc.save()
            if not success_save:
                messages.extend(messages_save)
                messages.append(
                    [
                        f"Erreur lors de l'écriture du fichier "
                        f"{chemin_fichier.name}",
                        "error",
                    ]
                )
                return False, messages

    # === 4. Préparer les données à inscrire dans le YAML ===
    old_compilation_parameters = {}
    new_comp_params = {}

    # En fonction des infos transmises, on peut déjà définir certains paramètres
    if infos_document.get("a_ignorer", False):
        new_comp_params["ignore"] = True

    if not infos_document.get("a_compiler", True):
        new_comp_params["compiler"] = False

    # On récupère les infos de @parametres.upsti.ini
    chemin_fichier_ini = (
        dossier_document / cfg.legacy.nom_fichier_parametres_compilation
    )

    if chemin_fichier_ini.exists() and chemin_fichier_ini.is_file():
        import configparser

        try:
            config = configparser.ConfigParser()
            config.read(chemin_fichier_ini, encoding='utf-8')

            # Convertir le ConfigParser en dictionnaire
            for section in config.sections():
                for key, value in config.items(section):
                    old_compilation_parameters[key] = value

        except Exception as e:
            messages.append(
                [
                    f"Erreur lors de la lecture du fichier "
                    f"{cfg.legacy.nom_fichier_parametres_compilation} : {e}",
                    "warning",
                ]
            )

    # On convertit les paramètres en format compatible avec le nouveau système
    new_comp_params["versions_a_compiler"] = []

    for key, value in old_compilation_parameters.items():
        if key == "est_un_document_a_trous":
            new_comp_params["est_un_document_a_trous"] = value == 1 or value == "1"

        elif key == "compiler_fichier_prof":
            if value == 1 or value == "1":
                new_comp_params["versions_a_compiler"].append("prof")

        elif key == "compiler_fichier_eleve":
            if value == 1 or value == "1":
                new_comp_params["versions_a_compiler"].append("eleve")

        elif key == "copier_fichiers_pdf_dans_dossier_cible":
            new_comp_params["copier_pdf_dans_dossier_cible"] = (
                value == 1 or value == "1"
            )

        elif key == "uploader_fichiers_sur_ftp":
            new_comp_params["upload"] = value == 1 or value == "1"

        elif key == "uploader_diaporama":
            new_comp_params["upload_diaporama"] = value == 1 or value == "1"

    # On supprime de new_comp_params les clés avec des valeurs par défaut
    # pour ne garder que les paramètres personnalisés
    keys_to_remove = []
    for key, value in new_comp_params.items():
        default_value = getattr(cfg.compilation, key, None)
        if default_value is not None:
            if isinstance(value, list) and isinstance(default_value, list):
                if set(value) == set(default_value) or len(value) == 0:
                    keys_to_remove.append(key)
            elif default_value == value:
                keys_to_remove.append(key)

    for key in keys_to_remove:
        del new_comp_params[key]

    # === 5. Créer le fichier yaml ===

    # On ajoute thematique et description pour que l'utilisateur puisse les compléter
    # dans le yaml
    new_comp_params["surcharge_metadonnees"] = {
        "thematique": thematique,
        "description": "--A compléter--",
    }

    creation_yaml, messages_yaml = create_compilation_parameter_file(
        dossier_document, new_comp_params
    )
    if not creation_yaml:
        messages.extend(messages_yaml)
        return False, messages

    # === 6. Supprimer le fichier @parametres.upsti.ini ===
    try:
        if chemin_fichier_ini.exists():
            chemin_fichier_ini.unlink()
    except Exception as e:
        messages.append(
            [
                f"Erreur lors de la suppression du fichier "
                f"{cfg.legacy.nom_fichier_parametres_compilation} : {e}",
                "warning",
            ]
        )

    if not messages:
        messages.append(["OK !", "success"])

    return True, messages


def get_template_env(use_latex_delimiters: bool = False) -> Environment:
    """Retourne l'environnement Jinja2 configuré pour les templates.

    Cherche d'abord dans custom/templates/ puis dans templates/ pour permettre
    la surcharge des templates par l'utilisateur.

    Paramètres
    ----------
    use_latex_delimiters : bool, optional
        Si True, utilise des délimiteurs compatibles LaTeX (<< >>, <% %>)
        au lieu des délimiteurs standard ({{ }}, {% %}).
        Défaut : False.

    Retourne
    --------
    Environment
        L'environnement Jinja2 avec support de surcharge de templates.
    """
    base_dir = Path(__file__).resolve().parents[1]
    custom_templates_dir = base_dir / "custom" / "templates"
    default_templates_dir = base_dir / "templates"

    # ChoiceLoader essaie les loaders dans l'ordre : custom d'abord, puis défaut
    loader = ChoiceLoader(
        [
            FileSystemLoader(custom_templates_dir),
            FileSystemLoader(default_templates_dir),
        ]
    )

    # Configuration selon le type de template
    if use_latex_delimiters:
        # Délimiteurs compatibles LaTeX pour éviter les conflits avec {}
        env = Environment(
            loader=loader,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            block_start_string='<%',
            block_end_string='%>',
            variable_start_string='<<',
            variable_end_string='>>',
        )
    else:
        # Délimiteurs standard Jinja2
        env = Environment(
            loader=loader,
            autoescape=select_autoescape(),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    return env


def check_path_readable(path: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Vérifie l'accessibilité en lecture d'un fichier.

    Teste si le chemin existe, est un fichier, et peut être lu en tant que
    fichier texte. Tente d'abord un décodage UTF-8, puis latin-1 en fallback.

    Paramètres
    ----------
    path : str
        Chemin du fichier à vérifier.

    Retourne
    --------
    Tuple[bool, Optional[str], Optional[str]]
        Tuple (accessible, raison, flag) où :
        - accessible : True si le fichier peut être lu, False sinon.
        - raison : None si accessible, sinon message décrivant l'erreur ou
          avertissement (ex: "Fichier lu en latin-1 (fallback d'encodage)").
        - flag : None si OK, 'warning' si fallback d'encodage utilisé,
          'fatal_error' si lecture impossible.

    Exemples
    --------
    >>> check_path_readable("/chemin/fichier.txt")
    (True, None, None)
    >>> check_path_readable("/chemin/fichier_inexistant.txt")
    (False, "Fichier introuvable", "fatal_error")
    """
    p = Path(path)
    if not p.exists():
        return False, "Fichier introuvable", "fatal_error"
    if not p.is_file():
        return False, "N'est pas un fichier", "fatal_error"
    try:
        # Lecture d'un octet pour forcer le décodage (et déclencher
        # UnicodeDecodeError si l'encodage est incorrect).
        # Lire 0 octet n'effectue pas de décodage.
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


def check_path_writable(path: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Vérifie l'accessibilité en écriture d'un fichier existant.

    Teste si le fichier existe et peut être ouvert en mode écriture.
    N'essaie PAS de créer le fichier s'il n'existe pas.

    Paramètres
    ----------
    path : str
        Chemin du fichier à vérifier.

    Retourne
    --------
    Tuple[bool, Optional[str], Optional[str]]
        Tuple (accessible, raison, flag) où :
        - accessible : True si le fichier peut être modifié, False sinon.
        - raison : None si accessible, sinon message décrivant l'erreur
          (ex: "Permission refusée", "Fichier introuvable").
        - flag : None si OK, 'fatal_error' si écriture impossible.

    Exemples
    --------
    >>> check_path_writable("/chemin/fichier.txt")
    (True, None, None)
    >>> check_path_writable("/chemin/readonly.txt")
    (False, "Permission refusée: ...", "fatal_error")
    """
    p = Path(path)
    if not p.exists():
        return False, "Fichier introuvable", "fatal_error"
    if not p.is_file():
        return False, "N'est pas un fichier", "fatal_error"
    try:
        # 'r+b' requiert que le fichier existe et autorise l'écriture sans le
        # tronquer
        with p.open("r+b") as _:
            pass
    except PermissionError as e:
        return False, f"Permission refusée: {e}", "fatal_error"
    except Exception as e:
        return False, f"Impossible d'ouvrir en écriture: {e}", "fatal_error"
    return True, None, None


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


def display_version(version_pyupstilatex: int, version_latex: str) -> str:
    """Retourne une chaîne de caractères affichable pour les versions détectées."""
    if version_pyupstilatex is None or version_latex is None:
        return "Inconnue"

    if isinstance(version_pyupstilatex, int):
        display_version = f"v{version_pyupstilatex}"
    else:
        display_version = str(version_pyupstilatex)

    return f"{display_version} - {version_latex}"


def format_nom_documents_for_display(
    documents: List[Dict[str, str]], max_length: int = 88
) -> List[Dict[str, str]]:
    """Ajoute des informations de formatage pour l'affichage des documents.

    Ajoute une clé 'display_path' à chaque document contenant le chemin
    tronqué pour l'affichage (limité à max_length caractères).

    Paramètres
    ----------
    documents : List[Dict[str, str]]
        Liste des documents à formater. Chaque dict doit contenir au minimum
        une clé 'path'.
    max_length : int, optional
        Longueur maximale du chemin d'affichage en caractères.
        Défaut : 88.

    Retourne
    --------
    List[Dict[str, str]]
        La même liste de documents, modifiée en place avec ajout de
        'display_path'.
    """
    _add_truncated_paths(documents, max_length)
    return documents


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
