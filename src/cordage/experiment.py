import json
from contextlib import contextmanager
from datetime import datetime
from itertools import count, product
from math import ceil, floor, log10
from pathlib import Path
from traceback import format_exc
from typing import Any, Dict, Generator, Generic, List, TypeVar, Union

from .global_config import GlobalConfig
from .util import flatten_dict, from_dict, logger, nested_serialization, to_dict

T = TypeVar("T")


class Experiment:
    def __init__(self, **kw):
        self.metadata: Dict[str, Any] = {"status": "waiting", **kw}

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

    def start(self):
        """Start the execution of an experiment.

        Set start time, create output directory, registers run, etc.
        """
        self.metadata.update(start_time=datetime.now(), status="running")
        self.create_output_dir()
        self.save_metadata()

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

    def output_dir_from_id(self, experiment_id):
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

        # save metadata in output dir
        with open(self.metadata_path, "w", encoding="utf-8") as fp:
            json.dump(md_dict, fp)

        if self.global_config.central_metadata.use:
            # rel exeriment path
            central_md_path = self.central_metadata_path
            central_md_path.parent.mkdir(parents=True, exist_ok=True)

            with central_md_path.open("w", encoding="utf-8") as fp:
                json.dump(md_dict, fp)

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


class Trial(Generic[T], Experiment):
    @property
    def config(self):
        return self.metadata["config"]

    def end(self, *args, **kwargs):
        super().end(*args, **kwargs)

        self.save_file_tree()

    def save_file_tree(self):
        if self.global_config.central_metadata.use:
            with (self.central_metadata_path.parent / "files.json").open("w", encoding="utf-8") as fp:
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
    def __init__(self, series_spec: Union[List[Dict], Dict[str, List], None] = None, **kw):
        super().__init__(**kw)

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

    @property
    def base_config(self) -> GlobalConfig:
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
            return len(self.series_spec)
        elif isinstance(self.series_spec, dict):
            num_trials = 1
            for values in self.series_spec.values():
                num_trials *= len(values)
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

    def __iter__(self) -> Generator[Trial[T], None, None]:
        if self.series_spec is None:
            # single trial experiment
            logger.debug("Configuration yields a single experiment.")
            yield self.make_trial(config=self.base_config)
        else:
            logger.debug("The given configuration yields an experiment series with %d experiments.", len(self))
            for i, trial_update in enumerate(self.get_trial_updates()):
                conf_data: Dict[str, Any] = to_dict(self.base_config)

                conf_data = flatten_dict(conf_data)

                trial_config_data = flatten_dict(trial_update, conf_data)

                trial_config = from_dict(type(self.base_config), trial_config_data)

                trial_index = str(i + 1).zfill(ceil(log10(len(self))))

                experiment_id = f"{self.experiment_id}/{trial_index}"

                yield self.make_trial(config=trial_config, series_id=self.experiment_id, experiment_id=experiment_id)
