import dataclasses
import inspect
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Dict, Union

from docstring_parser import parse as parse_docstring

from .configuration import ConfigurationParser
from .experiment import Series, Trial
from .global_config import GlobalConfig
from .util import from_dict as config_from_dict
from .util import logger

USAGE_STR: str = "%(prog)s [-h] [config_file] <configuration options to overwrite>"
DEFAULT_CONFIG_PATH: Path = Path("~/.config/cordage.json")


def get_global_config(global_config: Union[PathLike, Dict, GlobalConfig, None]) -> GlobalConfig:
    if global_config is None:
        return GlobalConfig()
    elif isinstance(global_config, dict):
        return config_from_dict(GlobalConfig, global_config)
    elif isinstance(global_config, (str, Path)):
        return config_from_dict(GlobalConfig, {".": global_config})
    else:
        assert isinstance(global_config, GlobalConfig)
        return global_config


def run(
    func: Callable,
    args=None,
    description=None,
    config_cls=None,
    global_config: Union[PathLike, Dict, GlobalConfig, None] = DEFAULT_CONFIG_PATH,
) -> None:
    logger.debug("Loading global configuration.")
    try:
        global_config = get_global_config(global_config)
    except FileNotFoundError as exc:
        if global_config == DEFAULT_CONFIG_PATH and exc.filename == str(DEFAULT_CONFIG_PATH):
            logger.warning("Global configuration file (%s) not found. Using default values.", DEFAULT_CONFIG_PATH)
            global_config = GlobalConfig()
        else:
            raise

    func_parameters = inspect.signature(func).parameters

    # derive configuration class
    if config_cls is None:
        try:
            config_cls = func_parameters[global_config.param_names.config].annotation
        except KeyError as exc:
            raise TypeError(f"Callable must accept config in `{global_config.param_names.config}`.") from exc

    if not dataclasses.is_dataclass(config_cls):
        raise TypeError(
            f"Configuration class could not be derived: Either pass a configuration dataclass via `config_cls` or"
            f"annotate the configuration parameter `{global_config.param_names.config}` with a dataclass."
        )

    if description is None:
        if func.__doc__ is not None:
            description = parse_docstring(func.__doc__).short_description
        else:
            description = func.__name__

    logger.debug("Parsing configuration")

    config_parser = ConfigurationParser(global_config, config_cls, description=description, usage=USAGE_STR)

    series: Series = config_parser.parse_all(args)

    logger.debug("%d experiments found in configuration", len(series))

    with series.run():
        trial: Trial
        for trial in series:
            logger.debug("Running trial")

            # execute function with the constructed keyword arguments
            with trial.run():
                logger.debug("Started execution")

                # construct arguments for the passed callable
                func_kw: Dict[str, Any] = {}

                # check if any other parameters are expected which can be resolved
                for name, param in func_parameters.items():
                    assert (
                        param.kind != param.POSITIONAL_ONLY
                    ), "Cordage currently does not support positional only parameters."

                    if name == global_config.param_names.config:
                        # pass the configuration
                        func_kw[name] = trial.config

                    elif name == global_config.param_names.output_dir:
                        # pass path to output directory
                        if issubclass(param.annotation, str):
                            func_kw[name] = str(trial.output_dir)
                        else:
                            func_kw[name] = trial.output_dir

                    elif name == global_config.param_names.trial_object:
                        # pass trial object
                        func_kw[name] = trial

                func(**func_kw)
