import dataclasses

from pathlib import Path


@dataclasses.dataclass
class CordageConfig:
    """Holds the configuration for cordage."""

    config_param_name: str = "config"
    output_dir_param_name: str = "output_dir"
    trial_object_param_name: str = "cordage_trial"

    output_dir_format: str = "{start_time:%Y-%m/%Y-%m-%d_%H-%M-%S}"

    base_output_dir: Path = Path("results")
