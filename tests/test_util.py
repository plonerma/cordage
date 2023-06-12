from dataclasses import dataclass

import pytest

from cordage.util import from_file, to_file


@dataclass
class Config:
    a: int = 1
    b: str = "2"


@pytest.mark.parametrize("extension", ["toml", "yaml", "yml", "yl", "json"])
def test_different_extensions(tmp_path, extension):
    config_data = dict(a=10, b="20")
    config = Config(a=10, b="20")

    path = tmp_path / f"data.{extension}"

    to_file(config_data, path)
    assert from_file(Config, path) == config

    to_file(config, path)
    assert from_file(Config, path) == config


def test_unkown_extensions(tmp_path):
    config = Config(a=10, b="20")

    path = tmp_path / "data.unkown"

    with pytest.raises(RuntimeError):
        to_file(config, path)

    with pytest.raises(RuntimeError):
        from_file(Config, path)
