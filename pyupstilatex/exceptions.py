class UPSTIError(Exception):
    """Base exception for pyUPSTIlatex"""


class DocumentParseError(UPSTIError):
    """Raised when parsing fails for a document"""
