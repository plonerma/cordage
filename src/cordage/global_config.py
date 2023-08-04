from dataclasses import dataclass, field
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import Dict, Union

from .util import from_dict as config_from_dict
from .util import from_file as config_from_file
from .util import logger


@dataclass
class ParameterNameConfig:
    """Determines the names of the parameters in the function to be called by cordage."""

    config: str = "config"
    output_dir: str = "output_dir"
    trial_object: str = "cordage_trial"


@dataclass
class LoggingConfig:
    use: bool = True
    to_stream: bool = True
    to_file: bool = True
    filename: str = "cordage.log"


@dataclass
class GlobalConfig:
    """Holds the configuration for cordage."""

    PROJECT_SPECIFIC_CONFIG_PATH = Path("./cordage_configuration.json")
    GLOBAL_CONFIG_PATH: Path = Path("~/.config/cordage.json")

    base_output_dir: Path = Path("results")

    output_dir_format: str = "{start_time:%Y-%m}/{start_time:%Y-%m-%d_%H-%M-%S}{collision_suffix}"

    overwrite_existing: bool = False

    _series_spec_key = "__series__"
    _series_skip_key = "__series-skip__"
    _experiment_comment_key = "__experiment-comment__"
    _output_dir_key = "__output-dir__"

    strict_mode: bool = True

    param_names: ParameterNameConfig = field(default_factory=ParameterNameConfig)

    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self):
        super().__init__()

        self.validate_format_strings()

    def validate_format_strings(self):
        # check the format strings
        self.output_dir_format.format(
            function="some_function",
            collision_suffix="_2",
            start_time=datetime.now(),
        )

    @classmethod
    def resolve(cls, global_config: Union[str, PathLike, Dict, "GlobalConfig", None]):
        # Dictionary: create configuration based on these values
        if isinstance(global_config, dict):
            logger.debug("Creating global from dictionary.")
            return config_from_dict(cls, global_config)

        # Path: load configuration file from this path
        elif isinstance(global_config, (str, Path)):
            global_config = Path(global_config)
            if not global_config.exists():
                raise FileNotFoundError(f"Given cordage configuration path ({global_config}) does not exist.")

            logger.debug("Loading global config from file (%s).", global_config)
            return config_from_file(cls, global_config)

        # GlobalConfig object
        elif isinstance(global_config, cls):
            return global_config

        # None: look for files
        elif global_config is None:
            # Go through config file order

            # 1. Check if a project specific configuration file exists
            if cls.PROJECT_SPECIFIC_CONFIG_PATH.exists():
                logger.debug("Loading project specific global config (%s).", cls.PROJECT_SPECIFIC_CONFIG_PATH)
                return config_from_file(cls, cls.PROJECT_SPECIFIC_CONFIG_PATH)

            # 2. Check if a global configuration file exists
            elif cls.GLOBAL_CONFIG_PATH.exists():
                logger.debug("Loading global config (%s).", cls.GLOBAL_CONFIG_PATH)
                return config_from_file(cls, cls.GLOBAL_CONFIG_PATH)

            # 3. Use the default values
            else:
                logger.info(
                    "No cordage configuration given. Using default values. Use a project specific (%s) or global"
                    "configuration (%s) to change the behavior.",
                    cls.PROJECT_SPECIFIC_CONFIG_PATH,
                    cls.GLOBAL_CONFIG_PATH,
                )
            return cls()
        else:
            raise TypeError("`global_config` must be one of str, PathLike, dict, cordage.GlobalConfig, None")
