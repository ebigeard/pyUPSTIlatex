"""
Tests pour le système de handlers de version.
"""

import pytest

from pyupstilatex.document import UPSTILatexDocument
from pyupstilatex.handlers import (
    DocumentVersionHandler,
    HandlerUPSTIDocumentV1,
    HandlerUPSTIDocumentV2,
)


def test_handler_lazy_initialization():
    """Vérifie que le handler est créé uniquement au premier appel."""
    # Créer un document sans version détectée
    doc = UPSTILatexDocument(source="test.tex")

    # Le handler ne doit pas être créé
    assert doc._handler is None
    assert doc._version is None


def test_v1_handler_selection():
    """Vérifie que HandlerUPSTIDocumentV1 est sélectionné pour un document v1."""
    # Simuler un document v1 (nécessite un vrai fichier ou mock)
    # Ce test nécessiterait un fichier .tex v1 réel ou un mock
    pass


def test_v2_handler_selection():
    """Vérifie que HandlerUPSTIDocumentV2 est sélectionné pour un document v2."""
    # Simuler un document v2 (nécessite un vrai fichier ou mock)
    # Ce test nécessiterait un fichier .tex v2 réel ou un mock
    pass


def test_handler_interface():
    """Vérifie que tous les handlers implémentent l'interface correcte."""
    from pyupstilatex.handlers import HandlerUPSTIDocumentV1, HandlerUPSTIDocumentV2

    # Vérifier que les handlers héritent de la classe abstraite
    assert issubclass(HandlerUPSTIDocumentV1, DocumentVersionHandler)
    assert issubclass(HandlerUPSTIDocumentV2, DocumentVersionHandler)

    # Vérifier que les méthodes abstraites sont implémentées
    required_methods = [
        'parse_metadata',
        'ajouter_metadonnee',
        'modifier_metadonnee',
        'supprimer_metadonnee',
    ]

    for handler_class in [HandlerUPSTIDocumentV1, HandlerUPSTIDocumentV2]:
        for method in required_methods:
            assert hasattr(handler_class, method)
            assert callable(getattr(handler_class, method))


def test_document_public_methods():
    """Vérifie que UPSTILatexDocument expose les bonnes méthodes publiques."""
    doc = UPSTILatexDocument(source="test.tex")

    # Vérifier que les méthodes publiques existent
    assert hasattr(doc, 'ajouter_metadonnee')
    assert hasattr(doc, 'modifier_metadonnee')
    assert hasattr(doc, 'supprimer_metadonnee')

    # Vérifier qu'elles sont callables
    assert callable(doc.ajouter_metadonnee)
    assert callable(doc.modifier_metadonnee)
    assert callable(doc.supprimer_metadonnee)


if __name__ == "__main__":
    # Lancer les tests basiques
    test_handler_interface()
    test_document_public_methods()
    print("✅ Tests de base réussis !")
