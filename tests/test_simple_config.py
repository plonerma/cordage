import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

import pytest

import cordage


@dataclass
class Config:
    """config_description.

    :param a: a_help_str
    :param d: wrong_help_text
    """

    a: int
    b: Path
    c: str = "test"
    d: int = field(default=1, metadata={"help": "correct_help_text"})
    e: Literal["a", "b", "c"] = "a"


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


def test_config_loading(global_config, resources_path):
    def func(config: Config):
        assert config.a == 1
        assert isinstance(config.b, Path)
        assert config.c == "some_other_value"

    config_file = resources_path / "test_config_simple_a.json"

    cordage.run(func, args=[str(config_file), "--c", "some_other_value"], global_config=global_config)


def test_literal_fields(global_config, resources_path):
    def func(config: Config):
        pass

    config_file = resources_path / "test_config_simple_b.json"

    with pytest.raises(TypeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_help(capfd, global_config):
    def func(config: Config):
        """short_function_description

        long_description

        :param config: Configuration to use.
        """
        assert False, "This should not be executed."

    with pytest.raises(SystemExit):
        cordage.run(func, args=["--help"], global_config=global_config)

    out, err = capfd.readouterr()

    print(out)

    assert "a_help_str" in out
    assert "correct_help_text" in out
    assert "wrong_help_text" not in out
    assert ":param" not in out

    assert "short_function_description" in out
    assert "long_description" not in out
    assert "config_description" not in out

    first_line = out.split("\n")[0]

    assert "[config_file]" in first_line
    assert "<configuration options to overwrite>" in first_line
