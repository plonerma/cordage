<div align="center">

# Cordage: *Co*mputational *R*esearch *D*ata Man*age*ment
   
*Parameterize experiments using dataclasses and use cordage to easily parse configuration files and command line
options.*

---

[![Build status](https://img.shields.io/github/actions/workflow/status/plonerma/cordage/tests.yml?logo=github&label=Tests)](https://github.com/plonerma/cordage/actions)
[![PyPI - Version](https://img.shields.io/pypi/v/cordage.svg?logo=pypi&label=Version&logoColor=gold)](https://pypi.org/project/cordage/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cordage.svg?logo=python&label=Python&logoColor=gold)](https://pypi.org/project/cordage/)
[![PyPI - License](https://img.shields.io/pypi/l/cordage?logo=pypi&logoColor=gold)](https://github.com/plonerma/cordage/blob/main/LICENSE)

    
![Cordage Icon](https://raw.githubusercontent.com/plonerma/cordage/main/docs/assets/icon.svg)

[Repository](https://github.com/plonerma/cordage) | [Documentation](https://plonerma.github.io/cordage/) | [Package](https://pypi.org/project/cordage/)

</div>

---

*Cordage is in a **very early stage**. Currently, it lacks a lot of documentation and wider range
of features. If you think it could be useful for you, try it out and leave suggestions, complains, and improvemnt ideas
as [github issues](https://github.com/plonerma/cordage/issues).*

*Check out the [roadmap](https://github.com/plonerma/cordage/wiki/Roadmap) for an outline of the next steps that are planned for the development of this package.*

---


## Motivation

In many cases, we want to execute and parameterize a main function.
Since experiments can quickly become more complex and may use an increasing number of parameters,
it often makes sense to store these parameters in a `dataclass`.

Cordage makes it easy to load configuration files or configure the experiment via the commandline.


## Quick Start

For more detailed information, check out the [documentation](https://plonerma.github.io/cordage/).

### Installation

In an environment of your choice (python>=3.8), run:

```bash
pip install cordage
```

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


## Features

The main purpose of cordage is to manage configurations to make configuring reproducible experiments easy.
Cordage automatically generates a commandline interface which can be used to parse configuration files and/or
set specific configuration fields via CLI options (run the experiment with the `--help option` to get an overview
over the available configuration fields).

By using the `__series__` key, it is possible ot invoke multiple repetitions of an experiment using the same
base configuration but varying some of the configuration fields. The resulting trial runs are (by default) 
saved in a common series-level directory.

Additionally, cordage can provide an output directory (via the `output_dir`) where cordage will store the used configuration
as well as some experimental metadata.
