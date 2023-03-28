import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from dataclasses import replace as dataclass_replace
from datetime import datetime
from itertools import count, product
from math import ceil, floor, log10
from os import PathLike
from pathlib import Path
from traceback import format_exc
from typing import Any, Dict, Generator, Generic, Iterable, List, Optional, Set, TypeVar, Union, cast

from .global_config import GlobalConfig
from .util import flatten_dict, from_dict, logger, nested_serialization, to_dict, unflatten_dict

T = TypeVar("T")


@dataclass
class Metadata:
    global_config: GlobalConfig
    output_dir: Optional[Path] = None
    experiment_id: Optional[str] = None
    status: str = "pending"

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    configuration: Any = None

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
    def global_config(self) -> GlobalConfig:
        return self.metadata.global_config

    @property
    def output_dir(self) -> Path:
        if self.metadata.output_dir is None:
            raise RuntimeError(f"{self.__class__.__name__} has not been started yet.")
        else:
            return self.metadata.output_dir

    @property
    def central_metadata_path(self):
        rel_path = self.output_dir.relative_to(self.global_config.base_output_dir)
        return self.global_config.central_metadata.path / rel_path / "metadata.json"

    @property
    def metadata_path(self):
        return self.output_dir / "cordage.json"

    def save_metadata(self):
        md_dict = nested_serialization(self.metadata)

        with open(self.metadata_path, "w", encoding="utf-8") as fp:
            json.dump(md_dict, fp)

        if self.global_config.central_metadata.use:
            self.central_metadata_path.parent.mkdir(parents=True, exist_ok=True)

            with self.central_metadata_path.open("w", encoding="utf-8") as fp:
                json.dump(md_dict, fp)

    @classmethod
    def load_metadata(cls, path: PathLike) -> Metadata:
        path = Path(path)
        if not path.suffix == ".json":
            path = path / "cordage.json"

        with path.open("r", encoding="utf-8") as fp:
            flat_data = flatten_dict(json.load(fp))
            metadata = from_dict(Metadata, flat_data)

        if metadata.output_dir != path.parent:
            logger.warning(
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
        return self.annotations.get("comment", "")

    @comment.setter
    def comment(self, value):
        self.annotations["comment"] = value

    @property
    def central_annotations_path(self):
        rel_path = self.output_dir.relative_to(self.global_config.base_output_dir)
        return self.global_config.central_metadata.path / rel_path / "annotations.json"

    @property
    def annotations_path(self):
        return self.output_dir / "annotations.json"

    def save_annotations(self):
        with open(self.annotations_path, "w", encoding="utf-8") as fp:
            json.dump(self.annotations, fp)

        if self.global_config.central_metadata.use and self.central_annotations_path.parent.exists():
            with open(self.central_annotations_path, "w", encoding="utf-8") as fp:
                json.dump(self.annotations, fp)

    def load_annotations(self):
        if self.annotations_path.exists():
            with self.annotations_path.open("r", encoding="utf-8") as fp:
                self.annotations = json.load(fp)


class Experiment(Annotatable):
    @property
    def experiment_id(self):
        if self.metadata.experiment_id is None:
            raise RuntimeError(f"{self.__class__.__name__} has not been started yet.")
        else:
            return self.metadata.experiment_id

    def __repr__(self):
        if self.metadata.experiment_id is not None:
            return f"{self.__class__.__name__} (id: {self.experiment_id}, status: {self.status})"
        else:
            return f"{self.__class__.__name__} (status: {self.status})"

    @property
    def status(self) -> str:
        return self.metadata.status

    @status.setter
    def status(self, value: str):
        self.metadata.status = value

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

    def end(self, status: str = "undecided"):
        """End the execution of an experiment.

        Write metadata, close logs, etc.
        """
        self.metadata.end_time = datetime.now()
        self.metadata.status = status
        self.save_metadata()
        self.save_annotations()

    def output_dir_from_id(self, experiment_id: str):
        metadata = {**self.metadata.__dict__, "experiment_id": experiment_id}

        return self.global_config.base_output_dir / self.global_config.output_dir_format.format(**metadata)

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

    def handle_exception(self, exc):
        self.metadata.additional_info["exception"] = {"short": repr(exc), "traceback": format_exc()}

    @contextmanager
    def run(self):
        try:
            self.start()
            logger.info("%s '%s' started.", self.__class__.__name__, self.experiment_id)
            yield self
            logger.info("%s '%s' completed.", self.__class__.__name__, self.experiment_id)
            self.end(status="complete")
        except KeyboardInterrupt:
            logger.warning("%s '%s' aborted.", self.__class__.__name__, self.experiment_id)
            self.end(status="aborted")
            raise
        except Exception as exc:
            self.handle_exception(exc)
            logger.warning("%s '%s' failed.", self.__class__.__name__, self.experiment_id)
            self.end(status="failed")
            raise

    def synchronize(self):
        """Synchronize to existing output directory."""

        if self.metadata.output_dir is None:
            assert (
                self.metadata.experiment_id is not None
            ), f"Cannot synchronize a {self.__class__.__name__} which has no `experiment_id` or `output_dir`."

            self.metadata.output_dir = self.output_dir_from_id(self.experiment_id)

        self.metadata = self.load_metadata(self.metadata.output_dir)

        self.load_annotations()

        return self

    @classmethod
    def from_path(cls, path: PathLike):
        metadata: Metadata = cls.load_metadata(path)

        experiment: Experiment
        if not metadata.is_series:
            experiment = Trial(metadata)
        else:
            experiment = Series(metadata)

        experiment.load_annotations()

        return experiment

    @classmethod
    def all_from_path(
        cls,
        results_path: PathLike,
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

            experiments.append(cls.from_path(p.parent))

        return list(sorted(experiments, key=lambda exp: exp.output_dir))


class Trial(Generic[T], Experiment):
    @property
    def config(self):
        return self.metadata.configuration

    def end(self, *args, **kwargs):
        super().end(*args, **kwargs)

        if self.global_config.central_metadata.use:
            self.save_file_tree(self.central_metadata_path.parent / "files.json")

    def save_file_tree(self, save_path):
        with save_path.open("w", encoding="utf-8") as fp:
            json.dump(self.produce_file_tree(self.output_dir), fp)

    def produce_file_tree(self, path, level=0):
        max_level = self.global_config.file_tree.max_level
        max_files = self.global_config.file_tree.max_files

        if path.is_dir():
            if level > self.global_config.file_tree.max_level:
                return f"Maximum depth of {max_level} exceeded."

            dir_dict = {}

            for i, p in enumerate(path.iterdir()):
                if i == max_files:
                    return f"Maximum number of files ({max_files}) exceeded."

                dir_dict[p.name] = self.produce_file_tree(p, level=level + 1)

            return dir_dict

        elif path.is_file():
            return path.stat().st_size
        else:
            return None


class Series(Generic[T], Experiment):
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        base_config: Optional[T] = None,
        series_spec: Union[List[Dict], Dict[str, List], None] = None,
        **kw,
    ):
        if metadata is not None:
            assert len(kw) == 0 and base_config is None and series_spec is None
            super().__init__(metadata)
        else:
            super().__init__(configuration={"base_config": base_config, "series_spec": series_spec}, **kw)

        self.validate_series_spec()

        self.trials: Optional[List[Trial[T]]] = None
        self.make_all_trials()

    def validate_series_spec(self):
        series_spec = self.series_spec

        if isinstance(series_spec, list):
            for config_update in series_spec:
                assert isinstance(config_update, dict)

        elif isinstance(series_spec, dict):
            series_spec = flatten_dict(series_spec)

            for values in series_spec.values():
                assert isinstance(values, list)
        else:
            assert series_spec is None

        self.metadata.configuration["series_spec"] = series_spec

    @property
    def base_config(self) -> T:
        return self.metadata.configuration["base_config"]

    @property
    def series_spec(self) -> Union[List[Dict], Dict[str, List], None]:
        return self.metadata.configuration["series_spec"]

    @property
    def is_singular(self):
        return self.series_spec is None

    @contextmanager
    def run(self):
        if self.is_singular:
            yield self
        else:
            with super().run():
                yield self

    def get_trial_updates(self) -> Generator[Dict, None, None]:
        if isinstance(self.series_spec, list):
            yield from self.series_spec
        elif isinstance(self.series_spec, dict):
            keys, values = zip(*self.series_spec.items())
            for update_values in product(*values):
                yield dict(zip(keys, update_values))
        else:
            yield {}

    def __len__(self):
        if isinstance(self.series_spec, list):
            assert self.trials is None or len(self.trials) == len(self.series_spec)
            return len(self.series_spec)
        elif isinstance(self.series_spec, dict):
            num_trials = 1
            for values in self.series_spec.values():
                num_trials *= len(values)
            assert self.trials is None or len(self.trials) == num_trials
            return num_trials
        else:
            return 1

    def make_trial(self, **kw):
        additional_info = kw.pop("additional_info", None)

        fields_to_update: Dict[str, Any] = {"experiment_id": None, "output_dir": None, "configuration": {}, **kw}

        trial_metadata = self.metadata.replace(**fields_to_update)

        if additional_info is not None:
            assert isinstance(additional_info, dict)
            trial_metadata.additional_info.update(additional_info)

        return Trial(trial_metadata)

    def make_all_trials(self):
        if self.series_spec is None:
            # single trial experiment
            logger.debug("Configuration yields a single experiment.")
            self.trials = [self.make_trial(configuration=self.base_config)]

        else:
            logger.debug("The given configuration yields an experiment series with %d experiments.", len(self))
            self.trials = []

            for i, trial_update in enumerate(self.get_trial_updates()):
                conf_data: Dict[str, Any]
                if isinstance(self.base_config, dict):
                    conf_data = self.base_config
                else:
                    conf_data = to_dict(self.base_config)

                conf_data = flatten_dict(conf_data)

                trial_config_data = flatten_dict(trial_update, conf_data)

                trial_config: T
                if isinstance(self.base_config, dict):
                    trial_config = cast(T, unflatten_dict(trial_config_data))
                else:
                    trial_config = cast(T, from_dict(type(self.base_config), trial_config_data))

                self.trials.append(self.make_trial(configuration=trial_config, additional_info={"trial_index": i}))

    def __iter__(self) -> Generator[Trial[T], None, None]:
        if self.series_spec is not None:
            assert self.trials is not None

            for i, trial in enumerate(self.trials):
                trial_subdir = str(i + 1).zfill(ceil(log10(len(self))))

                trial.metadata.additional_info["series_id"] = self.experiment_id
                trial.metadata.experiment_id = f"{self.experiment_id}/{trial_subdir}"

                yield trial
        else:
            assert self.trials is not None
            yield self.trials[0]
