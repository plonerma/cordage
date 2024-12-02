import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    Optional,
    TypeVar,
)

try:
    import colorlog
except ImportError:
    colorlog = None  # type: ignore

import typing
from enum import Enum

from cordage.global_config import GlobalConfig
from cordage.util import (
    from_dict,
    logger,
    to_dict,
)

if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance


ConfigClass = TypeVar("ConfigClass", bound="DataclassInstance")


class Status(str, Enum):
    UNKOWN = "unkown"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    ABORTED = "aborted"
    SKIPPED = "skipped"

    def __str__(self) -> str:
        return self.value

    @property
    def has_started(self):
        """The pname property."""
        return self not in (self.UNKOWN, self.PENDING)


@dataclass
class Metadata:
    function: str

    global_config: GlobalConfig

    configuration: dict[str, Any]

    output_dir: Optional[Path] = None
    status: Status = Status.UNKOWN

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    result: Any = None

    parent_dir: Optional[Path] = None

    additional_info: dict = field(default_factory=dict)

    @property
    def duration(self):
        assert self.end_time is not None and self.start_time is not None

        return self.end_time - self.start_time

    def replace(self, **changes):
        return dataclass_replace(self, **changes)

    @property
    def is_series(self):
        return isinstance(self.configuration, dict) and "series_spec" in self.configuration

    def to_dict(self):
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: Mapping):
        return from_dict(cls, data)


class MetadataStore:
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        global_config: Optional[GlobalConfig] = None,
        **kw,
    ):
        self.metadata: Metadata

        if metadata is not None:
            if global_config is not None or len(kw) > 0:
                msg = "Using the `metadata` argument is incompatible with using other arguments."
                raise TypeError(msg)
            else:
                self.metadata = metadata
        else:
            if global_config is None:
                global_config = GlobalConfig()

            self.metadata = Metadata(global_config=global_config, **kw)

    @property
    def global_config(self) -> GlobalConfig:
        return self.metadata.global_config

    @property
    def output_dir(self) -> Path:
        if self.metadata.output_dir is None:
            msg = f"{self.__class__.__name__} has not been started yet."
            raise RuntimeError(msg)
        else:
            return self.metadata.output_dir

    @property
    def parent_dir(self) -> Optional[Path]:
        return self.metadata.parent_dir

    def set_output_dir(self, path: Path):
        self.metadata.output_dir = path

    @property
    def metadata_path(self):
        return self.output_dir / "cordage.json"

    def save_metadata(self):
        md_dict = self.metadata.to_dict()

        with open(self.metadata_path, "w", encoding="utf-8") as fp:

            def invalid_obj_default(obj):
                logger.warning("Cannot serialize %s", str(obj))

            json.dump(md_dict, fp, indent=4, default=invalid_obj_default)

    @classmethod
    def load_metadata(cls, path: PathLike) -> Metadata:
        path = Path(path)
        if not path.suffix == ".json":
            path = path / "cordage.json"

        with path.open("r", encoding="utf-8") as fp:
            metadata_dict = GlobalConfig._convert_old_to_new(json.load(fp))
            metadata = Metadata.from_dict(metadata_dict)

        if metadata.output_dir != path.parent:
            logger.info(
                f"Output dir is not correct anymore. Changing it to the actual directory"
                f"({metadata.output_dir} -> {path.parent})"
            )
            metadata.output_dir = path.parent

        return metadata


class Annotatable(MetadataStore):
    TAG_PATTERN = re.compile(r"\B#(\w*[a-zA-Z]+\w*)")

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)

        self.annotations = {}

    @property
    def tags(self):
        tags = set(self.explicit_tags)

        # implicit tags
        tags.update(re.findall(self.TAG_PATTERN, self.comment))

        return list(tags)

    @property
    def explicit_tags(self):
        if "tags" not in self.annotations:
            self.annotations["tags"] = []
        return self.annotations["tags"]

    def add_tag(self, *tags: Iterable):
        for t in tags:
            if t not in self.explicit_tags:
                self.explicit_tags.append(t)

    def has_tag(self, *tags: str):
        return len(tags) == 0 or any(t in tags for t in self.tags)

    @property
    def comment(self):
        return self.annotations.get("comment", "") or ""

    @comment.setter
    def comment(self, value):
        self.annotations["comment"] = value

    @property
    def annotations_path(self):
        return self.output_dir / "annotations.json"

    def save_annotations(self):
        with open(self.annotations_path, "w", encoding="utf-8") as fp:
            json.dump(self.annotations, fp, indent=4)

    def load_annotations(self):
        if self.annotations_path.exists():
            with self.annotations_path.open("r", encoding="utf-8") as fp:
                self.annotations = json.load(fp)
