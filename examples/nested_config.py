from dataclasses import dataclass, field

import cordage


@dataclass
class TrainConfig:
    lr: float = 5e-5


@dataclass
class DataConfig:
    name: str = "MNIST"


@dataclass
class Config:
    data: DataConfig
    training: TrainConfig = field(default_factory=TrainConfig)


def train(config: Config):
    # to something
    print(config)  # noqa: T201


if __name__ == "__main__":
    cordage.run(train)
