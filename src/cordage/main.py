import dataclasses
import inspect
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union

from docstring_parser import parse as parse_docstring

from .config_parser import ConfigurationParser
from .experiment import Experiment, Series, Trial
from .global_config import GlobalConfig
from .util import from_dict as config_from_dict
from .util import logger

USAGE_STR: str = "%(prog)s [-h] [config_file] <configuration options to overwrite>"

PROJECT_SPECIFIC_CONFIG_PATH = Path("./cordage_configuration.json")
GLOBAL_CONFIG_PATH: Path = Path("~/.config/cordage.json")


class FunctionContext:
    """Wrapper for a function which accepts a dataclass configuration.

    This class can be used to:
    - parse argruments matching the config dataclass,
    - build a dictionary of the arguments expected by the function, and
    - call the function for each trial in a series.
    """

    global_config: GlobalConfig
    series: Series

    def __init__(
        self,
        func: Callable,
        description: Optional[str] = None,
        config_cls: Optional[Type] = None,
        global_config: Union[PathLike, Dict, GlobalConfig, None] = None,
    ):
        self.set_function(func)
        self.set_global_config(global_config)
        self.create_config_parser(description=description, config_cls=config_cls)

    def parse(self, args: Optional[List[str]]) -> Experiment:
        series: Series = self.config_parser.parse_all(args)
        logger.debug("%d experiments found in configuration", len(series))

        if series.is_singular:
            return next(iter(series))
        else:
            return series

    def create_config_parser(self, description: Optional[str], config_cls: Optional[Type]):
        # derive configuration class
        if config_cls is None:
            try:
                config_cls = self.func_parameters[self.global_config.param_names.config].annotation
            except KeyError as exc:
                raise TypeError(f"Callable must accept config in `{self.global_config.param_names.config}`.") from exc

        if not dataclasses.is_dataclass(config_cls):
            raise TypeError(
                f"Configuration class could not be derived: Either pass a configuration dataclass via `config_cls` or"
                f"annotate the configuration parameter `{self.global_config.param_names.config}` with a dataclass."
            )

        if description is None:
            if self.func.__doc__ is not None:
                description = parse_docstring(self.func.__doc__).short_description
            else:
                description = self.func.__name__

        logger.debug("Parsing configuration")

        self.config_parser = ConfigurationParser(
            self.global_config, config_cls, description=description, usage=USAGE_STR
        )

    @property
    def func(self) -> Callable:
        return self._func

    @property
    def func_parameters(self):
        return self._func_parameters

    def set_function(self, func: Callable):
        self._func = func
        self._func_parameters = inspect.signature(func).parameters

    def set_global_config(self, global_config: Union[PathLike, Dict, GlobalConfig, None]):
        logger.debug("Loading global configuration.")

        if isinstance(global_config, dict):
            # Dictionary given: create configuration based on these values
            self.global_config = config_from_dict(GlobalConfig, global_config)

        elif isinstance(global_config, (str, Path)):
            # Path given: load configuration file from this path
            global_config = Path(global_config)
            if not global_config.exists():
                raise FileNotFoundError(f"Given cordage configuration path ({global_config}) does not exist.")

            self.global_config = config_from_dict(GlobalConfig, {".": global_config})

        elif isinstance(global_config, GlobalConfig):
            self.global_config = global_config

        elif global_config is None:
            # Go through config file order

            # 1. Check if a project specific configuration file exists
            if PROJECT_SPECIFIC_CONFIG_PATH.exists():
                self.global_config = config_from_dict(GlobalConfig, {".": PROJECT_SPECIFIC_CONFIG_PATH})

            # 2. Check if a global configuration file exists
            elif GLOBAL_CONFIG_PATH.exists():
                self.global_config = config_from_dict(GlobalConfig, {".": GLOBAL_CONFIG_PATH})

            # 3. Use the default values
            else:
                logger.warning(
                    "No cordage configuration given. Using default values. Use a project specific (%s) or global"
                    "configuration (%s) to change the behavior.",
                    PROJECT_SPECIFIC_CONFIG_PATH,
                    GLOBAL_CONFIG_PATH,
                )
                self.global_config = GlobalConfig()
        else:
            raise TypeError("`global_config` must be one of PathLike, dict, cordage.GlobalConfig, None")

    def execute(self, experiment: Experiment):
        if isinstance(experiment, Trial):
            logger.debug("Running trial")

            # execute function with the constructed keyword arguments
            with experiment:
                logger.debug("Started execution")

                func_kw = self.construct_func_kwargs(experiment)

                experiment.result = self.func(**func_kw)
        elif isinstance(experiment, Series):
            with experiment:
                for trial in experiment:
                    self.execute(trial)
        else:
            raise TypeError("Passed object must be Trial or Series")

    def construct_func_kwargs(self, trial: Trial):
        # construct arguments for the passed callable
        func_kw: Dict[str, Any] = {}

        # check if any other parameters are expected which can be resolved
        for name, param in self.func_parameters.items():
            assert param.kind != param.POSITIONAL_ONLY, "Cordage currently does not support positional only parameters."

            if name == self.global_config.param_names.config:
                # pass the configuration
                func_kw[name] = trial.config

            elif name == self.global_config.param_names.output_dir:
                # pass path to output directory
                if issubclass(param.annotation, str):
                    func_kw[name] = str(trial.output_dir)
                else:
                    func_kw[name] = trial.output_dir

            elif name == self.global_config.param_names.trial_object:
                # pass trial object
                func_kw[name] = trial

        return func_kw


def run(
    func: Callable,
    args: Optional[List[str]] = None,
    description: Optional[str] = None,
    config_cls: Optional[Type] = None,
    global_config: Union[PathLike, Dict, GlobalConfig, None] = None,
) -> Experiment:
    context = FunctionContext(func, description=description, config_cls=config_cls, global_config=global_config)
    experiment = context.parse(args)
    context.execute(experiment)
    return experiment
