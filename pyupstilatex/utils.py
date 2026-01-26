import json
from pathlib import Path
from typing import Any, List, Optional, Union


# TODEL ???
def check_path_readable(path: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Vérifie qu'un chemin existe, est un fichier et est lisible (texte).

    Retourne (ok, raison, flag) où:
    - ok: True si accessible, False sinon
    - raison: None si ok, sinon un message court expliquant l'erreur/avertissement
    - flag: None, 'warning' (fallback d'encodage), ou 'fatal_error'
    """
    p = Path(path)
    if not p.exists():
        return False, "Fichier introuvable", "fatal_error"
    if not p.is_file():
        return False, "N'est pas un fichier", "fatal_error"
    try:
        # Lecture d'un octet pour forcer le décodage (et déclencher UnicodeDecodeError
        # si l'encodage est incorrect). Lire 0 octet n'effectue pas de décodage.
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


# TODEL ???
def check_path_writable(path: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Vérifie qu'un chemin de fichier existant est ouvrable en écriture.

    - Retourne (True, None, None) si le fichier existe et peut être ouvert en écriture.
    - Sinon (False, erreur). N'essaie PAS de créer le fichier s'il n'existe pas.
    """
    p = Path(path)
    if not p.exists():
        return False, "Fichier introuvable", "fatal_error"
    if not p.is_file():
        return False, "N'est pas un fichier", "fatal_error"
    try:
        # 'r+b' requiert que le fichier existe et autorise l'écriture sans le tronquer
        with p.open("r+b") as _:
            pass
    except PermissionError as e:
        return False, f"Permission refusée: {e}", "fatal_error"
    except Exception as e:
        return False, f"Impossible d'ouvrir en écriture: {e}", "fatal_error"
    return True, None, None


# TODEL ???
def check_types(obj: Any, expected_types: Union[str, List[str]]) -> bool:
    """
    Vérifie si `obj` est du type indiqué par `expected_types` (str ou liste de str).
    Exemple:
      check_types("abc", "str")         -> True
      check_types(123, "text")          -> True
      check_types(3.14, ["str", "text"]) -> True
    """
    type_map = {
        "str": str,
        "int": int,
        "float": float,
        "dict": dict,
        "list": list,
        "tuple": tuple,
        "bool": bool,
        "set": set,
        "text": (str, int, float),
    }

    if isinstance(expected_types, str):
        expected_types = [expected_types]

    for type_name in expected_types:
        cls = type_map.get(type_name)
        if cls and isinstance(obj, cls):
            return True

    return False


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
    """Création d'un poly de TD à partir d'un fichier xml

    Paramètres :
    ------------
        Path chemin_fichier_xml : chemin du fichier xml à traiter
        dict options
            bool verbose (optionnel) : si on affiche ou non les messages d'information en temps réel (default : True)

    Retourne : True
    ----------
    """

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
    """Création du fichier yaml nécessaire à la génération du poly de TD"""

    msg.info("Fonction create_yaml_for_poly non encore implémentée.", "info")

    '''"""
    # Dossiers
    DOSSIER_COURS = "Cours/LaTeX"
    DOSSIER_TD = "TD"

    self.affiche_message(
        {
            "texte": "Création du fichier xml de définition du poly de TD",
            "type": "titre1",
            "verbose": options["verbose"],
        }
    )

    # Nom du fichier xml à traiter
    chemin_fichier_xml = (
        chemin_dossier
        / self.config["Poly_TD"]["dossier_pour_poly_td"]
        / self.config["Poly_TD"]["nom_fichier_xml_poly"]
    )

    # On récupère et on filtre la liste des fichiers à traiter
    self.affiche_message(
        {
            "texte": "Récupération de la liste des fichiers",
            "type": "titre2",
            "verbose": options["verbose"],
        }
    )
    fichiers_a_traiter = self.get_liste_fichiers_a_traiter(
        {
            "custom": {"liste_dossiers": [chemin_dossier]},
            "verbose": options["verbose"],
        }
    )

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
        data = {}
        data["nom_chapitre"] = "[Impossible de trouver le nom du chapitre]"
        data["logo"] = "[Impossible de trouver le fichier logo]"
        data["id_classe"] = "2"
        data["id_variante"] = "2"
        data["competences"] = []
        data["fichiers"] = {}
        data["accessibilite"] = ""

        # On remonte à la racine des TD pour déterminer le chemin du cours
        chemin_du_cours = chemin_dossier
        nb_parents = 0
        while chemin_du_cours.name != DOSSIER_TD:
            chemin_du_cours = chemin_du_cours.parents[0]
            nb_parents += 1
        chemin_du_cours = chemin_du_cours.parents[0] / DOSSIER_COURS

        # On cherche le fichier tex du cours
        fichiers_cours = self.get_liste_fichiers_a_traiter(
            {"custom": {"liste_dossiers": [chemin_du_cours]}, "verbose": False}
        )

        # S'il y en a plusieurs, on prend le premier par défaut, et on crée une instance UPSTIFichierTex
        if len(fichiers_cours["liste"]) > 0:
            fichier_tex_cours = UPSTIFichierTex(fichiers_cours["liste"][0], self)
            fichier_tex_cours.get_infos()

            data["nom_chapitre"] = fichier_tex_cours.infos["titre_en_tete"]
            data["id_classe"] = fichier_tex_cours.infos["id_classe"]
            data["id_variante"] = fichier_tex_cours.infos["id_variante"]

            # On cherche le logo
            chemin_logo = fichier_tex_cours.get_valeur_commande("UPSTIlogoPageDeGarde")
            data["logo"] = (
                "../" + nb_parents * "../" + DOSSIER_COURS + "/" + chemin_logo
            )

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
