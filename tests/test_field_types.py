from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

import pytest
from config_classes import LongConfig as Config

import cordage
import cordage.exceptions


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

    cordage.run(
        func, args=[str(config_file), "--c", "some_other_value"], global_config=global_config
    )


def test_literal_fields(global_config, resources_path):
    def func(config: Config):
        pass

    config_file = resources_path / "simple_b.json"

    with pytest.raises(cordage.exceptions.WrongTypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_tuple_length_fields(global_config, resources_path):
    def func(config: Config):
        pass

    config_file = resources_path / "simple_c.toml"

    with pytest.raises(cordage.exceptions.WrongTypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


@pytest.mark.skip(reason="dacite currently does not properly support mixed tuples")
def test_valid_mixed_tuple(global_config, resources_path):
    def func(config: Config):
        pass

    config_file = resources_path / "simple_d.json"

    cordage.run(func, args=[str(config_file)], global_config=global_config)


@pytest.mark.skip(reason="dacite currently does not properly support mixed tuples")
def test_invalid_mixed_tuple(global_config, resources_path):
    def func(config: Config):
        pass

    config_file = resources_path / "simple_e.toml"

    with pytest.raises(cordage.exceptions.WrongTypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_valid_optional(global_config, resources_path):
    def func(config: Config):
        pass

    config_file = resources_path / "simple_f.json"

    cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_non_init_field(global_config):
    @dataclass
    class NonInitConfig:
        a: int
        b: float = field(init=False)

        def __post_init__(self):
            self.b = float(self.a)

    def func(config: NonInitConfig):
        assert int(config.b) == config.a

    cordage.run(func, args=["--a", "2"], global_config=global_config)

    # Invoking the command with b should make the parser exit
    with pytest.raises(SystemExit):
        cordage.run(func, args=["--a", "2", "--b", "3"], global_config=global_config)


def test_non_init_union_field(global_config):
    @dataclass
    class NonInitConfig:
        a: int
        b: Union[float, int, None] = field(init=False)

        def __post_init__(self):
            if self.a > 4:
                self.b = float(self.a)
            elif self.a > 0:
                self.b = self.a
            else:
                self.b = None

    def func(config: NonInitConfig):
        if config.a > 4:
            assert isinstance(config.b, float)
        elif config.a <= 0:
            assert config.b is None

    cordage.run(func, args=["--a", "2"], global_config=global_config)
    cordage.run(func, args=["--a", "-1"], global_config=global_config)

    # Invoking the command with b should make the parser exit
    with pytest.raises(SystemExit):
        cordage.run(func, args=["--a", "2", "--b", "3"], global_config=global_config)


def test_non_init_field_series(global_config, resources_path):
    @dataclass
    class NonInitConfig:
        a: int = -1
        b: float = field(init=False)

        def __post_init__(self):
            self.b = float(self.a)

    def func(config: NonInitConfig):
        assert int(config.b) == config.a

    cordage.run(
        func,
        args=[
            str(resources_path / "series_simple.yaml"),
        ],
        global_config=global_config,
    )
