import json
import logging
import re
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from datetime import datetime, timezone
from itertools import count, product
from json.decoder import JSONDecodeError
from math import ceil, floor, log10
from os import PathLike, getpid
from pathlib import Path
from traceback import format_exception
from typing import (
    Any,
    Dict,
    Generator,
    Generic,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from dacite import DaciteError

try:
    import colorlog
except ImportError:
    colorlog = None  # type: ignore

import typing

from cordage.global_config import GlobalConfig
from cordage.util import (
    config_output_dir_type,
    flattened_items,
    from_dict,
    logger,
    nest_items,
    nested_update,
    to_dict,
)

if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance


ConfigClass = TypeVar("ConfigClass", bound="DataclassInstance")


@dataclass
class Metadata:
    function: str

    global_config: GlobalConfig

    configuration: Dict[str, Any]

    output_dir: Optional[Path] = None
    status: str = "pending"

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    result: Any = None

    parent_dir: Optional[Path] = None

    additional_info: Dict = field(default_factory=dict)

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
    _warned_deprecated_nested_global_config: bool = False

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

    def create_output_dir(self):
        if self.metadata.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.set_output_dir(self.output_dir)
            return self.output_dir

        tried_paths: Set[Path] = set()
        suffix = ""

        for i in count(1):
            if i > 1:
                level = floor(log10(i) / 2) + 1
                suffix = "_" * level + str(i).zfill(2 * level)

            path = (
                self.global_config.base_output_dir
                / self.global_config.output_dir_format.format(
                    **self.metadata.__dict__,
                    collision_suffix=suffix,
                )
            )

            if path in tried_paths:
                # suffix was already tried: assume that further tries
                # wont resolve this collision
                msg = f"Path {path} does already exist - collision could not be avoided."
                raise RuntimeError(msg)

            try:
                path.mkdir(parents=True, exist_ok=False)
                self.set_output_dir(path)
                return path
            except FileExistsError:
                if self.global_config.overwrite_existing:
                    logger.warning(
                        "Path %s does existing. Replacing directory with new one.", str(path)
                    )
                    shutil.rmtree(path)
                    path.mkdir(parents=True)
                    self.set_output_dir(path)
                    return path
                else:
                    tried_paths.add(path)

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
            metadata_dict = json.load(fp)

            if "logging" in metadata_dict["global_config"]:
                if not cls._warned_deprecated_nested_global_config:
                    logger.warning("Using deprecated nested global_config format.")
                    cls._warned_deprecated_nested_global_config = True

                for k, v in metadata_dict["global_config"]["logging"].items():
                    metadata_dict["global_config"][f"logging_{k}"] = v

                for k, v in metadata_dict["global_config"]["param_names"].items():
                    metadata_dict["global_config"][f"param_name_{k}"] = v

                del metadata_dict["global_config"]["logging"]
                del metadata_dict["global_config"]["param_names"]

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


class Experiment(Annotatable):
    def __init__(self, *args, config_cls: Optional[Type] = None, **kwargs):
        super().__init__(*args, **kwargs)

        self.config_cls = config_cls
        self.log_handlers: List[logging.Handler] = []

    def __repr__(self):
        if self.metadata.output_dir is not None:
            return f"{self.__class__.__name__} ({self.output_dir}, status: {self.status})"
        else:
            return f"{self.__class__.__name__} (status: {self.status})"

    @property
    def log_path(self):
        return self.output_dir / self.global_config.logging_filename

    @property
    def status(self) -> str:
        return self.metadata.status

    @property
    def result(self) -> Any:
        return self.metadata.result

    def has_status(self, *status: str):
        return len(status) == 0 or self.status in status

    def start(self):
        """Start the execution of an experiment.

        Set start time, create output directory, registers run, etc.
        """
        assert self.config_cls is not None
        assert self.status == "pending", f"{self.__class__.__name__} has already been started."
        self.metadata.start_time = datetime.now(timezone.utc).astimezone()
        self.metadata.status = "running"
        self.metadata.additional_info["process_id"] = getpid()
        self.create_output_dir()
        self.save_metadata()
        self.save_annotations()
        self.setup_log()

    def end(self, status: str = "undecided"):
        """End the execution of an experiment.

        Write metadata, close logs, etc.
        """
        self.metadata.end_time = datetime.now(timezone.utc).astimezone()
        self.metadata.status = status
        self.save_metadata()
        self.save_annotations()
        self.teardown_log()

    def handle_exception(self, exc_type, exc_value, traceback):
        traceback_string = "".join(format_exception(exc_type, value=exc_value, tb=traceback))

        logger.exception("", exc_info=(exc_type, exc_value, traceback))
        self.metadata.additional_info["exception"] = {
            "short": repr(exc_value),
            "traceback": traceback_string,
        }

    def __enter__(self):
        self.start()
        logger.info("%s '%s' started.", self.__class__.__name__, str(self.output_dir))

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            logger.info("%s '%s' completed.", self.__class__.__name__, str(self.output_dir))
            self.end(status="complete")
        elif issubclass(exc_type, KeyboardInterrupt):
            logger.warning("%s '%s' aborted.", self.__class__.__name__, str(self.output_dir))
            self.end(status="aborted")
            return False
        else:
            self.handle_exception(exc_type, exc_value, traceback)
            logger.warning("%s '%s' failed.", self.__class__.__name__, str(self.output_dir))
            self.end(status="failed")
            return False

    def synchronize(self):
        """Synchronize to existing output directory."""
        assert (
            self.metadata.output_dir is not None
        ), f"Cannot synchronize a {self.__class__.__name__} which has no `output_dir`."

        if self.metadata.output_dir.exists():
            metadata = self.load_metadata(self.metadata.output_dir)

            if not isinstance(self.metadata.configuration, dict):
                metadata.configuration = from_dict(
                    type(self.metadata.configuration), metadata.configuration
                )

            self.metadata = metadata

            self.load_annotations()
        else:
            logger.warning("No metadata found. Skipping synchronization.")

        return self

    @classmethod
    def from_path(cls, path: PathLike, config_cls: Optional[Type[ConfigClass]] = None):
        metadata: Metadata = cls.load_metadata(path)

        experiment: Experiment
        if not metadata.is_series:
            experiment = Trial(metadata, config_cls=config_cls)

        else:
            experiment = Series(metadata, config_cls=config_cls)

        experiment.load_annotations()

        return experiment

    @classmethod
    def all_from_path(
        cls, results_path: Union[str, PathLike], *, skip_hidden: bool = True
    ) -> List["Experiment"]:
        """Load all experiments from the results_path."""
        results_path = Path(results_path)

        seen_dirs: Set[Path] = set()
        experiments = []

        for p in results_path.rglob("*/cordage.json"):
            if skip_hidden and any(
                part.startswith(".") for part in (p.relative_to(results_path)).parts
            ):
                continue

            path = p.parent

            if path.parent in seen_dirs:
                # we already encountered a parent experiment (series)
                continue

            seen_dirs.add(path)

            try:
                experiments.append(cls.from_path(p.parent))
            except (JSONDecodeError, DaciteError) as exc:
                logger.warning("Couldn't load '%s': %s", str(path), str(exc))

        return sorted(experiments, key=lambda exp: exp.output_dir)

    def setup_log(self):
        logger = logging.getLogger()

        if not self.global_config.logging_use:
            return

        # in this case, a StreamHandler was set up by the series
        is_toplevel = self.metadata.parent_dir is None

        handler: logging.Handler

        if self.global_config.logging_to_stream and is_toplevel:
            # add colored stream handler
            format_str = "%(name)s:%(filename)s:%(lineno)d - %(message)s"

            if colorlog is not None:
                handler = colorlog.StreamHandler()
                handler.setFormatter(
                    colorlog.ColoredFormatter(
                        f"%(log_color)s%(levelname)-8s%(reset)s {format_str}"
                    )
                )
            else:
                handler = logging.StreamHandler()
                handler.setFormatter(logging.Formatter(f"%(levelname)-8s {format_str}"))

            logger.addHandler(handler)
            self.log_handlers.append(handler)

        if self.global_config.logging_to_file:
            # setup logging to local output_dir
            formatter = logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s:%(filename)s:%(lineno)d - %(message)s"
            )
            handler = logging.FileHandler(self.log_path)
            handler.setFormatter(formatter)

            logger.addHandler(handler)
            self.log_handlers.append(handler)

    def teardown_log(self):
        logger = logging.getLogger()

        for handler in self.log_handlers:
            handler.close()
            logger.removeHandler(handler)


class Trial(Experiment, Generic[ConfigClass]):
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        config: Optional[Dict[str, Any]] = None,
        config_cls=None,
        **kw,
    ):
        if metadata is not None:
            if len(kw) == 0 and config is None:
                super().__init__(metadata, config_cls=config_cls)
            else:
                msg = "If metadata are provided, config and additional keywords can not be set."
                raise TypeError(msg)
        else:
            super().__init__(configuration=config, config_cls=config_cls, **kw)

        self._config: Optional[ConfigClass] = None

    @property
    def config(self) -> ConfigClass:
        if self._config is None:
            if self.config_cls is None:
                msg = (
                    "`trial.config` is only available if the configuration was loaded with a "
                    "configuration dataclass. You could use `trial.metadata.configuration` "
                    "instead or pass `config_cls` to the trial initializer."
                )
                raise AttributeError(msg)

            if self.metadata.output_dir is not None:
                self.set_output_dir(self.metadata.output_dir)

            # Create the config object
            self._config = from_dict(
                self.config_cls,
                self.metadata.configuration,
                strict=self.metadata.global_config.strict_mode,
            )

        return self._config

    def set_output_dir(self, path: Path):
        super().set_output_dir(path)

        if self.config_cls is not None:
            output_dir_type = config_output_dir_type(
                self.config_cls, self.global_config.param_name_output_dir
            )

            if output_dir_type is not None:
                self.metadata.configuration["output_dir"] = path

                # Config has attribute output_dir, mypy does not know it
                if self._config is not None:
                    self.config.output_dir = output_dir_type(path)  # type: ignore


class Series(Generic[ConfigClass], Experiment):
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        base_config: Optional[Dict[str, Any]] = None,
        series_spec: Union[List[Dict], Dict[str, List], None] = None,
        series_skip: Optional[int] = None,
        config_cls=None,
        **kw,
    ):
        if metadata is not None:
            assert len(kw) == 0 and base_config is None and series_spec is None
            super().__init__(metadata, config_cls=config_cls)
        else:
            if isinstance(series_spec, list):
                series_spec = [
                    nest_items(flattened_items(trial_update, sep="."))
                    for trial_update in series_spec
                ]

            super().__init__(
                configuration={
                    "base_config": base_config,
                    "series_spec": series_spec,
                    "series_skip": series_skip,
                },
                config_cls=config_cls,
                **kw,
            )

        self.validate_series_spec()

        self.trials: Optional[List[Trial[ConfigClass]]] = None
        self.make_all_trials()

    def validate_series_spec(self):
        series_spec = self.series_spec

        if isinstance(series_spec, list):
            for config_update in series_spec:
                assert isinstance(config_update, dict)

        elif isinstance(series_spec, dict):

            def only_list_nodes(d):
                for v in d.values():
                    if isinstance(v, dict):
                        if not only_list_nodes(v):
                            return False
                    elif not isinstance(v, list):
                        return False
                    return True

            assert only_list_nodes(series_spec), f"Invalid series specification: {series_spec}"
        else:
            assert series_spec is None

    @property
    def base_config(self) -> Dict[str, Any]:
        return self.metadata.configuration["base_config"]

    @property
    def series_spec(self) -> Union[List[Dict], Dict[str, List], None]:
        return self.metadata.configuration["series_spec"]

    @property
    def series_skip(self) -> int:
        skip: Optional[int] = self.metadata.configuration.get("series_skip", None)

        if skip is None:
            return 0
        else:
            return skip

    @property
    def is_singular(self):
        return self.series_spec is None

    def __enter__(self):
        if not self.is_singular:
            super().__enter__()
        # else: do nothing

    def __exit__(self, *args):
        if not self.is_singular:
            super().__exit__(*args)
        # else: do nothing

    @overload
    def get_changing_fields(self, sep: Literal[None] = None) -> Set[Tuple[Any, ...]]: ...

    @overload
    def get_changing_fields(self, sep: str) -> Set[str]: ...

    def get_changing_fields(
        self, sep: Optional[str] = None
    ) -> Union[Set[Tuple[Any, ...]], Set[str]]:
        keys: Set = set()

        if isinstance(self.series_spec, list):
            for trial_update in self.series_spec:
                for k, _ in flattened_items(trial_update, sep=sep):
                    keys.add(k)

        elif isinstance(self.series_spec, dict):
            for k, _ in flattened_items(self.series_spec, sep=sep):
                keys.add(k)

        return keys

    def get_trial_updates(self) -> Generator[Dict, None, None]:
        if isinstance(self.series_spec, list):
            yield from self.series_spec
        elif isinstance(self.series_spec, dict):
            keys, values = zip(*flattened_items(self.series_spec, sep="."))

            for update_values in product(*values):
                yield nest_items(zip(keys, update_values))
        else:
            yield {}

    def __len__(self):
        if isinstance(self.series_spec, list):
            assert self.trials is None or len(self.trials) == len(self.series_spec), (
                f"Number of existing ({len(self.trials)}) and expected trials "
                f"({len(self.series_spec)}) do not match."
            )
            return len(self.series_spec)
        elif isinstance(self.series_spec, dict):
            num_trials = 1
            for _, values in flattened_items(self.series_spec):
                num_trials *= len(values)
            assert self.trials is None or len(self.trials) == num_trials, (
                f"Number of existing ({len(self.trials)}) and expected trials ({num_trials}) do "
                "not match."
            )
            return num_trials
        else:
            return 1

    def make_trial(self, **kw):
        additional_info = kw.pop("additional_info", None)

        fields_to_update: Dict[str, Any] = {
            "output_dir": None,
            "configuration": {},
            "additional_info": {},
            "status": "pending",
            "parent_dir": None,
            **kw,
        }

        trial_metadata = self.metadata.replace(**fields_to_update)

        if additional_info is not None:
            assert isinstance(additional_info, dict)
            trial_metadata.additional_info.update(additional_info)

        return Trial(trial_metadata, config_cls=self.config_cls)

    def make_all_trials(self):
        if self.series_spec is None:
            # single trial experiment
            logger.debug("Configuration yields a single experiment.")
            single_trial = self.make_trial(configuration=self.base_config)
            single_trial.annotations = self.annotations

            if self.metadata.output_dir is not None:
                single_trial.set_output_dir(self.metadata.output_dir)

            self.trials = [single_trial]

        else:
            logger.debug(
                "The given configuration yields an experiment series with %d experiments.",
                len(self),
            )
            self.trials = []

            for i, trial_update in enumerate(self.get_trial_updates()):
                trial_configuration: Dict[str, Any] = deepcopy(self.base_config)

                nested_update(trial_configuration, trial_update)

                if i < self.series_skip:
                    status = "skipped"
                else:
                    status = "pending"

                trial = self.make_trial(
                    configuration=trial_configuration,
                    additional_info={"trial_index": i},
                    status=status,
                )
                self.trials.append(trial)

    def __iter__(self):
        return self.get_all_trials(include_skipped=False)

    def get_all_trials(
        self, *, include_skipped: bool = False
    ) -> Generator[Trial[ConfigClass], None, None]:
        assert self.trials is not None

        if not self.is_singular:
            skip = 0 if include_skipped else self.series_skip

            for i, trial in enumerate(self.trials[skip:], start=skip):
                trial_subdir = str(i).zfill(ceil(log10(len(self))))

                trial.metadata.output_dir = self.output_dir / trial_subdir

                yield trial
        else:
            assert len(self.trials) == 1
            yield self.trials[0]
