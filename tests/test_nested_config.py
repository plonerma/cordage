from dataclasses import dataclass, field

import pytest

import cordage


@dataclass
class DataConfig:
    """Description of the data config.

    :param name: Name of the dataset
    """

    name: str
    version: int


@dataclass
class HyperParameterConfig:
    learning_rate: float = 5e-5
    weight_decay: float = 0.0


@dataclass
class NestedConfig:
    data: DataConfig
    hyper_params: HyperParameterConfig = field(default_factory=HyperParameterConfig)


def test_nested_config(global_config):
    def func(config: NestedConfig):
        assert config == NestedConfig(
            data=DataConfig(name="mnist", version=1),
            hyper_params=HyperParameterConfig(learning_rate=2.0, weight_decay=0.0),
        )

    cordage.run(
        func,
        args=["--data.name", "mnist", "--data.version", "1", "--hyper_params.learning_rate", "2"],
        global_config=global_config,
    )


def test_nested_config_overwrite(global_config, resources_path):
    def func(config: NestedConfig):
        assert config == NestedConfig(
            data=DataConfig(name="mnist", version=1),
            hyper_params=HyperParameterConfig(learning_rate=2.0, weight_decay=0.0),
        )

    config_file = resources_path / "nested_c.json"

    cordage.run(
        func,
        args=[
            str(config_file),
            "--data.name",
            "mnist",
            "--data.version",
            "1",
            "--hyper_params.learning_rate",
            "2",
        ],
        global_config=global_config,
    )


def test_nested_loading(global_config, resources_path):
    def func(config: NestedConfig):
        assert config.data.name == "mnist"
        assert config.data.version == 1
        assert isinstance(config.hyper_params.learning_rate, float)
        assert config.hyper_params.learning_rate == 2.0
        assert config.hyper_params.weight_decay == 0.0

    config_file = resources_path / "nested_a.json"

    cordage.run(
        func,
        args=[str(config_file)],
        global_config=global_config,
    )


def test_mixed_nested_loading(global_config, resources_path):
    def func(config: NestedConfig):
        assert config.data.name == "mnist"
        assert config.data.version == 2
        assert isinstance(config.hyper_params.learning_rate, float)
        assert config.hyper_params.learning_rate == 2.0
        assert config.hyper_params.weight_decay == 0.0

    config_file = resources_path / "nested_b.yaml"

    cordage.run(
        func,
        args=[str(config_file), "--data.version", "2"],
        global_config=global_config,
    )


def test_additional_keys_exception(global_config, resources_path):
    def func(config: NestedConfig):
        pass

    with pytest.raises(cordage.exceptions.CordageError):
        cordage.run(
            func, args=[str(resources_path / "nested_add_key.json")], global_config=global_config
        )

    # with strict mode off, this should not raise an exception
    global_config.strict_mode = False
    cordage.run(
        func, args=[str(resources_path / "nested_add_key.json")], global_config=global_config
    )
