![Cordage Icon](icon.svg)


# Cordage: Computational Research Data Management


[![Build status](https://github.com/plonerma/cordage/actions/workflows/tests.yml/badge.svg)](https://github.com/plonerma/cordage/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

This is project is in a very early stage. It currently lacks a lot of documentation, proper testing, and a wide range
of features. If you think it could be useful for you, try it out and leave suggestions, complains, ideas for
improvements as github issues.


## Quick Start
### Installation

In your environment of choice, run:

```bash
pip install git+https://github.com/plonerma/cordage.git
```

Cordage requires python>=3.8.

### Usage

In many cases, we want to execute and parameterize a main function.
Since experiments can quickly become more complex and may use an increasing number of parameters,
it often makes sense to store these parameters in a `dataclass`.

Cordage makes it easy to load configuration files or configure the experiment via the commandline.

#### Example

```python
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


To use cordage, you need a main function (e.g. `func`) which takes a dataclass configuration object as an argument.
Use `cordage.run(func)` to execute this function with arguments passed via the command line. Cordage parses the
configuration and creates an output directory (if the function accepts `output_dir`, it will be passed as such).

See the examples in the examples directory for more details.
