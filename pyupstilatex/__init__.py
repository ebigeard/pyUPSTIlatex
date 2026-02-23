"""pyUPSTIlatex package

Les secrets (FTP, SITE_SECRET_KEY) sont chargés depuis custom/.env
via config.py lors de l'appel à load_config().
Toute autre configuration provient des fichiers TOML.
"""

from __future__ import annotations

# Import et export de la classe de document (personnalisée ou par défaut)
from .document_registry import get_document_class

UPSTILatexDocument = get_document_class()

__all__ = ["UPSTILatexDocument"]
