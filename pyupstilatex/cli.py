import click

from .document import UPSTILatexDocument
from .logger import (
    COLOR_DARK_GRAY,
    COLOR_GREEN,
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
def version(ctx, path):
    """Affiche la version du document UPSTI/EPB."""

    msg: MessageHandler = ctx.obj["msg"]
    msg.titre1(f"VERSION : {path}")
    msg.action("Détection de la version du document...")

    # Instanciation du document
    doc = UPSTILatexDocument.from_path(path)

    # Vérification du fichier via UPSTILatexDocument.check_file (sans émission auto)
    ok, file_errors = doc.check_file("read")
    if not ok:
        # Afficher les erreurs au format 'resultat' comme auparavant
        for err in file_errors:
            msg.resultat(f"{err[0]}", flag=err[1])
        msg.separateur1()
        return ctx.exit(1)

    # Détection de version
    version, errors = doc.get_version()
    for error in errors:
        msg.resultat(f"{error[0]}", flag=error[1])
    if version is not None:
        msg.resultat(f"Version détectée : {version}")
    msg.separateur1()


@main.command()
@click.argument("path", type=click.Path())
@click.pass_context
def infos(ctx, path):
    """Affiche les informations du document UPSTI"""

    msg: MessageHandler = ctx.obj["msg"]
    msg.titre1(f"INFOS : {path}")

    # Instanciation du document
    doc = UPSTILatexDocument.from_path(path)

    # Vérification du fichier (lecture)
    fichier_valide, errors = doc.check_file("read")

    # Récupération des métadonnées selon la version
    if fichier_valide:
        metadata, meta_errors = doc.get_metadata()
        errors += meta_errors

    # On détecte si on a rencontré une erreur fatale
    for error in errors:
        if error[1] == "fatal_error":
            msg.info(f"{error[0]}", flag=error[1])
            msg.separateur1()
            return ctx.exit(1)

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

            # type_meta peut être de la forme "default" ou "default:wrong_type"
            tm_raw = meta.get("type_meta") or ""
            tm_parts = tm_raw.split(":", 1)
            main_type = tm_parts[0] if tm_parts and tm_parts[0] else ""
            cause_type = tm_parts[1] if len(tm_parts) > 1 else ""
            items.append((label, valeur, main_type, cause_type, initial_value))

        max_label_len = max((len(lbl) for lbl, _, _, _, _ in items), default=0)

        # Afficher les lignes avec alignement des ':'
        # Vérifier l'affichage en fonction des nouveaux mots clés
        for label, valeur, type_meta, cause_meta, initial_value in items:
            # colorer le label selon s'il s'agit d'une valeur par défaut
            if type_meta == "default":
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

            # padding: ajouter des espaces après le label pour aligner ':'
            pad = max_label_len - len(label)
            padding = " " * pad
            msg.info(f"{padding}{label} {separateur_colored} {valeur}")

    # Erreurs rencontrées
    if errors:
        msg.separateur2()
        for error in errors:
            msg.info(f"{error[0]}", flag=error[1])

    # Légende des symboles
    msg.separateur1()
    msg.info(
        f"{COLOR_GREEN}=>{COLOR_RESET} valeur définie dans le fichier tex, "
        f"{COLOR_LIGHT_GREEN}=>{COLOR_RESET} valeur déduite, "
        f"{COLOR_DARK_GRAY}=>{COLOR_RESET} valeur par défaut"
    )
    msg.info(
        f"{COLOR_ORANGE}=>{COLOR_RESET} problème, " f"{COLOR_RED}=>{COLOR_RESET} erreur"
    )
    msg.separateur1()


# ================================================================================
# TOCHECK Tout ce qui suit est généré par IA, à vérifier et comprendre
# ================================================================================


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.argument("zone", type=str)
@click.option("--stdout/--no-stdout", default=True)
@click.option("--output", "-o", type=click.Path(), default=None)
def extract_zone(path, zone, stdout, output):
    """Extract a named zone. Writes to stdout or file."""
    doc = UPSTILatexDocument.from_path(path)
    content = doc.get_zone(zone)
    if content is None:
        raise click.ClickException(f"Zone '{zone}' not found in {path}")
    if stdout:
        click.echo(content)
    elif output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Wrote {output}")


if __name__ == "__main__":
    main()
