import logging
import shutil
from collections.abc import Generator, Iterable
from copy import deepcopy
from datetime import datetime, timezone
from itertools import chain, count, product
from json.decoder import JSONDecodeError
from math import floor, log10
from os import PathLike, getpid
from pathlib import Path
from traceback import format_exception
from typing import (
    Any,
    Generic,
    Literal,
    Optional,
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

from cordage.metadata import Annotatable, Metadata, Status
from cordage.util import (
    TrialIndices,
    TrialIndicesEntry,
    config_output_dir_type,
    flattened_items,
    from_dict,
    logger,
    nest_items,
    nested_update,
)

if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance


ConfigClass = TypeVar("ConfigClass", bound="DataclassInstance")


class Experiment(Annotatable):
    def __init__(self, *args, config_cls: Optional[type] = None, **kwargs):
        super().__init__(*args, **kwargs)

        self.config_cls = config_cls
        self.log_handlers: list[logging.Handler] = []

    def __repr__(self):
        if self.metadata.output_dir is not None:
            return f"{self.__class__.__name__} ({self.output_dir}, status: {self.status})"
        else:
            return f"{self.__class__.__name__} (status: {self.status})"

    @property
    def log_path(self):
        return self.output_dir / self.global_config.logging_filename

    @property
    def status(self) -> Status:
        return self.metadata.status

    def has_status(self, *status: Status):
        return len(status) == 0 or self.status in status

    @property
    def result(self) -> Any:
        return self.metadata.result

    def start(self):
        """Start the execution of an experiment.

        Set start time, create output directory, registers run, etc.
        """
        assert self.config_cls is not None
        assert not self.status.has_started, f"{self.__class__.__name__} has already been started."
        self.metadata.start_time = datetime.now(timezone.utc).astimezone()
        self.metadata.status = Status.RUNNING
        self.metadata.additional_info["process_id"] = getpid()
        self.create_output_dir()
        self.save_metadata()
        self.save_annotations()
        self.setup_log()

    def end(self, status: Status):
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
            self.end(status=Status.COMPLETE)
        elif issubclass(exc_type, KeyboardInterrupt):
            logger.warning("%s '%s' aborted.", self.__class__.__name__, str(self.output_dir))
            self.end(status=Status.ABORTED)
            return False
        else:
            self.handle_exception(exc_type, exc_value, traceback)
            logger.warning("%s '%s' failed.", self.__class__.__name__, str(self.output_dir))
            self.end(status=Status.FAILED)
            return False

    def load_data(self):
        """Synchronize to existing output directory."""
        assert self.metadata.output_dir is not None, (
            f"Cannot synchronize a {self.__class__.__name__} which has no `output_dir`."
        )

        if self.metadata.output_dir.exists():
            metadata = self.load_metadata(self.metadata.output_dir)

            if not isinstance(self.metadata.configuration, dict):
                metadata.configuration = from_dict(
                    type(self.metadata.configuration), metadata.configuration
                )

            self.metadata = metadata

            self.load_annotations()
        else:
            logger.warning(
                "Experiment directory (%s) not found. Cannot load the data.",
                str(self.metadata.output_dir),
            )

        return self

    @classmethod
    def from_path(
        cls,
        path: PathLike,
        *,
        config_cls: Optional[type[ConfigClass]] = None,
        load_series_trials: bool = True,
    ):
        metadata: Metadata = cls.load_metadata(path)

        experiment: Experiment
        if not metadata.is_series:
            experiment = Trial(metadata, config_cls=config_cls)

        else:
            experiment = Series(metadata, config_cls=config_cls)
            if load_series_trials:
                for trial in experiment:
                    if trial.metadata.output_dir.exists():
                        trial.load_data()

        experiment.load_annotations()

        return experiment

    @classmethod
    def all_from_path(
        cls, results_path: Union[str, PathLike], *, skip_hidden: bool = True
    ) -> list["Experiment"]:
        """Load all experiments from the results_path."""
        results_path = Path(results_path)

        seen_dirs: set[Path] = set()
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

    def create_output_dir(self):
        if self.metadata.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.set_output_dir(self.output_dir)
            return self.output_dir

        tried_paths: set[Path] = set()
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


class Trial(Experiment, Generic[ConfigClass]):
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        config: Optional[dict[str, Any]] = None,
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
    trials: list[Trial[ConfigClass]]

    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        /,
        base_config: Optional[dict[str, Any]] = None,
        series_spec: Union[list[dict], dict[str, list], None] = None,
        trial_indices: Optional[TrialIndices] = None,
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
                    "trial_indices": trial_indices,
                },
                config_cls=config_cls,
                **kw,
            )

        self.validate_series_spec()
        self.make_all_trials()

    def validate_series_spec(self):
        assert (
            self.metadata.configuration.get("series_skip", None) is None
            or self.metadata.configuration.get("series_trial", None) is None
        ), "Only one of `series_skip` and`series_trial` should be used."

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
    def base_config(self) -> dict[str, Any]:
        return self.metadata.configuration["base_config"]

    @property
    def series_spec(self) -> Union[list[dict], dict[str, list], None]:
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
        for i, trial in enumerate(self.trials, start=1):
            if i <= self.series_skip:
                trial.metadata.status = Status.SKIPPED
            else:
                trial.metadata.status = Status.PENDING

        if not self.is_singular:
            super().__enter__()
        # else: do nothing

    def __exit__(self, *args):
        if not self.is_singular:
            super().__exit__(*args)
        # else: do nothing

    @overload
    def get_changing_fields(self, sep: Literal[None] = None) -> set[tuple[Any, ...]]: ...

    @overload
    def get_changing_fields(self, sep: str) -> set[str]: ...

    def get_changing_fields(
        self, sep: Optional[str] = None
    ) -> Union[set[tuple[Any, ...]], set[str]]:
        keys: set = set()

        if isinstance(self.series_spec, list):
            for trial_update in self.series_spec:
                for k, _ in flattened_items(trial_update, sep=sep):
                    keys.add(k)

        elif isinstance(self.series_spec, dict):
            for k, _ in flattened_items(self.series_spec, sep=sep):
                keys.add(k)

        return keys

    def get_trial_updates(self) -> Generator[dict, None, None]:
        if isinstance(self.series_spec, list):
            yield from self.series_spec
        elif isinstance(self.series_spec, dict):
            keys, values = zip(*flattened_items(self.series_spec, sep="."))

            for update_values in product(*values):
                yield nest_items(zip(keys, update_values))
        else:
            yield {}

    def _derive_len(self) -> int:
        if isinstance(self.series_spec, list):
            return len(self.series_spec)
        elif isinstance(self.series_spec, dict):
            num_trials = 1
            for _, values in flattened_items(self.series_spec):
                num_trials *= len(values)
            return num_trials
        else:
            return 1

    def __len__(self) -> int:
        if len(self.trials) != self._derive_len():
            msg = (
                f"Number of existing ({len(self.trials)}) and expected trials "
                f"({self._derive_len()}) do not match."
            )
            raise RuntimeError(msg)

        return len(self.trials)

    def make_trial(self, **kw):
        additional_info = kw.pop("additional_info", None)

        fields_to_update: dict[str, Any] = {
            "output_dir": None,
            "configuration": {},
            "additional_info": {},
            "status": Status.UNKOWN,
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
                self._derive_len(),
            )
            self.trials = []

            for i, trial_update in enumerate(self.get_trial_updates(), start=1):
                trial_configuration: dict[str, Any] = deepcopy(self.base_config)

                nested_update(trial_configuration, trial_update)

                trial = self.make_trial(
                    configuration=trial_configuration,
                    additional_info={"trial_index": i},
                )
                self.trials.append(trial)

    def __iter__(self):
        return self.get_all_trials(include_skipped=False)

    def get_effective_indices(self, *, include_skipped=False) -> list[int]:
        if include_skipped:
            return list(range(1, len(self) + 1))

        entries: Optional[TrialIndices] = self.metadata.configuration.get("trial_indices", None)

        if not entries:
            return list(range(1, len(self) + 1))

        indices: list[Union[Iterable[int]]] = []

        entry: TrialIndicesEntry
        for entry in entries:
            if isinstance(entry, int):
                indices.append([entry])
            else:
                start, end = entry

                if start is None:
                    # Indices start at 1
                    start = 1

                if end is not None:
                    # Ranges are inclusive
                    end += 1

                indices.append(range(*slice(start, end).indices(len(self) + 1)))

        # Deduplicate (maintaining the insertion order)
        return list(dict.fromkeys(chain.from_iterable(indices)))

    def get_all_trials(
        self, *, include_skipped: bool = False
    ) -> Generator[Trial[ConfigClass], None, None]:
        assert self.trials is not None

        if not self.is_singular:
            for i in self.get_effective_indices(include_skipped=include_skipped):
                trial = self.trials[i - 1]
                if self.global_config.zero_pad_trial_output_dir:
                    trial_subdir = str(i).zfill(floor(log10(len(self))) + 1)
                else:
                    trial_subdir = str(i)
                trial.metadata.output_dir = self.output_dir / trial_subdir
                yield trial

        else:
            assert len(self.trials) == 1
            yield self.trials[0]
