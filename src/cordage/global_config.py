from dataclasses import dataclass, field
from datetime import datetime
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Union

from .util import from_dict as config_from_dict
from .util import from_file as config_from_file
from .util import logger


@dataclass
class ParameterNameConfig:
    config: str = "config"
    output_dir: str = "output_dir"
    trial_object: str = "cordage_trial"


@dataclass
class FileTreeConfig:
    max_level: int = 3
    max_files: int = 1000


@dataclass
class LoggingConfig:
    use: bool = True
    to_stream: bool = True
    to_file: bool = True
    filename: str = "cordage.log"


@dataclass
class GlobalConfig:
    """Holds the configuration for cordage."""

    base_output_dir: Path = Path("results")

    experiment_id_format: str = "{start_time:%Y-%m-%d_%H-%M-%S}"
    output_dir_format: str = "{start_time:%Y-%m}/{experiment_id}"

    _series_spec_key = "__series__"
    _series_skip_key = "__series-skip__"
    _series_comment_key = "__series-comment__"

    strict_mode: bool = True

    param_names: ParameterNameConfig = field(default_factory=ParameterNameConfig)

    file_tree: FileTreeConfig = field(default_factory=FileTreeConfig)

    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def __post_init__(self):
        super().__init__()

        self.validate_format_strings()

    def validate_format_strings(self):
        # check the format strings
        dummy_metadata: Dict[str, Any] = dict(start_time=datetime.now())
        self.experiment_id_format.format(**dummy_metadata)

        dummy_metadata["experiment_id"] = "experiment_id"
        self.output_dir_format.format(**dummy_metadata)


PROJECT_SPECIFIC_CONFIG_PATH = Path("./cordage_configuration.json")
GLOBAL_CONFIG_PATH: Path = Path("~/.config/cordage.json")


def get_global_config(global_config: Union[str, PathLike, Dict, GlobalConfig, None]):
    if isinstance(global_config, dict):
        # Dictionary given: create configuration based on these values
        logger.debug("Creating global from dictionary.")
        return config_from_dict(GlobalConfig, global_config)

    elif isinstance(global_config, (str, Path)):
        # Path given: load configuration file from this path
        global_config = Path(global_config)
        if not global_config.exists():
            raise FileNotFoundError(f"Given cordage configuration path ({global_config}) does not exist.")

        logger.debug("Loading global config from file (%s).", global_config)
        return config_from_file(GlobalConfig, global_config)

    elif isinstance(global_config, GlobalConfig):
        return global_config

    elif global_config is None:
        # Go through config file order

        # 1. Check if a project specific configuration file exists
        if PROJECT_SPECIFIC_CONFIG_PATH.exists():
            logger.debug("Loading project specific global config (%s).", PROJECT_SPECIFIC_CONFIG_PATH)
            return config_from_file(GlobalConfig, PROJECT_SPECIFIC_CONFIG_PATH)

        # 2. Check if a global configuration file exists
        elif GLOBAL_CONFIG_PATH.exists():
            logger.debug("Loading global config (%s).", GLOBAL_CONFIG_PATH)
            return config_from_file(GlobalConfig, GLOBAL_CONFIG_PATH)

        # 3. Use the default values
        else:
            logger.warning(
                "No cordage configuration given. Using default values. Use a project specific (%s) or global"
                "configuration (%s) to change the behavior.",
                PROJECT_SPECIFIC_CONFIG_PATH,
                GLOBAL_CONFIG_PATH,
            )
            return GlobalConfig()
    else:
        raise TypeError("`global_config` must be one of str, PathLike, dict, cordage.GlobalConfig, None")
