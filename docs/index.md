# Getting Started


## Installation

In your desired environment run:

``` shell
pip install cordage
```


## Usage Example

The following code illustrates how to set up a cordage CLI.

``` python title="example.py"
from dataclasses import dataclass
import cordage


@dataclass
class Config:
    lr: float = 5e-5
    name: str = "MNIST"


def train(config: Config):
    """Help text which will be shown."""
    print(config)


if __name__ == "__main__":
    cordage.run(train)
```

Using `--help` option now shows the available configuration options.

``` shell-session
$ python example.py --help

usage: example.py [-h] [config_file] <configuration options to overwrite>

Help text which will be shown.

positional arguments:
  config_file           Top-level config file to load (optional).

optional arguments:
  -h, --help            show this help message and exit
  --series-skip N       Skip first N trials in the execution of a series.
  --cordage-comment COMMENT
                        Add a comment to the annotation of this series.
  --output-dir PATH     Path to use as the output directory.

configuration:
  --lr LR
  --name NAME

```
