import logging
from dataclasses import dataclass
from typing import Callable, Dict, Optional

# Séparateurs
SEPARATORS = {
    "separateur1": 88 * "═",
    "separateur2": 88 * "─",
    "separateur3": 88 * "-",
}

# Codes couleurs ANSI
COLOR_GREEN = "\033[92m"
COLOR_ORANGE = "\033[38;5;214m"
COLOR_RED = "\033[91m"
COLOR_LIGHT_BLUE = "\033[94m"
COLOR_LIGHT_GREEN = "\033[38;2;200;255;200m"
COLOR_DARK_GRAY = "\033[90m"
COLOR_RESET = "\033[0m"


@dataclass
class FormattedMessage:
    text: str
    level: int


Formatter = Callable[[str, Optional[str]], FormattedMessage]


# -----------------------------
# Utilitaires
# -----------------------------
def _annoted_text(
    text: str, flag: Optional[str], version: Optional[str] = "full"
) -> str:
    """Annote un texte avec des symboles et couleurs selon le flag.

    Paramètres
    ----------
    text : str
        Le texte à annoter.
    flag : str, optional
        Type d'annotation : 'success', 'warning', 'error', 'fatal_error', 'info'.
    version : str, optional
        Version de l'annotation : 'full' (défaut) ou 'compact'.

    Retourne
    --------
    str
        Le texte annoté avec symboles et couleurs ANSI.
    """
    if version == "compact":
        text_info = "i"
        text_success = "✓"
        text_warning = "!"
        text_error = "✗"
    else:
        text_info = "INFO"
        text_success = "OK"
        text_warning = "WARNING"
        text_error = "ERREUR"

    if flag == "success":
        return f"{COLOR_GREEN}{text_success}{COLOR_RESET} : {text}"
    elif flag == "warning":
        return f"{COLOR_ORANGE}{text_warning}{COLOR_RESET} : {text}"
    elif flag in ("error", "fatal_error"):
        return f"{COLOR_RED}{text_error}{COLOR_RESET} : {text}"
    elif flag == "info":
        return f"{COLOR_LIGHT_BLUE}{text_info}{COLOR_RESET} : {text}"
    return text


def _level_from_flag(flag: Optional[str]) -> int:
    """Convertit un flag en niveau de logging.

    Paramètres
    ----------
    flag : str, optional
        Type de flag : 'warning', 'error', 'fatal_error', ou autre.

    Retourne
    --------
    int
        Niveau de logging correspondant (logging.WARNING, logging.ERROR, ou logging.INFO).
    """
    if flag == "warning":
        return logging.WARNING
    elif flag in ("error", "fatal_error"):
        return logging.ERROR
    return logging.INFO


def fmt_generic(
    t: str,
    flag: Optional[str] = None,
    prefix: str = "",
    suffix: str = "",
    version: str = "full",
) -> FormattedMessage:
    """Formate un message générique avec préfixe et suffixe.

    Paramètres
    ----------
    t : str
        Le texte du message.
    flag : str, optional
        Type de flag pour l'annotation.
    prefix : str, optional
        Préfixe à ajouter avant le texte. Défaut : "".
    suffix : str, optional
        Suffixe à ajouter après le texte. Défaut : "".
    version : str, optional
        Version de l'annotation ('full' ou 'compact'). Défaut : "full".

    Retourne
    --------
    FormattedMessage
        Message formaté avec son niveau de logging.
    """
    return FormattedMessage(
        f"{prefix}{_annoted_text(t, flag, version)}{suffix}", _level_from_flag(flag)
    )


def fmt_separator(key: str, flag: Optional[str] = None) -> FormattedMessage:
    """Formate un séparateur visuel.

    Paramètres
    ----------
    key : str
        Clé du séparateur dans SEPARATORS ('separateur1', 'separateur2', 'separateur3').
    flag : str, optional
        Type de flag pour le niveau de logging.

    Retourne
    --------
    FormattedMessage
        Séparateur formaté en gris avec son niveau de logging.
    """
    # Affiche les séparateurs en gris pour plus de discrétion
    sep = SEPARATORS[key]
    return FormattedMessage(
        f"{COLOR_DARK_GRAY}{sep}{COLOR_RESET}", _level_from_flag(flag)
    )


# -----------------------------
# Formatters centralisés
# -----------------------------
DEFAULT_FORMATTERS: Dict[str, Formatter] = {
    "titre1": lambda t, f=None: fmt_generic(
        t,
        f,
        prefix=f"{fmt_separator('separateur1').text}\n",
        suffix=f"\n{fmt_separator('separateur1').text}",
    ),
    "titre2": lambda t, f=None: fmt_generic(
        t,
        f,
        prefix=f"{fmt_separator('separateur2').text}\n",
        suffix=f"\n{fmt_separator('separateur2').text}",
    ),
    "titre3": lambda t, f=None: fmt_generic(
        t, f, suffix=f"\n{fmt_separator('separateur3').text}"
    ),
    "titre4": lambda t, f=None: fmt_generic(t, f),
    "text": lambda t, f=None: fmt_generic(t, f),
    "info": lambda t, f=None: fmt_generic(t, f, prefix="  "),
    "resultat": lambda t, f=None: fmt_generic(t, f, prefix="    └─> "),
    "resultat_item": lambda t, f=None: fmt_generic(t, f),  # géré dans format_message
    "resultat_conclusion": lambda t, f=None: fmt_generic(
        t, f, prefix="    │\n    └─> "
    ),
    "conclusion": lambda t, f=None: fmt_generic(t, f, prefix="\n└─> "),
    "saut": lambda t, f=None: FormattedMessage("", _level_from_flag(f)),
    "separateur1": lambda t, f=None: fmt_separator("separateur1", f),
    "separateur2": lambda t, f=None: fmt_separator("separateur2", f),
    "separateur3": lambda t, f=None: fmt_separator("separateur3", f),
}


# -----------------------------
# Classe principale
# -----------------------------
class MessageHandler:
    """Gestionnaire de messages avec logging configurable.

    Paramètres
    ----------
    log_file : str, optional
        Chemin du fichier de log. Si None, pas de logging fichier.
    verbose : bool, optional
        Active le mode verbeux. Défaut : True.
    logger_name : str, optional
        Nom du logger. Défaut : "pyUPSTIlatex".
    console_level : int, optional
        Niveau de logging console. Défaut : logging.INFO.
    file_level : int, optional
        Niveau de logging fichier. Défaut : logging.DEBUG.
    formatters : Dict[str, Formatter], optional
        Dictionnaire de formatters personnalisés. Si None, utilise DEFAULT_FORMATTERS.
    """

    def __init__(
        self,
        log_file: Optional[str] = None,
        verbose: bool = True,
        logger_name: str = "pyUPSTIlatex",
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        formatters: Optional[Dict[str, Formatter]] = None,
    ):
        self.verbose = bool(verbose)
        self._logger = logging.getLogger(logger_name)
        self._formatters = formatters or DEFAULT_FORMATTERS
        self._configure_logger(log_file, console_level, file_level)

    def _configure_logger(self, log_file, console_level, file_level):
        """Configure le logger avec handlers console et fichier.

        Paramètres
        ----------
        log_file : str, optional
            Chemin du fichier de log.
        console_level : int
            Niveau de logging pour la console.
        file_level : int
            Niveau de logging pour le fichier.
        """
        if not self._logger.handlers:
            self._logger.setLevel(logging.DEBUG)
            console = logging.StreamHandler()
            console.setLevel(console_level if self.verbose else logging.WARNING)
            console.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(console)
            if log_file:
                fh = logging.FileHandler(log_file, encoding="utf-8")
                fh.setLevel(file_level)
                fh.setFormatter(
                    logging.Formatter(
                        "%(asctime)s %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
                    )
                )
                self._logger.addHandler(fh)

    def format_message(
        self, typ: str, texte: str, flag: str = None, last: bool = False
    ) -> FormattedMessage:
        """Formate un message selon son type.

        Paramètres
        ----------
        typ : str
            Type de message (ex: 'titre1', 'info', 'resultat_item', etc.).
        texte : str
            Contenu du message.
        flag : str, optional
            Flag d'annotation ('success', 'warning', 'error', etc.).
        last : bool, optional
            Indique si c'est le dernier élément d'une liste. Défaut : False.

        Retourne
        --------
        FormattedMessage
            Message formaté prêt à être logé.
        """
        fmt = self._formatters.get(typ)
        if typ == "resultat_item":
            char = "└" if last else "├"
            return fmt_generic(
                texte,
                flag,
                prefix=f"    {COLOR_DARK_GRAY}{char}─{COLOR_RESET} ",
                version="compact",
            )
        return (
            fmt(texte or "", flag)
            if fmt
            else FormattedMessage(texte or "", _level_from_flag(flag))
        )

    def emit(self, message: dict):
        """Émet un message via le logger.

        Paramètres
        ----------
        message : dict
            Dictionnaire contenant les clés :
            - 'type' : type de message
            - 'texte' : contenu du message
            - 'flag' : flag d'annotation (optional)
            - 'verbose' : si False, ignore le message (optional)
            - 'last' : si True, dernier d'une liste (optional)
        """
        if not message or (message.get("verbose") is False):
            return
        typ = message.get("type", "info")
        if not self.verbose and typ in ("info", "resultat", "resultat_item", "action"):
            return
        texte = message.get("texte", "")
        flag = message.get("flag")
        last = message.get("last", False)
        formatted = self.format_message(typ, texte, flag, last)
        if formatted.text == "" and formatted.level == logging.INFO:
            self._logger.info("")
        else:
            self._logger.log(formatted.level, formatted.text)

    # Helpers
    def msg(
        self, typ: str, texte: str, verbose: Optional[bool] = None, flag: str = None
    ):
        """Helper pour émettre rapidement un message.

        Paramètres
        ----------
        typ : str
            Type de message.
        texte : str
            Contenu du message.
        verbose : bool, optional
            Contrôle si le message doit être affiché.
        flag : str, optional
            Flag d'annotation.
        """
        m = {"type": typ, "texte": texte}
        if verbose is not None:
            m["verbose"] = verbose
        if flag is not None:
            m["flag"] = flag
        self.emit(m)

    # Méthodes pratiques
    def titre1(self, texte, verbose=None):
        self.msg("titre1", texte, verbose)

    def titre2(self, texte, verbose=None):
        self.msg("titre2", texte, verbose)

    def titre3(self, texte, verbose=None):
        self.msg("titre3", texte, verbose)

    def titre4(self, texte, verbose=None):
        self.msg("titre4", texte, verbose)

    def text(self, texte, verbose=None, flag=None):
        self.msg("text", texte, verbose, flag)

    def info(self, texte, verbose=None, flag=None):
        self.msg("info", texte, verbose, flag)

    def resultat(self, texte, verbose=None, flag=None):
        self.msg("resultat", texte, verbose, flag)

    def resultat_item(self, texte, verbose=None, flag=None, last: bool = False):
        m = {"type": "resultat_item", "texte": texte}
        if verbose is not None:
            m["verbose"] = verbose
        if flag is not None:
            m["flag"] = flag
        if last:
            m["last"] = True
        self.emit(m)

    def resultat_conclusion(self, texte, verbose=None, flag=None):
        self.msg("resultat_conclusion", texte, verbose, flag)

    def conclusion(self, texte, verbose=None, flag=None):
        self.msg("conclusion", texte, verbose, flag)

    def success(self, texte, verbose=None):
        self.msg("info", texte, verbose, flag="success")

    def saut(self):
        self.msg("saut", "")

    def separateur1(self):
        self.msg("separateur1", "")

    def separateur2(self):
        self.msg("separateur2", "")

    def separateur3(self):
        self.msg("separateur3", "")

    def affiche_messages(
        self, messages: list[object], type: str = "info", format_last: bool = True
    ):
        if not messages:
            return
        writer = {
            "info": self.info,
            "resultat": self.resultat,
            "resultat_item": self.resultat_item,
            "text": self.text,
        }.get(type, self.info)
        for idx, entry in enumerate(messages):
            texte, flag = (
                (entry[0], entry[1])
                if isinstance(entry, (list, tuple))
                else (str(entry), None)
            )
            is_last = idx == len(messages) - 1
            # Use the provided `type` parameter to decide passing `last`.
            if type == "resultat_item" and format_last:
                writer(texte, flag=flag, last=is_last)
            else:
                writer(texte, flag=flag)


class NoOpMessageHandler:
    """Handler silencieux qui implémente l'interface MessageHandler sans rien faire."""

    def emit(self, message: dict):
        pass

    def msg(
        self, typ: str, texte: str, verbose: Optional[bool] = None, flag: str = None
    ):
        pass

    def titre1(self, texte, verbose=None):
        pass

    def titre2(self, texte, verbose=None):
        pass

    def titre3(self, texte, verbose=None):
        pass

    def titre4(self, texte, verbose=None):
        pass

    def text(self, texte, verbose=None, flag=None):
        pass

    def info(self, texte, verbose=None, flag=None):
        pass

    def resultat(self, texte, verbose=None, flag=None):
        pass

    def resultat_item(self, texte, verbose=None, flag=None, last: bool = False):
        pass

    def resultat_conclusion(self, texte, verbose=None, flag=None):
        pass

    def conclusion(self, texte, verbose=None, flag=None):
        pass

    def success(self, texte, verbose=None):
        pass

    def saut(self):
        pass

    def separateur1(self):
        pass

    def separateur2(self):
        pass

    def separateur3(self):
        pass

    def affiche_messages(
        self, messages: list[object], type: str = "info", format_last: bool = True
    ):
        pass
