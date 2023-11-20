from pathlib import Path

import pytest
from config_classes import LongConfig as Config

import cordage


def test_simple_config(global_config):
    def func(config: Config):
        """short_function_description

        long_description

        :param config: Configuration to use.
        """
        assert config.a == 1
        assert isinstance(config.b, Path)
        assert config.c == "test"

    cordage.run(func, args=["--a", "1", "--b", "~"], global_config=global_config)


def test_loading(global_config, resources_path):
    def func(config: Config):
        assert config.a == 1
        assert isinstance(config.b, Path)
        assert config.c == "some_other_value"

    config_file = resources_path / "simple_a.toml"

    cordage.run(func, args=[str(config_file), "--c", "some_other_value"], global_config=global_config)


def test_literal_fields(global_config, resources_path):
    def func(config: Config):  # noqa: ARG001
        pass

    config_file = resources_path / "simple_b.json"

    with pytest.raises(cordage.WrongTypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_tuple_length_fields(global_config, resources_path):
    def func(config: Config):  # noqa: ARG001
        pass

    config_file = resources_path / "simple_c.toml"

    with pytest.raises(cordage.WrongTypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


@pytest.mark.skip(reason="dacite currently does not properly support mixed tuples")
def test_valid_mixed_tuple(global_config, resources_path):
    def func(config: Config):  # noqa: ARG001
        pass

    config_file = resources_path / "simple_d.json"

    cordage.run(func, args=[str(config_file)], global_config=global_config)


@pytest.mark.skip(reason="dacite currently does not properly support mixed tuples")
def test_invalid_mixed_tuple(global_config, resources_path):
    def func(config: Config):  # noqa: ARG001
        pass

    config_file = resources_path / "simple_e.toml"

    with pytest.raises(cordage.WrongTypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_valid_optional(global_config, resources_path):
    def func(config: Config):  # noqa: ARG001
        pass

    config_file = resources_path / "simple_f.json"

    cordage.run(func, args=[str(config_file)], global_config=global_config)
