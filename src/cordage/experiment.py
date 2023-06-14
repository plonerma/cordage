import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from datetime import datetime
from io import StringIO
from itertools import count, product
from json.decoder import JSONDecodeError
from math import ceil, floor, log10
from os import PathLike
from pathlib import Path
from traceback import format_exception
from typing import Any, Dict, Generator, Generic, Iterable, List, Mapping, Optional, Set, Type, TypeVar, Union, cast

try:
    import colorlog
except ImportError:
    colorlog = None  # type: ignore

from .global_config import GlobalConfig
from .util import flattened_items, from_dict, logger, nest_items, nested_update, to_dict

T = TypeVar("T")


@dataclass
class Metadata:
    function: str

    global_config: GlobalConfig

    output_dir: Optional[Path] = None
    experiment_id: Optional[str] = None
    status: str = "pending"

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    configuration: Any = None

    result: Any = None

    parent_id: Optional[str] = None

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
    def __init__(self, metadata: Optional[Metadata] = None, /, global_config: Optional[GlobalConfig] = None, **kw):
        self.metadata: Metadata

        if metadata is not None:
            if global_config is not None or len(kw) > 0:
                raise TypeError("Using the `metadata` argument is incompatible with using other arguments.")
            else:
                self.metadata = metadata
        else:
            if global_config is None:
                global_config = GlobalConfig()
            else:
                assert isinstance(global_config, GlobalConfig)

            self.metadata = Metadata(global_config=global_config, **kw)

    @property
    def experiment_id(self):
        if self.metadata.experiment_id is None:
            raise RuntimeError(f"{self.__class__.__name__} has not been started yet.")
        else:
            return self.metadata.experiment_id

    @property
    def parent_id(self):
        return self.metadata.parent_id

    def output_dir_from_id(self, experiment_id: Optional[str]):
        metadata = {**self.metadata.__dict__, "experiment_id": experiment_id}

        return self.global_config.base_output_dir / self.global_config.output_dir_format.format(**metadata)

    @property
    def global_config(self) -> GlobalConfig:
        return self.metadata.global_config

    @property
    def output_dir(self) -> Path:
        if self.metadata.output_dir is None:
            raise RuntimeError(f"{self.__class__.__name__} has not been started yet.")
        else:
            return self.metadata.output_dir

    @property
    def metadata_path(self):
        return self.output_dir / "cordage.json"

    def save_metadata(self):
        md_dict = self.metadata.to_dict()

        try:
            # test if the result is serializable
            stream = StringIO()
            json.dump(md_dict["result"], stream)
        except TypeError:
            # can't serialize return value, replace in with None
            md_dict["result"] = None

        with open(self.metadata_path, "w", encoding="utf-8") as fp:
            json.dump(md_dict, fp, indent=4)

    @classmethod
    def load_metadata(cls, path: PathLike) -> Metadata:
        path = Path(path)
        if not path.suffix == ".json":
            path = path / "cordage.json"

        with path.open("r", encoding="utf-8") as fp:
            metadata = Metadata.from_dict(json.load(fp))

        if metadata.output_dir != path.parent:
            logger.info(
                f"Output dir is not correct anymore. Changing it to the actual directory"
                f"({metadata.output_dir} -> {path.parent})"
            )
            metadata.output_dir = path.parent

            # adjust global_config.base_output_dir
            rel_theoretical_output_dir = Path(metadata.global_config.output_dir_format.format(**metadata.__dict__))

            suffix_matches = all(
                a == b for a, b in zip(metadata.output_dir.parts[::-1], rel_theoretical_output_dir.parts[::-1])
            )

            if not suffix_matches:
                logger.warning(
                    "Could not reconstruct base output directory (expected suffix: '%s', actual path: '%s'.",
                    str(rel_theoretical_output_dir),
                    str(metadata.output_dir),
                )
            else:
                # compute number of levels to go up
                levels = len(rel_theoretical_output_dir.parts) - 1
                metadata.global_config.base_output_dir = metadata.output_dir.parents[levels]

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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.log_handlers: List[logging.Handler] = []

    def __repr__(self):
        if self.metadata.experiment_id is not None:
            return f"{self.__class__.__name__} (id: {self.experiment_id}, status: {self.status})"
        else:
            return f"{self.__class__.__name__} (status: {self.status})"

    @property
    def log_path(self):
        return self.output_dir / self.global_config.logging.filename

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
        assert self.status == "pending", f"{self.__class__.__name__} has already been started."
        self.metadata.start_time = datetime.now()
        self.metadata.status = "running"
        self.create_output_dir()
        self.save_metadata()
        self.save_annotations()
        self.setup_log()

    def end(self, status: str = "undecided"):
        """End the execution of an experiment.

        Write metadata, close logs, etc.
        """
        self.metadata.end_time = datetime.now()
        self.metadata.status = status
        self.save_metadata()
        self.save_annotations()
        self.teardown_log()

    def create_unique_id(self):
        ideal_id = self.global_config.experiment_id_format.format(**self.metadata.__dict__)

        if not self.output_dir_from_id(ideal_id).exists():
            return ideal_id

        # enumerate experiments starting at 1 (as a first one already exists)
        for i in count(2):
            level = floor(log10(i) / 2) + 1
            real_id = ideal_id + "_" * level + str(i).zfill(2 * level)

            if not self.output_dir_from_id(real_id).exists():
                return real_id

    def create_output_dir(self):
        if self.metadata.output_dir is not None:
            assert self.output_dir.exists(), f"Output directory given ({self.output_dir}), but it does not exist."
            return self.output_dir

        if self.metadata.experiment_id is None:
            self.metadata.experiment_id = self.create_unique_id()

        self.metadata.output_dir = self.output_dir_from_id(self.experiment_id)
        self.output_dir.mkdir(parents=True)

        return self.output_dir

    def handle_exception(self, exc_type, exc_value, traceback):
        traceback_string = "".join(format_exception(exc_type, value=exc_value, tb=traceback))

        logger.exception("", exc_info=(exc_type, exc_value, traceback))
        self.metadata.additional_info["exception"] = {"short": repr(exc_value), "traceback": traceback_string}

    def __enter__(self):
        self.start()
        logger.info("%s '%s' started.", self.__class__.__name__, self.experiment_id)

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            logger.info("%s '%s' completed.", self.__class__.__name__, self.experiment_id)
            self.end(status="complete")
        elif issubclass(exc_type, KeyboardInterrupt):
            logger.warning("%s '%s' aborted.", self.__class__.__name__, self.experiment_id)
            self.end(status="aborted")
            return False
        else:
            self.handle_exception(exc_type, exc_value, traceback)
            logger.warning("%s '%s' failed.", self.__class__.__name__, self.experiment_id)
            self.end(status="failed")
            return False

    def synchronize(self):
        """Synchronize to existing output directory."""

        if self.metadata.output_dir is None:
            assert (
                self.metadata.experiment_id is not None
            ), f"Cannot synchronize a {self.__class__.__name__} which has no `experiment_id` or `output_dir`."

            self.metadata.output_dir = self.output_dir_from_id(self.experiment_id)

        if self.metadata.output_dir.exists():
            self.metadata = self.load_metadata(self.metadata.output_dir)

            self.load_annotations()
        else:
            logger.warning("No metadata found. Skipping synchronization.")

        return self

    @classmethod
    def from_path(cls, path: PathLike, config_cls: Optional[Type] = None):
        metadata: Metadata = cls.load_metadata(path)

        experiment: Experiment
        if not metadata.is_series:
            if config_cls is not None:
                metadata.configuration = from_dict(config_cls, metadata.configuration)

            experiment = Trial(metadata)

        else:
            if config_cls is not None:
                metadata.configuration["base_config"] = from_dict(config_cls, metadata.configuration["base_config"])

            experiment = Series(metadata)

        experiment.load_annotations()

        return experiment

    @classmethod
    def all_from_path(
        cls,
        results_path: Union[str, PathLike],
    ) -> List["Experiment"]:
        """Load all experiments from the results_path."""
        results_path = Path(results_path)

        seen_dirs: Set[Path] = set()
        experiments = []

        for p in results_path.rglob("*/cordage.json"):
            path = p.parent

            if path.parent in seen_dirs:
                # we already encountered a parent experiment (series)
                continue

            seen_dirs.add(path)

            try:
                experiments.append(cls.from_path(p.parent))
            except JSONDecodeError as exc:
                logger.warning("Couldn't load '%s': %s", str(path), str(exc))

        return list(sorted(experiments, key=lambda exp: exp.output_dir))

    def setup_log(self):
        logger = logging.getLogger()

        if not self.global_config.logging.use:
            return

        # in this case, a StreamHandler was set up by the series
        is_toplevel = self.parent_id is None

        handler: logging.Handler

        logger.info("%s is%s toplevel: parent_id=%s", repr(self), "" if is_toplevel else " not", str(self.parent_id))

        if self.global_config.logging.to_stream and is_toplevel:
            # add colored stream handler
            format_str = "%(name)s:%(filename)s:%(lineno)d - %(message)s"

            if colorlog is not None:
                handler = colorlog.StreamHandler()
                handler.setFormatter(colorlog.ColoredFormatter(f"%(log_color)s%(levelname)-8s%(reset)s {format_str}"))
            else:
                handler = logging.StreamHandler()
                handler.setFormatter(colorlog.ColoredFormatter(f"%(levelname)-8s {format_str}"))

            logger.addHandler(handler)
            self.log_handlers.append(handler)

        if self.global_config.logging.to_file:
            # setup logging to local output_dir
            formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s:%(filename)s:%(lineno)d - %(message)s")
            handler = logging.FileHandler(self.log_path)
            handler.setFormatter(formatter)

            logger.addHandler(handler)
            self.log_handlers.append(handler)

    def teardown_log(self):
        logger = colorlog.getLogger()

        for handler in self.log_handlers:
            handler.close()
            logger.removeHandler(handler)


class Trial(Generic[T], Experiment):
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        config: Optional[T] = None,
        **kw,
    ):
        if metadata is not None:
            assert len(kw) == 0 and config is None
            super().__init__(metadata)
        else:
            super().__init__(configuration=config, **kw)

    @property
    def config(self):
        return self.metadata.configuration


class Series(Generic[T], Experiment):
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        base_config: Optional[T] = None,
        series_spec: Union[List[Dict], Dict[str, List], None] = None,
        series_skip: Optional[int] = None,
        **kw,
    ):
        if metadata is not None:
            assert len(kw) == 0 and base_config is None and series_spec is None
            super().__init__(metadata)
        else:
            if isinstance(series_spec, list):
                series_spec = [nest_items(flattened_items(trial_update, sep=".")) for trial_update in series_spec]

            super().__init__(
                configuration={"base_config": base_config, "series_spec": series_spec, "series_skip": series_skip}, **kw
            )

        self.validate_series_spec()

        self.trials: Optional[List[Trial[T]]] = None
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
    def base_config(self) -> T:
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

    def get_changing_fields(self):
        keys = set()

        if isinstance(self.series_spec, list):
            for trial_update in self.series_spec:
                for k, _ in flattened_items(trial_update):
                    keys.add(k)

        elif isinstance(self.series_spec, dict):
            for k, _ in flattened_items(self.series_spec):
                keys.add(k)

        return keys

    def get_trial_updates(self) -> Generator[Dict, None, None]:
        if isinstance(self.series_spec, list):
            for trial_update in self.series_spec:
                yield trial_update
        elif isinstance(self.series_spec, dict):
            keys, values = zip(*flattened_items(self.series_spec))

            keys = [".".join(k) for k in keys]

            for update_values in product(*values):
                yield nest_items(zip(keys, update_values))
        else:
            yield {}

    def __len__(self):
        if isinstance(self.series_spec, list):
            assert self.trials is None or len(self.trials) == len(
                self.series_spec
            ), f"Number of existing ({len(self.trials)}) and expected trials ({len(self.series_spec)}) do not match."
            return len(self.series_spec)
        elif isinstance(self.series_spec, dict):
            num_trials = 1
            for _, values in flattened_items(self.series_spec):
                num_trials *= len(values)
            assert (
                self.trials is None or len(self.trials) == num_trials
            ), f"Number of existing ({len(self.trials)}) and expected trials ({num_trials}) do not match."
            return num_trials
        else:
            return 1

    def make_trial(self, **kw):
        additional_info = kw.pop("additional_info", None)

        fields_to_update: Dict[str, Any] = {
            "experiment_id": None,
            "output_dir": None,
            "configuration": {},
            "additional_info": {},
            "status": "pending",
            "parent_id": None,
            **kw,
        }

        trial_metadata = self.metadata.replace(**fields_to_update)

        if additional_info is not None:
            assert isinstance(additional_info, dict)
            trial_metadata.additional_info.update(additional_info)

        return Trial(trial_metadata)

    def make_all_trials(self):
        if self.series_spec is None:
            # single trial experiment
            logger.debug("Configuration yields a single experiment.")
            single_trial = self.make_trial(configuration=self.base_config)
            single_trial.annotations = self.annotations
            self.trials = [single_trial]

        else:
            logger.debug("The given configuration yields an experiment series with %d experiments.", len(self))
            self.trials = []

            for i, trial_update in enumerate(self.get_trial_updates()):
                trial_config_data: Dict[str, Any]

                if isinstance(self.base_config, dict):
                    trial_config_data = deepcopy(self.base_config)
                else:
                    trial_config_data = to_dict(self.base_config)

                logger.debug("Base configuration: %s", str(trial_config_data))
                logger.debug("Trial update: %s", str(trial_update))

                nested_update(trial_config_data, trial_update)

                trial_config: T
                if isinstance(self.base_config, dict):
                    trial_config = cast(T, trial_config_data)
                else:
                    trial_config = cast(T, from_dict(type(self.base_config), trial_config_data))

                if i < self.series_skip:
                    status = "skipped"
                else:
                    status = "pending"

                trial = self.make_trial(configuration=trial_config, additional_info={"trial_index": i}, status=status)
                self.trials.append(trial)

    def __iter__(self):
        return self.get_all_trials(include_skipped=False)

    def get_all_trials(self, include_skipped: bool = False) -> Generator[Trial[T], None, None]:
        assert self.trials is not None

        if not self.is_singular:
            skip = 0 if include_skipped else self.series_skip

            for i, trial in enumerate(self.trials[skip:], start=skip):
                trial_subdir = str(i + 1).zfill(ceil(log10(len(self))))

                trial.metadata.parent_id = self.experiment_id
                trial.metadata.experiment_id = f"{self.experiment_id}/{trial_subdir}"

                yield trial
        else:
            assert len(self.trials) == 1
            yield self.trials[0]
