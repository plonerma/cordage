from dataclasses import dataclass
from pathlib import Path

import pytest
from config_classes import NestedConfig
from config_classes import SimpleConfig as Config

import cordage
from cordage.util import from_file, get_nested_field, set_nested_field, to_file


@pytest.mark.parametrize("extension", ["toml", "yaml", "yml", "yl", "json"])
def test_different_extensions(tmp_path, extension):
    config_data = {"a": 10, "b": "20"}
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


def test_value_casting(tmp_path):
    @dataclass
    class ComplexConfig:
        data: dict

    config = ComplexConfig({"p": Path("."), "i": 42, "pi": 3.14})

    path = tmp_path / "data.json"

    to_file(config, path)

    loaded = from_file(ComplexConfig, path)

    assert loaded.data["p"] == "."
    assert loaded.data["i"] == 42
    assert loaded.data["pi"] == 3.14


def test_nested_value_retrieval(global_config):
    def func(config: NestedConfig):
        assert get_nested_field(config, "alpha.a") == 42

        set_nested_field(config, "alpha.a", 123)

        assert get_nested_field(config, "alpha.a") == 123

    cordage.run(func, ["--alpha.a", "42", "--beta.a", "c_value"], global_config=global_config)
