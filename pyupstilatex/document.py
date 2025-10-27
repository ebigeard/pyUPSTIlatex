from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from .storage import FileSystemStorage
from .parsers import parse_yaml_front_matter, parse_tex_commands, parse_named_zones
from .exceptions import DocumentParseError


@dataclass
class UPSTILatexDocument:
    source: str
    storage: Any = field(default_factory=FileSystemStorage)
    _raw: Optional[str] = field(default=None, init=False)
    _meta: Optional[Dict] = field(default=None, init=False)
    _commands: Optional[Dict] = field(default=None, init=False)
    _zones: Optional[Dict] = field(default=None, init=False)

    @classmethod
    def from_path(cls, path: str, storage=None):
        return cls(source=path, storage=(storage or FileSystemStorage()))

    @classmethod
    def from_string(cls, content: str):
        inst = cls(source="<string>", storage=FileSystemStorage())
        inst._raw = content
        return inst

    def read(self) -> str:
        if self._raw is None:
            try:
                self._raw = self.storage.read_text(self.source)
            except Exception as e:
                raise DocumentParseError(f"Unable to read source {self.source}: {e}")
        return self._raw

    def refresh(self):
        self._raw = None
        self._meta = None
        self._commands = None
        self._zones = None
        return self.read()

    @property
    def metadata(self) -> Dict:
        if self._meta is None:
            self._meta = parse_yaml_front_matter(self.read())
        return self._meta or {}

    def get_commands(self, names: Optional[List[str]] = None) -> Dict[str, List[Optional[str]]]:
        if self._commands is None:
            self._commands = parse_tex_commands(self.read(), names=names)
        return self._commands

    def list_zones(self) -> List[str]:
        if self._zones is None:
            self._zones = parse_named_zones(self.read())
        return list(self._zones.keys())

    def get_zone(self, name: str):
        if self._zones is None:
            self._zones = parse_named_zones(self.read())
        vals = self._zones.get(name)
        if not vals:
            return None
        return vals if len(vals) > 1 else vals[0]

    def to_dict(self):
        return {
            "source": self.source,
            "metadata": self.metadata,
            "commands": self.get_commands(),
            "zones": self._zones or parse_named_zones(self.read()),
        }
