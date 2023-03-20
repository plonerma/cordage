import dataclasses
from pathlib import Path


@dataclasses.dataclass
class GlobalConfig:
    """Holds the configuration for cordage."""

    config_param_name: str = "config"
    output_dir_param_name: str = "output_dir"
    trial_object_param_name: str = "cordage_trial"

    trial_id_format: str = "{start_time:%Y-%m-%d_%H-%M-%S}"
    output_dir_format: str = "{start_time:%Y-%m}/{trial_id}"

    base_output_dir: Path = Path("results")

    use_central_metadata_store: bool = True
    central_metadata_store: Path = Path("~/.cordage")
