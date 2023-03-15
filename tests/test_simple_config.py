import sys
from dataclasses import dataclass, field

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
    :param c: wrong_help_text
    """

    a: int
    b: str = "test"
    c: int = field(default=1, metadata={"help": "correct_help_text"})
    d: Literal["a", "b", "c"] = "a"


def test_simple_config():
    def func(config: Config):
        """short_function_description

        long_description

        :param config: Configuration to use.
        """
        assert config.a == 1
        assert config.b == "test"

    cordage.run(func, args=["--a", "1"])


def test_help(capfd):
    def func(config: Config):
        """short_function_description

        long_description

        :param config: Configuration to use.
        """
        assert False, "This should not be executed."

    with pytest.raises(SystemExit):
        cordage.run(func, args=["--help"])

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
