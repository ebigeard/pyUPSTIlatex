from pathlib import Path

import click

from .config import load_config
from .document import UPSTILatexDocument
from .file_helpers import format_documents_for_display, scan_for_documents
from .logger import (
    COLOR_DARK_GRAY,
    COLOR_GREEN,
    COLOR_LIGHT_BLUE,
    COLOR_LIGHT_GREEN,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_RESET,
    MessageHandler,
)


@click.group()
@click.option(
    "--log-file", "-L", type=click.Path(), default=None, help="Chemin du fichier de log"
)
@click.option(
    "--no-verbose",
    is_flag=True,
    default=False,
    help="Désactive les messages d'information",
)
@click.pass_context
def main(ctx, log_file, no_verbose):
    """pyUPSTIlatex CLI"""
    handler = MessageHandler(log_file=log_file, verbose=not no_verbose)
    ctx.obj = {"msg": handler}


@main.command()
@click.argument("path", type=click.Path())
@click.pass_context
def version(ctx, path: str):
    """Affiche la version du document UPSTI/EPB."""
    msg: MessageHandler = ctx.obj["msg"]
    chemin = Path(path)

    msg.titre1(f"VERSION : {chemin.name}")

    # Vérification centralisée du chemin / document
    doc = _check_path(ctx, chemin)

    # Détection de version
    version, messages = doc.get_version()
    if version:
        messages.append(f"Version détectée : {COLOR_GREEN}{version}{COLOR_RESET}")

    return _exit_with_messages(ctx, msg, messages)


@main.command()
@click.argument("path", type=click.Path())
@click.pass_context
def infos(ctx, path):
    """Affiche les informations du document UPSTI"""

    msg: MessageHandler = ctx.obj["msg"]
    chemin = Path(path)

    msg.titre1(f"INFOS : {chemin.name}")

    # Vérification centralisée du chemin / document
    doc = _check_path(ctx, chemin)

    # Récupération des métadonnées selon la version
    metadata, messages = doc.get_metadata()

    # On détecte si on a rencontré une erreur fatale
    if metadata is None:
        return _exit_with_messages(ctx, msg, messages)

    if metadata:
        # Préparer la liste des éléments affichables et calculer la largeur max
        items = []
        for meta in metadata.values():
            label = meta.get("label")
            valeur = (
                meta.get("valeur")
                if meta.get("valeur") is not None
                else meta.get("raw_value", "")
            )
            initial_value = meta.get("initial_value", "")
            display_flag = meta.get("display_flag", "")

            # type_meta peut être de la forme "default" ou "default:wrong_type"
            tm_raw = meta.get("type_meta") or ""
            tm_parts = tm_raw.split(":", 1)
            main_type = tm_parts[0] if tm_parts and tm_parts[0] else ""
            cause_type = tm_parts[1] if len(tm_parts) > 1 else ""
            items.append(
                (label, valeur, main_type, cause_type, initial_value, display_flag)
            )

        max_label_len = max((len(lbl) for lbl, _, _, _, _, _ in items), default=0)

        # Afficher les lignes avec alignement des ':'
        # Vérifier l'affichage en fonction des nouveaux mots clés
        for label, valeur, type_meta, cause_meta, initial_value, display_flag in items:
            # colorer le label selon s'il s'agit d'une valeur par défaut
            if display_flag == "info":
                separateur_colored = f"{COLOR_LIGHT_BLUE}=>{COLOR_RESET}"
            elif type_meta == "default":
                separateur_colored = f"{COLOR_DARK_GRAY}=>{COLOR_RESET}"
                if cause_meta:
                    separateur_colored = f"{COLOR_ORANGE}=>{COLOR_RESET}"
                    valeur = (
                        f"{COLOR_ORANGE}{valeur} (avant correction: "
                        f"'{initial_value}'){COLOR_RESET}"
                    )
            elif type_meta == "deducted":
                separateur_colored = f"{COLOR_LIGHT_GREEN}=>{COLOR_RESET}"
            elif type_meta == "ignored":
                separateur_colored = f"{COLOR_RED}=>{COLOR_RESET}"
                valeur = f"{COLOR_RED}ignoré: '{initial_value}'{COLOR_RESET}"
            else:
                separateur_colored = f"{COLOR_GREEN}=>{COLOR_RESET}"

            # Gérer les sauts de ligne dans valeur pour l'alignement
            indent_width = max_label_len + 6  # label + " => " + 2 (mystère)
            valeur_aligned = str(valeur).replace("\n", "\n" + " " * indent_width)

            # padding: ajouter des espaces après le label pour aligner ':'
            pad = max_label_len - len(label)
            padding = " " * pad
            msg.info(f"{padding}{label} {separateur_colored} {valeur_aligned}")

    # Erreurs rencontrées
    if messages:
        msg.separateur2()
        msg.affiche_messages(messages, "info")

    # Légende des symboles
    msg.separateur1()
    msg.info(
        f"{COLOR_GREEN}=>{COLOR_RESET} valeur définie dans le fichier tex, "
        f"{COLOR_LIGHT_GREEN}=>{COLOR_RESET} valeur déduite, "
        f"{COLOR_DARK_GRAY}=>{COLOR_RESET} valeur par défaut"
    )
    msg.info(
        f"{COLOR_ORANGE}=>{COLOR_RESET} WARNING, "
        f"{COLOR_RED}=>{COLOR_RESET} ERROR, {COLOR_LIGHT_BLUE}=>{COLOR_RESET} INFO"
    )
    return _exit_with_separator(ctx, msg)


@main.command(name="liste-fichiers")
@click.argument(
    "path",
    nargs=-1,
    type=click.Path(file_okay=False, dir_okay=True),
)
@click.option(
    "--exclude",
    "exclude",
    multiple=True,
    help=(
        "Motifs d'exclusion (glob). Si absent, utilise "
        "OS_TRAITEMENT_PAR_LOT_FICHIERS_A_EXCLURE."
    ),
)
@click.option(
    "--show-full-path",
    is_flag=True,
    default=False,
    help="Affiche le chemin complet au lieu du chemin tronqué à 88 caractères.",
)
@click.option(
    "--filter-mode",
    default="compatible",
    help=(
        "Mode de filtrage des fichiers: 'compatible' (défaut), "
        "'incompatible' ou 'all'."
    ),
)
@click.option(
    "--compilability",
    default="all",
    help=(
        "Mode de filtrage des fichiers suivant leur compilabilité: 'all' (défaut), "
        "'compilable' ou 'non-compilable'."
    ),
)
@click.pass_context
def liste_fichiers(ctx, path, exclude, show_full_path, filter_mode, compilability):
    """Affiche la liste des fichiers UPSTI_document dans un ou plusieurs dossiers."""

    msg: MessageHandler = ctx.obj["msg"]
    cfg = load_config()

    # Déterminer les racines à scanner
    # Si path fourni, on l'utilise, sinon scan_for_documents utilisera la config
    roots_to_scan = list(path) if path and len(path) > 0 else None

    # Déterminer les motifs d'exclusion (priorité: --exclude > env)
    exclude_patterns = list(exclude) if exclude else None  # None = utiliser .env

    # Titre
    if roots_to_scan:
        nb_dossiers = len(roots_to_scan)
        if nb_dossiers == 1:
            msg.titre1(
                f"LISTE des fichiers UPSTI_document contenus dans : {roots_to_scan[0]}"
            )
        else:
            msg.titre1(
                "LISTE des fichiers UPSTI_document contenus dans :\n  - "
                + "\n  - ".join(roots_to_scan)
            )
    else:
        # Utilisation de la configuration
        dossiers_config = cfg.traitement_par_lot.dossiers_a_traiter
        if dossiers_config and len(dossiers_config) > 0:
            if len(dossiers_config) == 1:
                msg.titre1(
                    f"LISTE des fichiers UPSTI_document contenus dans : "
                    f"{dossiers_config[0]} (depuis la configuration)"
                )
            else:
                msg.titre1(
                    "LISTE des fichiers UPSTI_document contenus dans (depuis la "
                    "configuration) :\n  - " + "\n  - ".join(dossiers_config)
                )
        else:
            msg.titre1("LISTE des fichiers UPSTI_document")

    # Scanner les documents
    documents, messages = scan_for_documents(
        roots_to_scan,
        exclude_patterns,
        filter_mode=filter_mode,
        compilable_filter=compilability,
    )

    # Gérer les erreurs fatales
    if documents is None:
        msg.affiche_messages(messages, "info")
        return _exit_with_separator(ctx, msg)

    # Afficher les documents trouvés
    if not documents:
        msg.info("Aucun document trouvé.", flag="warning")
    else:
        # Préparer les chemins d'affichage (tronqués) puis calculer les largeurs
        # format_documents_for_display ajoute la clé 'display_path' en place.
        format_documents_for_display(documents)
        display_key = "path" if show_full_path else "display_path"
        max_path = max(len(d[display_key]) for d in documents)
        max_version = max(len(d["version"]) for d in documents)

        # Afficher chaque document
        for doc in sorted(documents, key=lambda x: x["path"]):
            path_padded = doc[display_key].ljust(max_path)
            version_text = doc["version"].ljust(max_version)

            # Colorer la version selon le paramètre compiler
            version_colored = f"{COLOR_DARK_GRAY}│{COLOR_RESET} "
            if doc.get("a_compiler", False):
                version_colored += f"{version_text}"
            else:
                version_colored += f"{COLOR_DARK_GRAY}{version_text}{COLOR_RESET}"

            msg.info(f"{path_padded} {version_colored}")

        # Total
        nb_documents = len(documents)
        msg.separateur2()
        msg.info(
            f"Total de {COLOR_GREEN}{nb_documents}{COLOR_RESET} "
            "document(s) trouvé(s)."
        )

    # Erreurs/avertissements rencontrés
    if messages:
        msg.separateur2()
        msg.affiche_messages(messages, "info")

    return _exit_with_separator(ctx, msg)


@main.command(name="compile")
@click.argument("path", type=click.Path())
@click.option(
    "--mode",
    "-m",
    default="normal",
    help=(
        "Mode de compilation: 'normal' (défaut), 'quick' ou 'deep'. Toute autre valeur "
        "sera traitée comme 'normal'."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Mode test: affiche les actions sans les exécuter.",
)
@click.pass_context
def compile(ctx, path, mode, dry_run):
    """Compile un fichier .tex ou tous les fichiers d'un dossier."""

    from pathlib import Path

    chemin = Path(path)
    msg: MessageHandler = ctx.obj["msg"]
    compilation_unique = False

    # Normaliser le paramètre 'mode'
    try:
        mode = str(mode).lower()
    except Exception:
        mode = "normal"
    if mode not in ("deep", "quick"):
        mode = "normal"

    # On récupère la config pour gérer le niveau de verbosité
    cfg = load_config()
    affiche_details = cfg.compilation.affichage_detaille_dans_console

    # Titre
    msg.titre1(f"COMPILATION de {chemin}")

    # Gérer le cas où le chemin fourni est invalide nous-mêmes
    if not chemin.exists():
        msg.info(f"Fichier ou dossier introuvable : {chemin}", flag="error")
        return _exit_with_separator(ctx, msg)

    # Cas où on a un dossier
    if chemin.is_dir():
        # Liste des fichiers contenus dans le dossier passé en paramètres
        msg.titre2("Recherche de tous les fichiers tex UPSTI_document à compiler")
        documents_a_compiler, messages = scan_for_documents(
            [str(chemin)],
            None,
            filter_mode="compatible",
            compilable_filter="compilable",
        )

        # Afficher les messages d'erreur/warning du scan
        if messages:
            msg.affiche_messages(messages, "info")
            msg.separateur2()

        # Gérer les erreurs fatales
        if documents_a_compiler is None:
            messages = [["Erreur fatale lors du scan.", "error"]]
            return _exit_with_messages(ctx, msg, messages, separator_before=True)

        nb_documents = len(documents_a_compiler)
        if nb_documents == 0:
            messages = [["Aucun document compatible trouvé.", "error"]]
            return _exit_with_messages(ctx, msg, messages, separator_before=True)

        # Affichage de la liste des documents trouvés (avec numérotation)
        max_name = max(len(d["filename"]) for d in documents_a_compiler)
        max_version = max(len(d["version"]) for d in documents_a_compiler)

        for idx, d in enumerate(
            sorted(documents_a_compiler, key=lambda x: x["filename"]), start=1
        ):
            msg.info(
                f"{d['filename']:{max_name}}  "
                f"{COLOR_DARK_GRAY}│{COLOR_RESET} {d['version']:>{max_version}}"
            )

        if nb_documents > 1:
            str_fichiers_a_traiter = (
                f"ces {COLOR_GREEN}{nb_documents} documents"
                f"{COLOR_RESET} (la procédure peut-être très longue)"
            )
            compile_verbose = "messages"
        else:
            str_fichiers_a_traiter = f"{COLOR_GREEN}ce fichier{COLOR_RESET}"
            compile_verbose = "normal"

        msg.titre2(
            f"Souhaitez-vous réellement compiler {str_fichiers_a_traiter} ? (O/N)"
        )

        doit_compiler = input()
        if doit_compiler not in ["O", "o"]:
            messages = [["Opération annulée par l'utilisateur.", "error"]]
            return _exit_with_messages(ctx, msg, messages, separator_before=True)
        else:
            if nb_documents == 1:
                msg.titre2(f"Compilation de : {documents_a_compiler[0]['filename']}")
                compilation_unique = True
                doc = UPSTILatexDocument.from_path(
                    documents_a_compiler[0]["path"], msg=msg
                )[0]

            else:
                msg.titre2("Démarrage de la compilation...")
                statut_compilation_fichiers = {
                    "success": [],
                    "warning": [],
                    "error": [],
                }

                # Calculer la largeur de numérotation (1 pour 1-9, 2 pour 10-99, ...)
                num_width = len(str(nb_documents))

                # Compiler chaque document (numérotation cohérente)
                for idx, doc in enumerate(documents_a_compiler, start=1):

                    if nb_documents > 1:
                        number_label = f"{idx:0{num_width}d}"
                        msg.info(
                            f"{COLOR_DARK_GRAY}{number_label}/{nb_documents} - "
                            f"{COLOR_RESET}{doc['filename']}"
                        )

                    # Lancer la compilation
                    document = UPSTILatexDocument.from_path(doc["path"], msg=msg)[0]
                    result, messages = document.compile(
                        mode=mode, verbose=compile_verbose, dry_run=dry_run
                    )
                    # Protéger contre un statut inattendu
                    if result in statut_compilation_fichiers:
                        statut_compilation_fichiers[result].append(doc['filename'])
                    else:
                        # Statut inattendu : traiter comme erreur
                        statut_compilation_fichiers['error'].append(doc['filename'])

                    if nb_documents > 1:
                        if affiche_details and result == "success":
                            messages.append(["OK !", "success"])

                        msg.affiche_messages(messages, "resultat_item")

                # Message de conclusion
                msg.separateur1()
                if (
                    len(statut_compilation_fichiers['warning']) == 0
                    and len(statut_compilation_fichiers['error']) == 0
                ):
                    msg.info("Compilation terminée")
                else:
                    msg.info("Compilation terminée :")
                    nb_warnings = len(statut_compilation_fichiers['warning'])
                    if nb_warnings > 0:
                        pluriel = "s" if nb_warnings > 1 else ""
                        msg.info(
                            f"  - {COLOR_ORANGE}{nb_warnings}{COLOR_RESET} fichier"
                            f"{pluriel} partiellement compilé{pluriel} :"
                        )
                        for f in statut_compilation_fichiers['warning']:
                            msg.info(f"      - {f}")

                    nb_errors = len(statut_compilation_fichiers['error'])
                    if nb_errors > 0:
                        pluriel = "s" if nb_errors > 1 else ""
                        msg.info(
                            f"  - {COLOR_RED}{nb_errors}{COLOR_RESET} "
                            f"fichier{pluriel} en échec de compilation :"
                        )
                        for f in statut_compilation_fichiers['error']:
                            msg.info(f"      - {f}")

                return _exit_with_separator(ctx, msg)

    # Cas où on a un fichier unique
    elif chemin.is_file():
        # Vérification et instanciation centralisées
        doc = _check_path(ctx, chemin)
        compilation_unique = True

    if compilation_unique:
        result, messages = doc.compile(mode=mode, verbose="normal", dry_run=dry_run)

        # Message de conclusion
        msg.separateur1()
        # result est toujours "success", "warning" ou "error" (string)
        if result == "error":
            msg.info("Échec de la compilation", flag="error")
        elif result == "warning":
            msg.info("Compilation partiellement réussie", flag="warning")
        else:  # "success"
            msg.info("Compilation réussie", flag="success")
        return _exit_with_separator(ctx, msg)


@main.command(name="poly-td")
@click.argument("path", type=click.Path())
@click.pass_context
def poly_td(ctx, path):
    """Créé un poly de TD ou le fichier YAML pour le créer."""

    from pathlib import Path

    chemin = Path(path)
    msg: MessageHandler = ctx.obj["msg"]

    # On récupère la config
    cfg = load_config()
    nom_fichier_yaml = cfg.poly_td.nom_fichier_yaml

    # Cas où le chemin fourni est invalide
    if not chemin.exists():
        msg.titre1("CRÉATION DU POLY DE TD")
        msg.info(f"Fichier ou dossier introuvable : {chemin}", flag="error")
        return _exit_with_separator(ctx, msg)

    # Cas où on a un dossier
    if chemin.is_dir():
        msg.titre1(f"CRÉATION DU FICHIER YAML à partir de {chemin}")

        from .file_helpers import create_yaml_for_poly

        resultat, messages = create_yaml_for_poly(chemin, msg)

        if not resultat:
            messages.append(["Le fichier YAML n'a pu être créé", "fatal_error"])
            return _exit_with_messages(ctx, msg, messages, separator_before=True)

    # Cas où on a un fichier unique
    elif chemin.is_file():
        msg.titre1("CRÉATION DU POLY DE TD à partir du fichier YAML")
        if chemin.name != nom_fichier_yaml:
            msg.info(f"Fichier non pris en charge : {chemin.name}", flag="error")
            return _exit_with_separator(ctx, msg)
        else:
            from .file_helpers import create_poly_td

            resultat, messages = create_poly_td(chemin, msg)

    return _exit_with_separator(ctx, msg)


def _exit_with_separator(ctx, msg):
    msg.separateur1()
    ctx.exit(1)


def _exit_with_messages(ctx, msg, messages, separator_before=False):
    if separator_before:
        msg.separateur1()
    msg.affiche_messages(messages, "info")
    return _exit_with_separator(ctx, msg)


def _check_path(ctx, chemin: Path):
    """Vérifie le chemin, instancie le document et contrôle la lisibilité.

    En cas d'erreur, affiche les messages appropriés et sort via les helpers.
    Retourne l'objet `UPSTILatexDocument` si tout est OK.
    """
    msg: MessageHandler = ctx.obj["msg"]

    # Vérifications du chemin
    if not chemin.exists() or not chemin.is_file():
        erreur = (
            "Chemin incorrect"
            if not chemin.exists()
            else "Le chemin n'indique pas un fichier"
        )
        msg.info(f"{erreur} : {chemin}", flag="fatal_error")
        return _exit_with_separator(ctx, msg)

    # Instanciation du document
    doc, errors = UPSTILatexDocument.from_path(str(chemin), msg=msg)
    if not isinstance(doc, UPSTILatexDocument):
        errors.append(
            ["Impossible d'initialiser le document (objet invalide).", "fatal_error"]
        )
        return _exit_with_messages(ctx, msg, errors)

    # Vérification du fichier
    file_ok, file_errors = doc.file.check_file("read")
    if not file_ok:
        return _exit_with_messages(ctx, msg, file_errors)

    return doc


if __name__ == "__main__":
    main()
