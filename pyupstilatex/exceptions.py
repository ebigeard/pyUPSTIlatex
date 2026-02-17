from typing import List


class UPSTIError(Exception):
    """Base exception for pyUPSTIlatex."""


class DocumentParseError(UPSTIError):
    """Raised when parsing fails for a document."""


class CompilationStepError(UPSTIError):
    """Exception levée quand une étape de compilation échoue.

    L'attribut `messages` contient la liste des messages générés lors de
    l'étape (liste de paires `[message, flag]`).

    Paramètres
    ----------
    messages : List[List[str]]
        Liste des messages générés lors de l'étape. Chaque message est
        une paire [message: str, flag: str].
    """

    def __init__(self, messages: List[List[str]]):
        self.messages = messages
        super().__init__()
