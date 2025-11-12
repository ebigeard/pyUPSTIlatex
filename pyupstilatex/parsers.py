from typing import Any, Dict, List, Optional, Tuple

import regex as re
import yaml

from .utils import read_json_config


def parse_metadonnees_yaml(text: str) -> Tuple[Dict[str, Any], List[List[str]]]:
    """
    Extrait et parse le YAML contenu dans la zone
    %### BEGIN metadonnees_yaml ### ... %### END metadonnees_yaml ###
    Retourne (dict Python, liste d'erreurs).
    """
    errors: List[List[str]] = []

    block = extract_tex_zone(text, "metadonnees_yaml", remove_comment_char=True)
    if not block:
        return {}, errors

    # Prétraiter le bloc YAML : remplacer les tabulations et supprimer
    # les commentaires en fin de ligne (hors chaînes entre guillemets)
    def _strip_yaml_inline_comments(s: str) -> str:
        out_lines: List[str] = []
        for line in s.splitlines():
            buf: List[str] = []
            in_single = False
            in_double = False
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == "'" and not in_double:
                    in_single = not in_single
                    buf.append(ch)
                elif ch == '"' and not in_single:
                    in_double = not in_double
                    buf.append(ch)
                elif ch == "#" and not in_single and not in_double:
                    # début d'un commentaire en fin de ligne -> arrêter
                    break
                else:
                    buf.append(ch)
                i += 1
            out_lines.append(''.join(buf).rstrip())
        return "\n".join(out_lines)

    # Convertir tabulations en espaces (YAML interdit les tabs pour l'indentation)
    block = block.expandtabs(4)
    block_clean = _strip_yaml_inline_comments(block)

    try:
        data = yaml.safe_load(block_clean) or {}
        if not isinstance(data, dict):
            errors.append(
                [
                    "Le bloc YAML (front matter) n’est pas une structure de "
                    "type dictionnaire.",
                    "fatal_error",
                ]
            )
            data = {}
    except yaml.YAMLError as e:
        errors.append([f"Erreur de lecture des métadonnées YAML: {e}", "fatal_error"])
        data = {}

    return data, errors


def parse_metadonnees_tex(
    text: str, tex_names: Optional[List[str]] = None
) -> Tuple[Dict[str, Any], List[List[str]]]:
    """
    Extrait les commandes tex de configuration du fichier UPSTI_document.
    Retourne (dict Python, liste de messages d'erreurs (msg, flag)).
    """
    cfg = read_json_config()
    cfg_meta = cfg.get("metadonnee") or {}
    result: Dict[str, Any] = {}
    errors: List[List[str]] = []

    def _resolve_rel_value(section_key: str, raw: Any) -> Optional[str]:
        """
        Résout la valeur relationnelle en renvoyant la clé du mapping
        cfg[section_key].
        """
        mapping = cfg.get(section_key) or {}
        if not isinstance(mapping, dict):
            return str(raw)

        # Déjà une clé existante
        if str(raw) in mapping:
            return str(raw)

        # Essayer via id_upsti_document (numérique)
        try:
            raw_int = int(str(raw).strip())
        except Exception:
            raw_int = None

        for k, obj in mapping.items():
            if not isinstance(obj, dict):
                continue
            if raw_int is not None and obj.get("id_upsti_document") == raw_int:
                return k
            if str(obj.get("slug", "")) == str(raw):
                return k
            if str(obj.get("nom", "")) == str(raw):
                return k
            if str(obj.get("initiales", "")) == str(raw):
                return k

        return None

    # Parcours des métadonnées
    for key, m in cfg_meta.items():
        params = m.get("parametres", {})
        tex_key = params.get("tex_key")
        if not tex_key:
            continue

        tex_type = params.get("tex_type", "command_declaration")

        if tex_type == "command_declaration":
            parsed = find_tex_entity(text, tex_key, kind="command_declaration")
            if not parsed:
                continue

            valeur = parsed.get("value")

            if params.get("join_key"):
                custom_tex_keys = params.get("custom_tex_keys")
                if custom_tex_keys and valeur == "0":
                    valeur = {}
                    missing_custom_fields: List[str] = []
                    for custom_tex_key in custom_tex_keys:
                        parsed_custom = find_tex_entity(
                            text, custom_tex_key["tex_key"], kind="command_declaration"
                        )
                        tmp_valeur = (
                            parsed_custom.get("value") if parsed_custom else None
                        )
                        if tmp_valeur is None:
                            missing_custom_fields.append(custom_tex_key["tex_key"])
                        valeur[custom_tex_key["champ"]] = tmp_valeur

                    if missing_custom_fields:
                        msg = (
                            f"{tex_key} est égal à 0 (valeur custom), "
                            "mais il manque des valeurs pour : "
                            + ", ".join(missing_custom_fields)
                        )
                        errors.append([msg, "warning"])
                else:
                    valeur_associated = _resolve_rel_value(key, valeur)
                    if valeur_associated is not None:
                        valeur = valeur_associated
                    else:
                        msg = (
                            f"Valeur invalide pour {tex_key} ({parsed.get('value')}). "
                            "On va utiliser la valeur par défaut."
                        )
                        errors.append([msg, "warning"])
                        valeur = ""
            result[key] = valeur

        elif tex_type == "package_option_programme":
            parsed = find_tex_entity(text, tex_key, kind="package_options")
            if not parsed:
                continue

            if "ancienProgramme" in parsed:
                result["programme"] = "2013"

            cfg_programmes = cfg.get("programme") or {}
            for prog_key, prog in cfg_programmes.items():
                if prog.get("code_upsti_document") in parsed:
                    result["programme"] = prog_key
                    break

        elif tex_type == "batch_competences":
            competences: List[str] = []

            parsed = find_tex_entity(text, "UPSTIprogramme", kind="command_declaration")
            if not parsed or not parsed.get("value"):
                continue

            matches = re.findall(r"\\UPSTIcomp[PS]\{([^}]+)\}", parsed["value"])
            competences.extend(m.strip() for m in matches if m.strip())

            parsed = find_tex_entity(
                text, "UPSTIligneTableauCompetence", kind="command"
            )
            for cmd in parsed or []:
                args = cmd.get("args") or []
                if args:
                    code = args[0].get("value", "").strip()
                    if code:
                        competences.append(code)

            competences = sorted(set(competences))
            if competences:
                result[key] = {"FILIERE_TO_FIND": competences}

        elif tex_type == "batch_sources":
            sources: Dict[str, Any] = {}

            parsed = find_tex_entity(text, "UPSTIsource", kind="command_declaration")
            if parsed:
                sources["source"] = parsed.get("value", "")

            parsed = find_tex_entity(text, "nocite", kind="command")
            if parsed:
                sources["biblio"] = [
                    arg.get("value", "").strip()
                    for cmd in parsed
                    for arg in (cmd.get("args") or [])
                    if arg.get("value", "").strip()
                ]

            if sources:
                result[key] = sources

    # Cas particulier de la filière
    if "competences" in result:
        default_classe = "PT"
        default_filiere = "PTSI-PT"

        classe = result.get("classe", default_classe)
        filiere = None
        if isinstance(classe, dict):
            filiere = classe.get("filiere")
            if isinstance(filiere, str) and "[pyUl_ERREUR" in filiere:
                filiere = None
            classe = classe.get("nom", default_classe)

        classe_cfg = read_json_config().get("classe") or {}
        filiere = classe_cfg.get(classe, {}).get("filiere") or default_filiere

        comp = result["competences"]
        if "FILIERE_TO_FIND" in comp:
            comp[filiere] = comp.pop("FILIERE_TO_FIND")

    return result, errors


def extract_tex_zone(
    text: str, zone_name: str, remove_comment_char: bool = False
) -> Optional[str]:
    """
    Extrait le contenu brut d'une zone LaTeX délimitée par
    %### BEGIN <zone_name> ### et %### END <zone_name> ###

    - Les lignes BEGIN/END doivent correspondre exactement,
      avec éventuellement des espaces en fin de ligne.
    - Si remove_comment_char=True, supprime un seul '%' en début de ligne
      (et l'espace qui suit éventuellement).
    """
    pattern = (
        rf"^%### BEGIN {re.escape(zone_name)} ### *\r?\n"  # ligne BEGIN stricte
        r"(.*?)"  # contenu capturé
        rf"^%### END {re.escape(zone_name)} ### *$"  # ligne END stricte
    )
    match = re.search(pattern, text, flags=re.DOTALL | re.MULTILINE)
    if not match:
        return None

    content = match.group(1).rstrip("\n")

    if remove_comment_char:
        cleaned_lines = []
        for line in content.splitlines():
            # Supprime un seul '%' en début de ligne, et l'espace qui suit s'il existe
            cleaned_lines.append(re.sub(r"^% ?", "", line))
        return "\n".join(cleaned_lines).rstrip("\n")

    return content


def find_tex_entity(text: str, name: str, kind: str = "command_declaration"):
    """
    Recherche des entités LaTeX dans le texte.

            kind peut être :
                - "command_declaration" → dernière déclaration
                - "package_options" → options du dernier import
                - "command" → toutes les occurrences

    """
    parsers = {
        "command_declaration": (parse_tex_command_declaration, "last"),
        "package_options": (parse_package_import, "last"),
        "command": (parse_tex_command, "all"),
    }

    if kind not in parsers:
        raise ValueError(f"Type de recherche inconnu: {kind}")

    parser, mode = parsers[kind]

    results = []
    for line in text.splitlines():
        parsed = parser(line)

        if parsed and parsed.get("name") == name:
            results.append(parsed)

    if mode == "last":
        if not results:
            return [] if kind == "package_options" else None
        last = results[-1]
        if kind == "package_options":
            return last.get("options", [])
        return last
    else:  # mode == "all"
        return results


def parse_tex_command(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse une ligne TeX pour extraire l'appel d'une commande.

    Retourne un dict avec :
        - name : nom de la commande
        - args : liste de dicts {"value": str, "required": True}
    """
    stripped = line.lstrip()
    if stripped.startswith("%"):
        return None

    # Cherche une commande \Nom{...}{...}...
    m = re.match(r"\\(?P<name>[A-Za-z@]+)", stripped)
    if not m:
        return None

    name = m.group("name")
    args: List[Dict[str, Any]] = []

    pos = m.end()
    while pos < len(stripped):
        if stripped[pos].isspace():
            pos += 1
            continue
        if stripped[pos] == '{':
            val = _extract_braced_value(stripped, pos)
            args.append({"value": val, "required": True})
            # avancer jusqu'à la fin du bloc
            depth = 0
            while pos < len(stripped):
                if stripped[pos] == '{':
                    depth += 1
                elif stripped[pos] == '}':
                    depth -= 1
                    if depth == 0:
                        pos += 1
                        break
                pos += 1
        else:
            break

    return {"name": name, "args": args}


def parse_tex_command_declaration(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse une ligne TeX pour extraire les infos de déclaration de commande.

    Retourne un dict avec :
        - decl : type (def, gdef, edef, xdef, newcommand, renewcommand, ...)
        - name : nom de la commande
        - value : corps de la commande
        - options : éventuelles options (string ou None)
        - args : nombre d’arguments attendus (0 si aucun)
        - required : liste de booléens (True = obligatoire, False = optionnel)
    """
    stripped = line.lstrip()
    if stripped.startswith("%"):
        return None

    # --- Cas newcommand / renewcommand (+ variantes x et *)
    pat_cmdx = re.compile(
        r"\\(?P<decl>(?:new|renew)commandx?\*?)\s*"
        r"\{\\(?P<name>[A-Za-z@]+)\}"
        r"(?:\[(?P<args>\d+)\])?"  # nb d’args
        r"(?:\[(?P<opt_spec>[^\]]*)\])?"  # spec optionnelle (newcommandx)
        r"\{"
    )
    m = pat_cmdx.search(line)
    if m:
        n = int(m.group("args")) if m.group("args") else 0
        flags = [True] * n
        opt_spec = m.group("opt_spec")
        if opt_spec and "commandx" in m.group("decl"):
            for item in opt_spec.split(","):
                item = item.strip()
                if not item:
                    continue
                k_match = re.match(r"(\d+)\s*=", item)
                if k_match:
                    k = int(k_match.group(1))
                    if 1 <= k <= n:
                        flags[k - 1] = False

        # reculer d’un caractère pour inclure la vraie accolade ouvrante
        value = _extract_braced_value(line, m.end() - 1)
        return {
            "decl": m.group("decl"),
            "name": m.group("name"),
            "value": value,
            "options": opt_spec,
            "args": n,
            "required": flags,
        }

    # --- Cas def / gdef / edef / xdef
    pat_def = re.compile(
        r"\\(?P<decl>[egx]?def)\s*\\(?P<name>[A-Za-z@]+)" r"(?P<sig>(?:#\d+)*)\s*\{"
    )
    m = pat_def.search(line)
    if m:
        indices = re.findall(r"#(\d+)", m.group("sig") or "")
        n_args = int(max(indices)) if indices else 0
        flags = [True] * n_args
        value = _extract_braced_value(line, m.end() - 1)
        return {
            "decl": m.group("decl"),
            "name": m.group("name"),
            "value": value,
            "options": None,
            "args": n_args,
            "required": flags,
        }

    return None


def parse_package_import(line: str) -> Optional[Dict[str, Any]]:
    """Parse une ligne LaTeX pour détecter usepackage / RequirePackage.

    Retourne dict {'decl': 'usepackage'|'RequirePackage', 'name': <package>,
    'options': [opt1, opt2, ...]} ou None.
    """
    if not line or line.lstrip().startswith("%"):
        return None

    # Regex: decl (usepackage|RequirePackage), options optional, {names}
    m = re.search(
        r"\\(?P<decl>usepackage|RequirePackage)\s*(?:\[(?P<opts>[^]]*)\])?\s*\{(?P<name>[^}]*)\}",
        line,
    )
    if not m:
        return None

    decl = m.group("decl")
    raw_opts = m.group("opts") or ""
    name = m.group("name").strip()

    opts = [t.strip() for t in raw_opts.split(",") if t.strip()]

    return {"decl": decl, "name": name, "options": opts}


def parse_package_imports(content: str) -> List[str]:
    r"""Retourne la liste des noms de packages importés.

    Gère:
      - options: \\usepackage[optA,optB]{pkg}
      - imports multiples: \\usepackage{pkgA,pkgB}
      - chemins: \\usepackage{Dummy/Path/UPSTI_Document} -> UPSTI_Document
    """
    pat = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
    packages: List[str] = []
    for m in pat.findall(content):
        for raw in m.split(','):
            raw = raw.strip()
            if not raw:
                continue
            # Normaliser séparateurs de chemin
            base = raw.replace('/', '\\').split('\\')[-1]
            packages.append(base)
    return packages


def _extract_braced_value(s: str, start: int) -> str:
    """Extrait le contenu d’un bloc {...} en gérant les accolades imbriquées."""
    depth = 0
    value = []
    for i in range(start, len(s)):
        ch = s[i]
        if ch == '{':
            depth += 1
            if depth == 1:
                continue  # ne pas inclure la première {
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return ''.join(value)
        value.append(ch)
    return ''.join(value)  # si jamais mal équilibré
