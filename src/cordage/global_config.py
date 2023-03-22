from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


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

    experiment_id_format: str = "{start_time:%Y-%m-%d_%H-%M-%S}"
    output_dir_format: str = "{start_time:%Y-%m}/{experiment_id}"

    series_spec_key = "__series__"

    param_names: ParameterNameConfig = ParameterNameConfig()

    file_tree: FileTreeConfig = FileTreeConfig()

    central_metadata: CentralMetadataConfig = CentralMetadataConfig()

    def __post_init__(self):
        super().__init__()

        self.validate_format_strings()

    def validate_format_strings(self):
        # check the format strings
        dummy_metadata: Dict[str, Any] = dict(start_time=datetime.now())
        self.experiment_id_format.format(**dummy_metadata)

        dummy_metadata["experiment_id"] = "experiment_id"
        self.output_dir_format.format(**dummy_metadata)
