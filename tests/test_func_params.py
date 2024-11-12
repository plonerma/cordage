from dataclasses import dataclass
from pathlib import Path

import cordage


@dataclass
class Config:
    """config_description.

    :param a: a_help_str
    :param d: wrong_help_text
    """

    a: int
    b: str


def test_simple_func(global_config):
    def func(config: Config):
        assert isinstance(config, Config)
        assert config.a == 1
        assert config.b == "test"

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_func_with_output_dir_path(global_config):
    def func(config: Config, output_dir: Path):
        assert config.a == 1
        assert config.b == "test"
        assert isinstance(output_dir, Path)
        assert output_dir.exists()

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_func_with_output_dir_str(global_config):
    def func(config: Config, output_dir: str):
        assert config.a == 1
        assert config.b == "test"
        assert isinstance(output_dir, str)

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_func_with_trial(global_config):
    def func(config: Config, cordage_trial):
        assert config.a == 1
        assert config.b == "test"
        assert isinstance(cordage_trial, cordage.Trial)

        assert str(cordage_trial.output_dir) in repr(cordage_trial)

        assert (
            cordage_trial.output_dir == cordage_trial.global_config.base_output_dir / "experiment"
        )

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_explicit_config_class(global_config):
    def func(config):
        pass

    cordage.run(
        func, args=["--a", "1", "--b", "test"], global_config=global_config, config_cls=Config
    )
