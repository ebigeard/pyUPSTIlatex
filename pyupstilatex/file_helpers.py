import fnmatch
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .accessibilite import VERSIONS_ACCESSIBLES_DISPONIBLES
from .config import load_config


def scan_for_documents(
    root_paths: Optional[Union[str, List[str]]] = None,
    exclude_patterns: Optional[List[str]] = None,
    filter_mode: str = "compatible",
    compilable_filter: str = "all",
) -> Tuple[Optional[List[Dict[str, str]]], List[List[str]]]:
    """Scanne un ou plusieurs dossiers à la recherche de fichiers LaTeX.

    Analyse tous les fichiers .tex et .ltx trouvés et les classe selon leur
    compatibilité avec pyUPSTIlatex (UPSTI_Document_v1 ou UPSTI_Document_v2).
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
                "UPSTI_Document_v1",
                "UPSTI_Document_v2",
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


def format_documents_for_display(
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


def create_poly_td(chemin_fichier_yaml: Path, msg) -> tuple[bool, List[List[str]]]:
    """Création d'un poly de TD à partir d'un fichier xml"""

    msg.info("Fonction create_poly_td non encore implémentée.", "info")

    '''
    # Nettoyage des options
    if not "verbose" in options:
        options["verbose"] = True

    self.affiche_message(
        {
            "texte": "Création du poly de TD à partir du fichier xml",
            "type": "titre1",
            "verbose": options["verbose"],
        }
    )

    # Récupérer les données du fichier xml
    self.affiche_message(
        {
            "texte": "Extraction des données depuis le fichier xml.",
            "type": "action",
            "verbose": options["verbose"],
        }
    )

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


def create_yaml_for_poly(chemin_dossier: Path, msg) -> tuple[bool, List[List[str]]]:
    """Création du fichier YAML nécessaire à la génération d'un poly de TD"""

    cfg = load_config()

    # Initialisation des données avec valeurs par défaut
    data_poly = dict(
        nom_chapitre="[Impossible de trouver le nom du chapitre]",
        logo="[Impossible de trouver le fichier logo]",
        classe="PT",
        variante="jean-zay",
        competences=[],
        fichiers=[],
        accessibilite=[],
    )

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

    # 2. Il faut lister les TD parmi les fichiers trouvés
    #    On en profite pour récupérer les compétences couvertes
    msg.info("Filtrage des TD et récupération des infos nécessaires", "info")
    messages_filtrage_td: List[List[str]] = []

    liste_td: List[Dict] = []
    for fichier in liste_fichiers:
        from .document import UPSTILatexDocument

        doc, doc_errors = UPSTILatexDocument.from_path(fichier["path"])
        messages_filtrage_td.extend(doc_errors)

        # On vérifie si c'est un TD et on récupère les infos utiles
        if doc.get_metadata_value("type_document") == "td":
            fichier["variante"] = doc.get_metadata_value("variante")
            fichier["filiere"] = doc.get_metadata_value("filiere")
            fichier["programme"] = doc.get_metadata_value("programme")
            fichier["competences"] = doc.get_competences()
            liste_td.append(fichier)

    # 3. Récupération du titre et de l'image de titre à partir du cours associé
    msg.info("Récupération des informations du cours associé", "info")
    messages_recuperation_cours: List[List[str]] = []

    #
    # CONTINUE : si variante, filiere et programme sont cohérents entre les TD,
    # on les met dans le YAML
    #

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
                    f"Aucun fichier de cours trouvé dans le dossier {chemin_du_cours}",
                    "warning",
                ]
            )
    else:
        fichier_cours = liste_fichiers_cours[0]

    messages_recuperation_cours.append(["CONTINUE - On en est là", "info"])

    msg.affiche_messages(messages_recuperation_cours, "resultat_item")
    '''
    # S'il y en a plusieurs, on prend le premier par défaut, et on crée une instance UPSTIFichierTex
    if len(fichiers_cours["liste"]) > 0:
        fichier_tex_cours = UPSTIFichierTex(fichiers_cours["liste"][0], self)
        fichier_tex_cours.get_infos()

        data["nom_chapitre"] = fichier_tex_cours.infos["titre_en_tete"]
        data["id_classe"] = fichier_tex_cours.infos["id_classe"]
        data["id_variante"] = fichier_tex_cours.infos["id_variante"]

        # On cherche le logo
        chemin_logo = fichier_tex_cours.get_valeur_commande("UPSTIlogoPageDeGarde")
        data["logo"] = "../" + nb_parents * "../" + DOSSIER_COURS + "/" + chemin_logo

    # 4. Création d'une sauvegarde du fichier yaml s'il existe déjà
    msg.info("Création d'une sauvegarde du fichier yaml s'il existe déjà", "info")

    # 5. Génération du fichier yaml
    msg.info("Génération du fichier YAML", "info")

    '''

    '''"""
    # Dossiers
    DOSSIER_COURS = "Cours/LaTeX"
    DOSSIER_TD = "TD"


    # Traitement des fichiers
    if fichiers_a_traiter["is_OK"] and fichiers_a_traiter["nombre"]:
        from upsti_latex import UPSTIFichierTex

        self.affiche_message(
            {
                "texte": "Génération du fichier xml",
                "type": "titre2",
                "verbose": options["verbose"],
            }
        )

        # Récupération du nom du chapitre : on va tenter de regarder s'il existe un cours dans le même chapitre...


        # On remonte à la racine des TD pour déterminer le chemin du cours

        # Génération du numéro de version - Pour l'instant, on va mettre une version 1.0 par défaut. On verra à l'usage
        data["version"] = "1.0"

        # On classe par ordre alphabetique avec les accents
        # TODO
        locale.setlocale(
            locale.LC_COLLATE, 'fr_FR.UTF-8'
        )  # Utilisation de la localisation française
        liste_UPSTI_fichier_tex_triee = sorted(
            liste_UPSTI_fichier_tex,
            key=lambda fic: locale.strxfrm(fic.infos["titre"]),
        )

        # Génération de la liste des fichiers (organisé en section), et recensement des compétences
        for fichier in fichiers_a_traiter["liste"]:
            # self.affiche_message({"texte" : fichier.name, "type" : "resultat_item"})

            # On va lister les fichiers, et les classer par dossier
            if fichier.parents[2].name == "TD":
                nom_dossier = "default"
            else:
                nom_dossier = fichier.parents[2].name

            key_dossier = hashlib.md5(nom_dossier.encode()).hexdigest()

            if key_dossier not in data["fichiers"]:
                data["fichiers"][key_dossier] = {
                    "dossier": nom_dossier,
                    "liste": [fichier.as_posix()],
                }
            else:
                data["fichiers"][key_dossier]["liste"].append(fichier.as_posix())

            # Competences
            fichier_tex = UPSTIFichierTex(fichier, self)
            fichier_tex.get_infos()
            data["competences"] += fichier_tex.infos["competences"]

        # On élimine les doublons et on classe les compétences dans l'ordre
        data["competences"] = sorted(list(set(data["competences"])))

    # Maintenant qu'on a toutes les infos, on s'occupe du fichier xml
    xml_content = self.set_xml_content(data)

    # Si le fichier existe, on crée une copie
    if chemin_fichier_xml.exists():
        self.affiche_message(
            {
                "texte": f"Un fichier {self.config['Poly_TD']['nom_fichier_xml_poly']} existe déjà. Création d'une copie de sauvegarde.",
                "type": "action",
                "verbose": options["verbose"],
            }
        )
        chemin_fichier_bak = (
            chemin_fichier_xml.parent / "bak" / (chemin_fichier_xml.name + '.bak')
        )
        chemin_fichier_bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(chemin_fichier_xml, chemin_fichier_bak)
        self.affiche_message(
            {
                "texte": "Copie de sauvegarde créée avec succès.",
                "type": "resultat",
                "verbose": options["verbose"],
            }
        )

    # On crée le fichier (si le dossier n'existe pas, on crée le dossier)
    self.affiche_message(
        {
            "texte": "Création du fichier xml sur le disque.",
            "type": "action",
            "verbose": options["verbose"],
        }
    )
    chemin_fichier_xml.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin_fichier_xml, "w", encoding="utf-8") as fic:
        fic.write(xml_content)
        self.affiche_message(
            {
                "texte": f"Fichier {chemin_fichier_xml} créé.",
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
    '''
    return True, []


# def set_xml_content(self, data, options={}):
#     """Création du contenu du fichier xml

#     Paramètres :
#     ------------
#         dict data : données à convertir en fichier xml

#     Retourne :
#     ----------
#         str contenu_xml : contenu à écrire dans le fichier xml
#     """
#     # Nettoyage des options
#     if not "verbose" in options:
#         options["verbose"] = True

#     self.affiche_message(
#         {
#             "texte": "Création du contenu du fichier xml à partir de la structure des dossiers.",
#             "type": "action",
#             "verbose": options["verbose"],
#         }
#     )
#     doc, tag, text = Doc().tagtext()

#     doc.asis('<?xml version="1.0" encoding="utf-8"?>\n')
#     doc.asis('<!--\n')
#     doc.asis(
#         '=============================================================================\n'
#     )
#     doc.asis(" Configuration pour la génération d'un poly de TD\n")
#     doc.asis(
#         '=============================================================================\n'
#     )
#     doc.asis('  - Vous pouvez modifier ce fichier comme vous le souhaitez\n')
#     doc.asis(
#         "  - L'ordre des documents et des sections dans le poly sera l'ordre défini dans ce fichier\n"
#     )
#     doc.asis("  - Les chemins relatifs sont définis par rapport à ce fichier xml\n")
#     doc.asis(
#         '=============================================================================\n'
#     )
#     doc.asis('-->')
#     with tag('poly'):
#         with tag('nom'):
#             text(data["nom_chapitre"])
#         with tag('version'):
#             text(data["version"])
#         with tag('imagepagedegarde'):
#             text(data["logo"])
#         with tag('id_variante'):
#             text(data["id_variante"])
#         with tag('id_classe'):
#             text(data["id_classe"])
#         with tag('accessibilite'):
#             text(data["accessibilite"])
#         with tag('sections'):
#             for id, section in data["fichiers"].items():
#                 with tag('section', ('nom', section["dossier"])):
#                     for fichier in section["liste"]:
#                         with tag('fichier'):
#                             text(fichier)
#         with tag('competences'):
#             for competence in data["competences"]:
#                 with tag('competence'):
#                     text(competence)

#     contenu_xml = indent(doc.getvalue(), indentation=' ' * 4, newline='\n')
#     self.affiche_message(
#         {
#             "texte": "Contenu du fichier xml créé.",
#             "type": "resultat",
#             "verbose": options["verbose"],
#         }
#     )

#     return contenu_xml


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
