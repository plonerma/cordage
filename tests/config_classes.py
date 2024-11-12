from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, Tuple


@dataclass
class SimpleConfig:
    a: int = 42
    b: str = "test"


@dataclass
class AlphaConfig:
    a: int
    b: str = "b_value"


@dataclass
class BetaConfig:
    a: str
    b: int = 0


@dataclass
class NestedConfig:
    """config_description.

    :param a: a_help_str
    :param d: wrong_help_text
    """

    alpha: AlphaConfig
    beta: BetaConfig = field(default_factory=lambda: BetaConfig(a="a_value"))

    a: str = "e_default"

    # these fields are used in test_more_trial_series for checking the
    # configuration and output dir etc.
    alphas: int = 1
    betas: int = 1


@dataclass
class LongConfig:
    """config_description.

    :param a: a_help_str
    :param d: wrong_help_text
    """

    a: int
    b: Path
    c: str = "test"
    d: int = field(default=1, metadata={"help": "correct_help_text"})
    e: Literal["a", "b", "c"] = "a"
    f: bool = False
    g: Optional[int] = None
    h: Tuple[str, ...] = ("a", "b")
    i: Tuple[str, str] = ("a", "b")
    j: Tuple[str, int, float] = ("a", 1, 1.0)
    k: Optional[int] = None
