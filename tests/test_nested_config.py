from dataclasses import dataclass

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
    hyper_params: HyperParameterConfig


def test_nested_config(global_config):
    def func(config: NestedConfig):
        assert config.data.name == "mnist"
        assert config.data.version == 1
        assert isinstance(config.hyper_params.learning_rate, float)
        assert config.hyper_params.learning_rate == 2.0
        assert config.hyper_params.weight_decay == 0.0

    cordage.run(
        func,
        args=["--data.name", "mnist", "--data.version", "1", "--hyper_params.learning_rate", "2"],
        global_config=global_config,
    )
