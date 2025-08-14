from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import cordage


@dataclass
class ConfigWithoutOutputDir:
    a: int
    b: str


def test_func_with_output_dir_path(global_config):
    def func(config: ConfigWithoutOutputDir, output_dir: Path):
        assert config.a == 1
        assert config.b == "test"
        assert isinstance(output_dir, Path)
        assert output_dir.exists()

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_func_with_output_dir_str(global_config):
    def func(config: ConfigWithoutOutputDir, output_dir: str):
        assert config.a == 1
        assert config.b == "test"
        assert isinstance(output_dir, str)

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_config_with_output_dir_path(global_config):
    @dataclass
    class ConfigWithOutputDir:
        a: int
        b: str
        output_dir: Path

    def func(config: ConfigWithOutputDir):
        assert config.a == 1
        assert config.b == "test"
        assert str(config.output_dir) != "default"
        assert isinstance(config.output_dir, Path)
        assert config.output_dir.exists()

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_config_with_output_dir_str(global_config):
    @dataclass
    class ConfigWithOutputDir:
        a: int
        b: str
        output_dir: str

    def func(config: ConfigWithOutputDir):
        assert config.a == 1
        assert config.b == "test"
        assert config.output_dir != "default"
        assert isinstance(config.output_dir, str)
        assert Path(config.output_dir).exists()

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_config_and_func_with_output_dir(global_config):
    @dataclass
    class ConfigWithOutputDir:
        a: int
        b: str
        output_dir: str

    def func(config: ConfigWithOutputDir, output_dir: Path):
        assert config.a == 1
        assert config.b == "test"
        assert isinstance(config.output_dir, str)
        assert isinstance(output_dir, Path)
        assert str(output_dir) == str(config.output_dir)
        assert config.output_dir != "default"
        assert Path(config.output_dir).exists()
        assert output_dir.exists()

    cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_incorrect_output_dir_type(global_config):
    @dataclass
    class ConfigWithOutputDir:
        a: int
        b: str
        output_dir: int = 1

    def func(config: ConfigWithOutputDir):
        pass

    with pytest.raises(TypeError):
        cordage.run(func, args=["--a", "1", "--b", "test"], global_config=global_config)


def test_manual_output_dir(global_config):
    @dataclass
    class ConfigWithOutputDir:
        a: int
        b: str
        output_dir: str

    def func(config: ConfigWithOutputDir, output_dir: Path):
        assert isinstance(config.output_dir, str)
        assert isinstance(output_dir, Path)

        assert str(output_dir) == str(config.output_dir)
        assert output_dir.exists()

        assert output_dir == global_config.base_output_dir / "test_name"

    cordage.run(
        func,
        args=[
            "--a",
            "1",
            "--b",
            "test",
            "--output_dir",
            str(global_config.base_output_dir / "test_name"),
        ],
        global_config=global_config,
    )


@pytest.mark.parametrize("zero_pad", (True, False))
def test_zero_padding(global_config, zero_pad, resources_path):
    @dataclass
    class Config:
        a: int

    def func(config: Config, output_dir: Path):
        if not zero_pad:
            assert output_dir.parts[-1] == str(config.a)
        else:
            assert output_dir.parts[-1] == f"{config.a:02}"

    cordage.run(
        func,
        args=[
            str(resources_path / "series_simple10.yaml"),
        ],
        global_config=replace(global_config, zero_pad_trial_output_dir=zero_pad),
    )
