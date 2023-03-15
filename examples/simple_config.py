from dataclasses import dataclass
from pathlib import Path

import cordage


@dataclass
class Config:
    lr: float = 5e-5
    name: str = "MNIST"


def train(config: Config, output_dir: Path):
    """Help text which will be shown."""

    print(output_dir)
    print(config)


if __name__ == "__main__":
    cordage.run(train)
