from pathlib import Path

import pytest

from cordage import GlobalConfig
from cordage.util import from_dict as config_from_dict


@pytest.fixture
def global_config(tmp_path: Path) -> GlobalConfig:
    return config_from_dict(
        GlobalConfig,
        {
            "output_dir_format": "experiment{collision_suffix}",
            "base_output_dir": tmp_path / "results",
            "catch_exception": False,
        },
    )


@pytest.fixture(scope="module")
def resources_path():
    return Path(__file__).parent / "resources"
