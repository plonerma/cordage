from pathlib import Path

import pytest

import cordage


@pytest.fixture
def global_config(tmp_path: Path) -> cordage.GlobalConfig:
    return cordage.GlobalConfig(
        central_metadata_store=tmp_path / "cordage_store",
        base_output_dir=tmp_path / "results",
    )
