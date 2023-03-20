from pathlib import Path

import pytest

from cordage import GlobalConfig
from cordage.configuration import from_dict as config_from_dict


@pytest.fixture
def global_config(tmp_path: Path) -> GlobalConfig:
    return config_from_dict(
        GlobalConfig,
        {
            "central_metadata.path": tmp_path / "cordage_store",
            "base_output_dir": tmp_path / "results",
        },
    )
