import json
import re
from contextlib import contextmanager
from datetime import datetime
from itertools import count, product
from math import ceil, floor, log10
from os import PathLike
from pathlib import Path
from traceback import format_exc
from typing import Any, Container, Dict, Generator, Generic, Iterable, List, Optional, Set, TypeVar, Union, cast

from .global_config import GlobalConfig
from .util import flatten_dict, from_dict, logger, nested_serialization, to_dict, unflatten_dict

T = TypeVar("T")


class Experiment:
    TAG_PATTERN = re.compile(r"\B#(\w*[a-zA-Z]+\w*)")

    def __init__(self, **kw):
        self.metadata: Dict[str, Any] = {"status": "waiting", **kw}
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

    @property
    def comment(self):
        return self.annotations.get("comment", "")

    @comment.setter
    def comment(self, value):
        self.annotations["comment"] = value

    @property
    def global_config(self):
        return self.metadata["global_config"]

    @property
    def central_metadata_path(self):
        rel_path = self.output_dir.relative_to(self.global_config.base_output_dir)
        return self.global_config.central_metadata.path / rel_path / "metadata.json"

    @property
    def metadata_path(self):
        return self.output_dir / "cordage.json"

    @property
    def annotations_path(self):
        return self.output_dir / "annotations.json"

    @property
    def output_dir(self) -> Path:
        try:
            return self.metadata["output_dir"]
        except KeyError:
            raise RuntimeError(f"{self.__class__.__name__} has not been started yet.")

    @property
    def experiment_id(self):
        try:
            return self.metadata["experiment_id"]
        except KeyError:
            raise RuntimeError(f"{self.__class__.__name__} has not been started yet.")

    @property
    def status(self) -> str:
        return self.metadata["status"]

    @status.setter
    def status(self, value: str):
        self.metadata["status"] = value

    def start(self):
        """Start the execution of an experiment.

        Set start time, create output directory, registers run, etc.
        """
        assert self.status == "waiting", f"{self.__class__.__name__} has already been started."
        self.metadata.update(start_time=datetime.now(), status="running")
        self.create_output_dir()
        self.save_metadata()
        self.save_annotations()

    def end(self, status: str = "undecided"):
        """End the execution of an experiment.

        Write metadata, close logs, etc.
        """
        end_time = datetime.now()
        self.metadata.update(
            end_time=end_time,
            duration=end_time - self.metadata["start_time"],
            status=status,
        )
        self.save_metadata()
        self.save_annotations()

    def output_dir_from_id(self, experiment_id: str):
        metadata = {**self.metadata, "experiment_id": experiment_id}

        return self.global_config.base_output_dir / self.global_config.output_dir_format.format(**metadata)

    def create_unique_id(self):
        ideal_id = self.global_config.experiment_id_format.format(**self.metadata)

        if not self.output_dir_from_id(ideal_id).exists():
            return ideal_id

        # enumerate experiments starting at 1 (as a first one already exists)
        for i in count(2):
            level = floor(log10(i) / 2) + 1
            real_id = ideal_id + "_" * level + str(i).zfill(2 * level)

            if not self.output_dir_from_id(real_id).exists():
                return real_id

    def create_output_dir(self):
        if "output_dir" in self.metadata:
            return self.output_dir

        if "experiment_id" not in self.metadata:
            self.metadata["experiment_id"] = self.create_unique_id()

        self.metadata["output_dir"] = self.output_dir_from_id(self.experiment_id)
        self.output_dir.mkdir(parents=True)

        return self.output_dir

    def handle_exception(self, exc):
        self.metadata["exception"] = {"short": repr(exc), "traceback": format_exc()}

    def save_metadata(self):
        md_dict = nested_serialization(self.metadata)

        with open(self.metadata_path, "w", encoding="utf-8") as fp:
            json.dump(md_dict, fp)

        if self.global_config.central_metadata.use:
            self.central_metadata_path.parent.mkdir(parents=True, exist_ok=True)

            with self.central_metadata_path.open("w", encoding="utf-8") as fp:
                json.dump(md_dict, fp)

    def save_annotations(self):
        with open(self.annotations_path, "w", encoding="utf-8") as fp:
            json.dump(self.annotations, fp)

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

    @classmethod
    def from_path(cls, path: PathLike):
        path = Path(path)
        if not path.name == "cordage.json":
            path = path / "cordage.json"

        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)

        data["global_config"] = from_dict(GlobalConfig, flatten_dict(data["global_config"]))

        data["output_dir"] = Path(data["output_dir"])

        if data["output_dir"] != path.parent:
            logger.warning(
                f"Output dir is not correct anymore. Changing it to the actual directory"
                f"({data['output_dir']} -> {path.parent})"
            )
            data["output_dir"] = path.parent

        experiment: Experiment

        if "series_spec" not in data:
            experiment = Trial(**data)
        else:
            experiment = Series(**data)

        annotations_path: Path = experiment.output_dir / "annotations.json"
        if annotations_path.exists():
            with annotations_path.open("r", encoding="utf-8") as fp:
                experiment.annotations = json.load(fp)

        return experiment

    def has_tag(self, tag: Union[Container[str], str, None] = None):
        if tag is None:
            return True
        elif isinstance(tag, str):
            return tag in self.tags
        else:
            return any(t in tag for t in self.tags)

    def has_status(self, status: Union[Container[str], str, None] = None):
        if status is None:
            return True
        elif isinstance(status, str):
            return self.status == status
        else:
            return self.status in status

    @classmethod
    def all_from_path(
        cls,
        results_path,
    ) -> List["Experiment"]:
        """Load all experiments from the results_path."""

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
        return self.metadata["config"]

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
    def __init__(self, base_config: T, series_spec: Union[List[Dict], Dict[str, List], None] = None, **kw):
        super().__init__(base_config=base_config, **kw)

        if isinstance(series_spec, list):
            for config_update in series_spec:
                assert isinstance(config_update, dict)

        elif isinstance(series_spec, dict):
            series_spec = flatten_dict(series_spec)

            for values in series_spec.values():
                assert isinstance(values, list)
        else:
            assert series_spec is None

        self.metadata["series_spec"] = series_spec

        self.trials: Optional[List[Trial[T]]] = None
        self.make_all_trials()

    @property
    def base_config(self) -> T:
        return self.metadata["base_config"]

    @property
    def series_spec(self) -> Union[List[Dict], Dict[str, List], None]:
        return self.metadata["series_spec"]

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
        trial_metadata = {
            k: v
            for k, v in self.metadata.items()
            if k not in ("series_spec", "base_config", "output_dir", "experiment_id")
        }

        trial_metadata.update(**kw)

        return Trial(**trial_metadata)

    def make_all_trials(self):
        if self.series_spec is None:
            # single trial experiment
            logger.debug("Configuration yields a single experiment.")
            self.metadata["is_series"] = False

            self.trials = [self.make_trial(config=self.base_config)]

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

                self.trials.append(self.make_trial(config=trial_config, trial_index=1))

            self.metadata["is_series"] = True
            self.metadata["num_trials"] = len(self.trials)

    def __iter__(self) -> Generator[Trial[T], None, None]:
        if self.series_spec is not None:
            assert self.trials is not None

            for i, trial in enumerate(self.trials):
                trial_index = str(i + 1).zfill(ceil(log10(len(self))))

                trial.metadata["series_id"] = self.experiment_id
                trial.metadata["experiment_id"] = f"{self.experiment_id}/{trial_index}"

                yield trial
        else:
            assert self.trials is not None
            yield self.trials[0]
