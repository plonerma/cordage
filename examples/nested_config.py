from dataclasses import dataclass

import cordage


@dataclass
class TrainConfig:
    lr: float = 5e-5


@dataclass
class DataConfig:
    name: str = "MNIST"


@dataclass
class Config:
    training: TrainConfig
    data: DataConfig


def train(config: Config):
    # to something
    print(config)


if __name__ == "__main__":
    cordage.run(train)
