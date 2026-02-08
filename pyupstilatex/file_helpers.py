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
            - 'version' : version détectée (ou "unknown" si incompatible)
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

            # Détection de la version
            version, version_errors = doc.get_version()
            if version_errors:
                for verr in version_errors:
                    messages.append([f"{file_path}: {verr[0]}", verr[1]])

            # Déterminer la compatibilité
            compatible = version in {
                "UPSTI_Document",
                "upsti-latex",
                "EPB_Cours",
            }

            # Préparer l'entrée du document
            doc_entry = {
                "name": file_path.stem,
                "filename": file_path.name,
                "path": str(file_path.resolve()),
                "version": version or "inconnue",
                "compatible": compatible,
            }

            # Récupérer le paramètre de compilation pour les documents compatibles
            if compatible:
                # Les documents EPB_Cours ont toujours a_compiler = False
                if version == "EPB_Cours":
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


def read_json_config(
    path: Optional[Path | str] = None,
) -> tuple[Optional[dict], List[List[str]]]:
    """Lit le fichier JSON de configuration.

    Retourne un tuple `(data, messages)` où `data` est le dictionnaire lu
    (ou `None` en cas d'erreur) et `messages` est une liste de paires
    `[message, flag]` décrivant les erreurs/avertissements rencontrés.
    """
    try:
        if path is None:
            json_path = Path(__file__).resolve().parents[1] / "pyUPSTIlatex.json"
        else:
            json_path = Path(path)
        with json_path.open("r", encoding="utf-8") as f:
            return json.load(f), []
    except Exception:
        msg = (
            "Impossible de lire le fichier pyUPSTIlatex.json. "
            "Vérifier s'il est bien présent à la racine du projet."
        )
        return None, [[msg, "error"]]


def create_yaml_for_poly(
    chemin_dossier: Path, poly_type: str, msg
) -> tuple[bool, List[List[str]]]:
    """Création du fichier YAML nécessaire à la génération d'un poly de TD"""

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
        "type_document": poly_type,
        "version_latex": "UPSTI_Document",
        "nom_chapitre": "[Impossible de trouver le nom du chapitre]",
        "logo": "[Impossible de trouver le fichier logo]",
        "classe": cfg.meta.classe,
        "variante": cfg.meta.variante,
        "versions_accessibles": [],
        "version": "1.0",
        "fichiers": {},
        "competences": [],
    }

    # 1. Récupération de la liste des fichiers tex dans le dossier
    msg.info("Récupération de la liste des fichiers tex dans le dossier", "info")
    liste_fichiers, messages_liste_fichiers = scan_for_documents(
        chemin_dossier,
        filter_mode="compatible",
        compilable_filter="compilable",
    )

    # Gestion des erreurs fatales
    if liste_fichiers is None:
        msg.affiche_messages(messages_liste_fichiers, "info")
        return False, messages_liste_fichiers

    # S'il n'y a aucun fichier
    if not liste_fichiers:
        msg.affiche_messages(
            [["Aucun fichier LaTeX trouvé dans le dossier spécifié.", "fatal_error"]],
            "resultat_item",
        )
        return False, []

    nb_fichiers = len(liste_fichiers)
    affichage_nb_fichiers = "fichier trouvé" if nb_fichiers == 1 else "fichiers trouvés"
    msg.affiche_messages(
        [[f"{nb_fichiers} {affichage_nb_fichiers}", "success"]], "resultat_item"
    )

    # 2. Récupération des infos du poly à partir du cours associé
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
            data_poly["version_latex"] = doc_cours.get_version()[0]
            data_poly["nom_chapitre"] = doc_cours.get_metadata_value("titre")
            data_poly["variante"] = doc_cours.get_metadata_value("variante")
            data_poly["classe"] = doc_cours.get_metadata_value("classe")

            # On cherche le logo
            chemin_logo = doc_cours.get_logo()
            if chemin_logo is not None:
                data_poly["logo"] = (
                    "../"
                    + nb_parents * "../"
                    + cfg.os.dossier_cours
                    + "/"
                    + cfg.os.dossier_latex
                    + "/"
                    + chemin_logo
                )

            # On récupère les versions accessibles à compiler
            parametres_compilation = doc_cours.get_compilation_parameters()[0]
            data_poly["versions_accessibles"] = parametres_compilation.get(
                "versions_accessibles_a_compiler", []
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

    # 3. Il faut filtrer les documents parmi les fichiers trouvés
    #    On en profite pour récupérer les compétences couvertes
    msg.info(
        f"Filtrage des documents de type \"{type_document_nom}\" et "
        "récupération des infos nécessaires",
        "info",
    )
    messages_filtrage: List[List[str]] = []

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

            # Compétences
            competences = fichier.get("competences")
            data_poly["competences"].extend(
                competences if isinstance(competences, list) else [competences]
            )

    # On classe par ordre alphabétique
    liste_filtree.sort(key=lambda x: x["name"])

    # Répartition des fichiers en catégories
    import hashlib

    for fichier in liste_filtree:
        obj_fichier = Path(fichier["path"])
        nom_dossier = obj_fichier.parents[2].name
        key_dossier = hashlib.md5(nom_dossier.encode()).hexdigest()

        if key_dossier not in data_poly["fichiers"]:
            data_poly["fichiers"][key_dossier] = {
                "dossier": nom_dossier,
                "liste": [obj_fichier.as_posix()],
            }
        else:
            data_poly["fichiers"][key_dossier]["liste"].append(obj_fichier.as_posix())

    # On élimine les doublons et on classe les compétences dans l'ordre
    data_poly["competences"] = sorted(list(set(data_poly["competences"])))

    # Génération du numéro de version
    # Pour l'instant, on va mettre une version 1.0 par défaut. On verra à l'usage
    data_poly["version"] = "1.0"

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

    # 4. Création d'une sauvegarde du fichier YAML s'il existe déjà
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
                [[f"Impossible de créer la sauvegarde : {e}", "error"]],
                "resultat_item",
            )

    # 5. Génération du fichier YAML
    msg.info("Génération du fichier YAML", "info")
    messages_yaml: List[List[str]] = []

    # S'assurer que le dossier destination existe
    try:
        chemin_fichier_yaml.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        msg.affiche_messages(
            [
                [
                    f"Impossible de créer le dossier {chemin_fichier_yaml.parent} : {e}",
                    "error",
                ]
            ],
            "resultat_item",
        )
        return False, [[str(e), "error"]]

    # Écriture du YAML avec template Jinja2
    try:
        # Charger le template
        env = get_template_env()
        template = env.get_template("yaml/poly.yaml.j2")

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
        msg.affiche_messages(
            [[f"Impossible d'écrire le fichier YAML : {e}", "error"]],
            "resultat_item",
        )
        return False, [[str(e), "error"]]

    return True, []


def create_poly(chemin_fichier_yaml: Path, msg) -> tuple[bool, List[List[str]]]:
    """Création d'un poly de TD à partir d'un fichier YAML"""

    # 1. Lecture du fichier YAML et récupération des données
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

    # Vérifications des données d'accessibilité
    raw = yaml_data.get("versions_accessibles", [])
    items = (
        (v.strip() for v in raw.split(","))
        if isinstance(raw, str)
        else (str(v).strip() for v in raw) if isinstance(raw, list) else ()
    )

    allowed = VERSIONS_ACCESSIBLES_DISPONIBLES
    yaml_data["versions_accessibles"] = [v for v in items if v and v in allowed]

    msg.affiche_messages(
        [["Données YAML récupérées avec succès", "success"]],
        "resultat_item",
    )

    # 2. Préparation des données du poly selon la version LaTeX
    msg.info("Vérification et normalisation des données du fichier YAML", "info")

    from .handlers import prepare_poly_data

    yaml_data_prepared, prepare_errors = prepare_poly_data(yaml_data, msg)

    # if prepare_errors:
    #     msg.affiche_messages(prepare_errors, "resultat_item")

    if yaml_data_prepared is None:
        msg.affiche_messages(
            [["Impossible de préparer les données du poly.", "fatal_error"]],
            "resultat_item",
        )
        return False, prepare_errors

    prepare_errors.append(["Données préparées avec succès", "success"])
    msg.affiche_messages(prepare_errors, "resultat_item")

    # 3. Création de la page de garde

    #
    #
    # CONTINUE: faut générer le le fichier tex et le compiler
    #
    #

    # 4. Création du pdf final

    '''
    with open(chemin_fichier_xml, "r", encoding="utf-8") as fic:
        contenu_xml = fic.read()

    # On parse le fichier xml
    soup_xml = BeautifulSoup(contenu_xml, 'xml')
    data = {}
    data["nom"] = soup_xml.find('nom').text
    data["version"] = soup_xml.find('version').text
    data["imagepagedegarde"] = "../../" + soup_xml.find('imagepagedegarde').text
    data["id_variante"] = soup_xml.find('id_variante').text
    data["id_classe"] = soup_xml.find('id_classe').text
    data["accessibilite"] = soup_xml.find('accessibilite').text

    # Fichiers
    from upsti_latex import UPSTIFichierTex

    data["fichiers"] = []
    sections = soup_xml.find('sections').findChildren("section", recursive=False)
    has_corriges = False
    for section in sections:
        # section_infos = {"titre": section.get("nom"), "nom_td": [], "fichiers_eleves": [], "fichiers_profs": []}
        section_infos = {"titre": section.get("nom"), "tds": []}
        for fichier in section.findChildren("fichier", recursive=False):
            td = {}

            # On crée une instance UPSTIFichierTex
            fichier_tex = UPSTIFichierTex(fichier.text)
            fichier_tex.get_parametres_compilation()
            fichier_tex.get_infos()

            if (
                fichier_tex.parametres_compilation["Compilation"][
                    "compiler_fichier_eleve"
                ]
                == "1"
                or fichier_tex.parametres_compilation["Compilation"][
                    "compiler_fichier_prof"
                ]
                == "1"
            ):
                td["nom"] = fichier_tex.infos["titre"]
                if (
                    fichier_tex.parametres_compilation["Compilation"][
                        "compiler_fichier_eleve"
                    ]
                    == "1"
                ):
                    nom_fichier_pdf_eleve = (
                        fichier_tex.fichier.parents[1]
                        / fichier_tex.fichier.with_suffix(".pdf").name
                    )
                    td["fichier_eleves"] = nom_fichier_pdf_eleve
                if (
                    fichier_tex.parametres_compilation["Compilation"][
                        "compiler_fichier_prof"
                    ]
                    == "1"
                ):
                    nom_fichier_pdf_prof = fichier_tex.fichier.parents[1] / (
                        str(fichier_tex.fichier.stem)
                        + self.config["Compilation"]["suffixe_nom_fichier_prof"]
                        + ".pdf"
                    )
                    td["fichier_prof"] = nom_fichier_pdf_prof
                    has_corriges = True  # Ca c'est juste pour savoir si on doit compiler une version prof de la page de garde
            section_infos["tds"].append(td)

        data["fichiers"].append(section_infos)

    # Compétences
    data["competences"] = []
    competences = soup_xml.find('competences').findChildren(
        "competence", recursive=False
    )
    for competence in competences:
        data["competences"].append(competence.text)

    self.affiche_message(
        {
            "texte": "Données récupérées.",
            "type": "resultat",
            "verbose": options["verbose"],
        }
    )

    # Création du fichier tex de la page d'accueil
    self.affiche_message(
        {
            "texte": "Génération de la page de garde",
            "type": "titre2",
            "verbose": options["verbose"],
        }
    )

    # Création du dossier pour la page de garde si nécessaire
    self.affiche_message(
        {
            "texte": "Préparation du fichier page_de_garde.tex.",
            "type": "action",
            "verbose": options["verbose"],
        }
    )
    dossier_page_de_garde = chemin_fichier_xml.parent / "page_de_garde"
    dossier_page_de_garde.mkdir(parents=True, exist_ok=True)

    template_page_de_garde = (
        self.dossier_racine / self.config["Poly_TD"]["template_page_de_garde"]
    )
    fichier_page_de_garde = dossier_page_de_garde / "page_de_garde.tex"
    if not template_page_de_garde.exists():
        self.affiche_message(
            {
                "texte": f"Le fichier {template_page_de_garde} n'existe pas.",
                "type": "error",
            }
        )
    else:
        shutil.copy(template_page_de_garde, fichier_page_de_garde)

        # Préparation des données pour éditer le fichier tex
        self.affiche_message(
            {
                "texte": "Mise à jour du fichier tex à partir des infos du fichier xml.",
                "type": "action",
                "verbose": options["verbose"],
            }
        )

        # Compétences
        tex_competences = ""
        for competence in data["competences"]:
            tex_competences += "\\UPSTIligneTableauCompetence{" + competence + "}\n"

        # Sommaire
        tex_sommaire = ""
        for section in data["fichiers"]:
            if len(data["fichiers"]) > 1:
                titre_section = section["titre"]
                if titre_section == "default":
                    titre_section = "Travaux dirigés"
                tex_sommaire += "\\subsection*{" + titre_section + "}\n"

            tex_sommaire += "\\begin{enumerate}\n"
            for td in section["tds"]:
                tex_sommaire += "\\item " + td["nom"] + "\n"
            tex_sommaire += "\\end{enumerate}\n"

        # On va remplacer les champs dans le fichier tex
        with open(fichier_page_de_garde, "r", encoding="utf-8") as fic:
            contenu_tex = fic.read()

        contenu_tex = contenu_tex.replace("***ID_VARIANTE***", data["id_variante"])
        contenu_tex = contenu_tex.replace("***ID_CLASSE***", data["id_classe"])
        contenu_tex = contenu_tex.replace("***TITRE***", data["nom"])
        contenu_tex = contenu_tex.replace("***VERSION***", data["version"])
        contenu_tex = contenu_tex.replace("***LOGO***", data["imagepagedegarde"])
        contenu_tex = contenu_tex.replace("***COMPETENCES***", tex_competences)
        contenu_tex = contenu_tex.replace("***SOMMAIRE***", tex_sommaire)

        with open(fichier_page_de_garde, "w", encoding="utf-8") as fic:
            fic.write(contenu_tex)

        self.affiche_message(
            {
                "texte": "Le fichier de page de garde est prêt à être compilé.",
                "type": "resultat",
                "verbose": options["verbose"],
            }
        )

    # Compilation de la page de garde (prof/élève si nécessaire)
    self.affiche_message(
        {
            "texte": "Compilation du fichier tex de la page de garde",
            "type": "action",
            "verbose": options["verbose"],
        }
    )

    from upsti_latex import UPSTIFichierTexACompiler

    # Paramètres de compilation
    compile_page_de_garde_eleve = "1"
    est_un_document_a_trous = "0"
    if has_corriges:
        compile_page_de_garde_prof = "1"
    else:
        compile_page_de_garde_prof = "0"

    # Compilation
    fichier_tex_a_compiler = UPSTIFichierTexACompiler(fichier_page_de_garde)

    if fichier_tex_a_compiler.compile_tex(
        {
            "verbose": False,
            "parametres_compilation": {
                "compiler_fichier_eleve": compile_page_de_garde_eleve,
                "compiler_fichier_prof": compile_page_de_garde_prof,
                "est_un_document_a_trous": est_un_document_a_trous,
                "compiler_versions_accessibles": data["accessibilite"],
            },
        }
    ):
        self.affiche_message(
            {
                "texte": "La page de garde a été compilée correctement",
                "type": "resultat",
                "verbose": options["verbose"],
            }
        )

        # On peut maintenant créer le pdf final
        self.affiche_message(
            {
                "texte": "Création du pdf final",
                "type": "titre2",
                "verbose": options["verbose"],
            }
        )

        # On se fait la liste des fichiers
        self.affiche_message(
            {
                "texte": "Regroupement de tous les fichiers pdf et ajout des pages blanches.",
                "type": "action",
                "verbose": options["verbose"],
            }
        )

        fichiers_eleves = [fichier_page_de_garde.with_suffix(".pdf")]
        fichiers_prof = [
            fichier_page_de_garde.parent
            / str(
                fichier_page_de_garde.stem
                + self.config["Compilation"]["suffixe_nom_fichier_prof"]
                + ".pdf"
            )
        ]
        for chapitre in data["fichiers"]:
            for td in chapitre["tds"]:
                if "fichier_eleves" in td:
                    fichiers_eleves.append(td["fichier_eleves"])
                if "fichier_prof" in td:
                    fichiers_prof.append(td["fichier_prof"])

        # Création du poly version élève
        nom_fichier_poly_td = chemin_fichier_xml.parent / str(
            data["nom"] + self.config["Poly_TD"]["suffixe_poly_td"] + ".pdf"
        )
        self.combine_pdf(fichiers_eleves, nom_fichier_poly_td)

        # Création des polys en version accessible
        for version in data["accessibilite"].split(","):
            nom_fichier_poly_td_accessible = chemin_fichier_xml.parent / str(
                data["nom"]
                + self.config["Poly_TD"]["suffixe_poly_td"]
                + "-"
                + version
                + ".pdf"
            )
            fichiers_accessible = [
                fichier_page_de_garde.parent
                / str(fichier_page_de_garde.stem + "-" + version + ".pdf")
            ]
            for fichier_eleve in fichiers_eleves[1:]:
                nom_fichier_accessible = fichier_eleve.parent / str(
                    fichier_eleve.stem + "-" + version + ".pdf"
                )
                fichiers_accessible.append(nom_fichier_accessible)
                self.combine_pdf(
                    fichiers_accessible,
                    nom_fichier_poly_td_accessible,
                    {"pages_par_feuille": 2},
                )

        # Création du poly version profs
        if has_corriges:
            nom_fichier_poly_td_prof = chemin_fichier_xml.parent / str(
                data["nom"]
                + self.config["Poly_TD"]["suffixe_poly_td"]
                + self.config["Compilation"]["suffixe_nom_fichier_prof"]
                + ".pdf"
            )
            self.combine_pdf(fichiers_prof, nom_fichier_poly_td_prof)

        self.affiche_message(
            {
                "texte": "Les fichiers pdf des polys ont été créés correctement.",
                "type": "resultat",
                "verbose": options["verbose"],
            }
        )
        self.affiche_message(
            {
                "texte": "L'opération s'est à priori terminée avec succès.",
                "type": "titre1",
            }
        )
    else:
        self.affiche_message(
            {
                "texte": "Problème de compilation....",
                "type": "error",
                "verbose": options["verbose"],
            }
        )
    '''
    return True, []


# def get_nombre_pages_pdf(self, fichier, nb_pages_par_feuille=2, recto_verso=True):
#     """Retourne le nombre de pages d'un fichier pdf, arrondi en fonction du nombre de pages par feuille

#     Paramètres :
#     ------------
#         path fichier : chemin du fichier à traiter
#         int nb_pages_par_feuille : nombre de pages à imprimer par feuille
#         bool recto_verso : True si on va imprimer en recto/verso

#     Retourne : le nombre de pages
#     ----------
#     """
#     if recto_verso:
#         nb_pages_par_feuille = nb_pages_par_feuille * 2

#     pdf_reader = PdfReader(fichier)
#     nombre_de_pages = len(pdf_reader.pages)
#     nombre_de_pages_total = (
#         (nombre_de_pages - 1) // nb_pages_par_feuille + 1
#     ) * nb_pages_par_feuille
#     return nombre_de_pages_total


# def combine_pdf(self, fichiers, fichier_pdf, options={}):
#     """Création d'un fichier pdf à partir de plusieurs fichiers

#     Paramètres :
#     ------------
#         list fichiers : liste des fichiers à combiner (sous forme d'objets Path)
#         str fichier_pdf : chemin du fichier pdf à créer
#         dict options :
#             "pages_par_feuille": nombre de page par feuille pour le pdf (default: 2)

#     Retourne : True / False si ça s'est bien passé ou non
#     ----------
#     """

#     # Valeurs par défaut
#     if "pages_par_feuille" not in options:
#         options["pages_par_feuille"] = 4  # 2 pages par feuille en R/V

#     # Objet correspondant au nouveau fichier pdf à créer
#     pdf_writer = PdfWriter()

#     # On parcourt tous les fichiers et on ajoute le nombre de pages blanches nécessaires, avant de les ajouter au fichier pdf global
#     for fichier in fichiers:
#         pdf_reader = PdfReader(fichier)
#         nombre_de_pages = len(pdf_reader.pages)
#         for numero_page in range(nombre_de_pages):
#             pdf_writer.add_page(pdf_reader.pages[numero_page])

#         # Ajout des pages blanches
#         nombre_de_pages_blanches = (
#             options["pages_par_feuille"]
#             - nombre_de_pages % options["pages_par_feuille"]
#         )
#         if (
#             nombre_de_pages_blanches != 0
#             and nombre_de_pages_blanches != options["pages_par_feuille"]
#         ):
#             for i in range(nombre_de_pages_blanches):
#                 pdf_writer.add_blank_page()

#     # On crée le nouveau fichier
#     with open(fichier_pdf, "wb") as fic:
#         pdf_writer.write(fic)

#     return True


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
