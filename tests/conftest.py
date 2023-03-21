from pathlib import Path

import pytest

from cordage import GlobalConfig
from cordage.util import from_dict as config_from_dict


@pytest.fixture
def global_config(tmp_path: Path) -> GlobalConfig:
    return config_from_dict(
        GlobalConfig,
        {
            "experiment_id_format": "experiment",
            "output_dir_format": "{experiment_id}",
            "central_metadata.path": tmp_path / "cordage_store",
            "base_output_dir": tmp_path / "results",
        },
    )


@pytest.fixture(scope="module")
def resources_path():
    return Path(__file__).parent / "resources"
