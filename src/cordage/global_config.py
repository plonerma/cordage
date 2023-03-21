from dataclasses import dataclass
from pathlib import Path


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
class CentralMetadataConfig:
    use: bool = True
    path: Path = Path("~/.cordage").expanduser()


@dataclass
class GlobalConfig:
    """Holds the configuration for cordage."""

    base_output_dir: Path = Path("results")

    trial_id_format: str = "{start_time:%Y-%m-%d_%H-%M-%S}"
    output_dir_format: str = "{start_time:%Y-%m}/{trial_id}"

    series_specification_key = "__series__"

    param_names: ParameterNameConfig = ParameterNameConfig()

    file_tree: FileTreeConfig = FileTreeConfig()

    central_metadata: CentralMetadataConfig = CentralMetadataConfig()
