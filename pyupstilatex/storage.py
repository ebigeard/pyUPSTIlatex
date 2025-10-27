from pathlib import Path


class FileSystemStorage:
    def read_text(self, source):
        p = Path(source)
        return p.read_text(encoding="utf-8", errors="strict")

    def exists(self, source):
        return Path(source).exists()

    def write_text(self, source, content):
        p = Path(source)
        p.write_text(content, encoding="utf-8")


class DjangoStorageAdapter:
    def __init__(self, django_storage):
        self.storage = django_storage

    def read_text(self, source):
        with self.storage.open(source, "r") as f:
            return f.read()

    def exists(self, source):
        return self.storage.exists(source)

    def write_text(self, source, content):
        from django.core.files.base import ContentFile

        if self.exists(source):
            self.storage.delete(source)
        self.storage.save(source, ContentFile(content))
