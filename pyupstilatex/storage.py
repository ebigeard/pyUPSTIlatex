from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageProtocol(Protocol):
    """Protocole définissant l'interface de stockage pour les documents."""

    def read_text(self, source: str) -> str:
        """Lit le contenu textuel d'une source.

        Paramètres
        ----------
        source : str
            Chemin ou identifiant de la source à lire.

        Retourne
        --------
        str
            Le contenu textuel de la source.
        """
        ...

    def exists(self, source: str) -> bool:
        """Vérifie si une source existe.

        Paramètres
        ----------
        source : str
            Chemin ou identifiant de la source à vérifier.

        Retourne
        --------
        bool
            True si la source existe, False sinon.
        """
        ...

    def write_text(self, source: str, content: str) -> None:
        """Écrit du contenu textuel dans une source.

        Paramètres
        ----------
        source : str
            Chemin ou identifiant de la destination.
        content : str
            Contenu à écrire.
        """
        ...


class FileSystemStorage:
    """Implémentation du stockage basée sur le système de fichiers local."""

    def read_text(self, source):
        """Lit le contenu d'un fichier local en UTF-8.

        Paramètres
        ----------
        source : str
            Chemin du fichier à lire.

        Retourne
        --------
        str
            Le contenu du fichier.

        Raises
        ------
        FileNotFoundError
            Si le fichier n'existe pas.
        UnicodeDecodeError
            Si le fichier ne peut pas être décodé en UTF-8.
        """
        p = Path(source)
        return p.read_text(encoding="utf-8", errors="strict")

    def exists(self, source):
        """Vérifie si un fichier local existe.

        Paramètres
        ----------
        source : str
            Chemin du fichier à vérifier.

        Retourne
        --------
        bool
            True si le fichier existe, False sinon.
        """
        return Path(source).exists()

    def write_text(self, source, content):
        """Écrit du contenu dans un fichier local en UTF-8.

        Paramètres
        ----------
        source : str
            Chemin du fichier de destination.
        content : str
            Contenu à écrire.
        """
        p = Path(source)
        p.write_text(content, encoding="utf-8")


class DjangoStorageAdapter:
    """Adaptateur pour utiliser un backend de stockage Django."""

    def __init__(self, django_storage):
        """Initialise l'adaptateur.

        Paramètres
        ----------
        django_storage : django.core.files.storage.Storage
            Instance de stockage Django à adapter.
        """
        self.storage = django_storage

    def read_text(self, source):
        """Lit le contenu d'un fichier via le stockage Django.

        Paramètres
        ----------
        source : str
            Chemin du fichier à lire.

        Retourne
        --------
        str
            Le contenu du fichier.
        """
        with self.storage.open(source, "r") as f:
            return f.read()

    def exists(self, source):
        """Vérifie si un fichier existe dans le stockage Django.

        Paramètres
        ----------
        source : str
            Chemin du fichier à vérifier.

        Retourne
        --------
        bool
            True si le fichier existe, False sinon.
        """
        return self.storage.exists(source)

    def write_text(self, source, content):
        """Écrit du contenu dans un fichier via le stockage Django.

        Si le fichier existe déjà, il est supprimé puis recréé.

        Paramètres
        ----------
        source : str
            Chemin du fichier de destination.
        content : str
            Contenu à écrire.
        """
        from django.core.files.base import ContentFile  # type: ignore[import-not-found]

        if self.exists(source):
            self.storage.delete(source)
        self.storage.save(source, ContentFile(content))
