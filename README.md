# Cordage: Computational Research Data Management

![Cordage Icon](icon.svg)


This is project is in a very early stage. It currently lacks a lot of documentation, proper testing, and a wide range
of features. If you think it could be useful for you, try it out and leave suggestions, complains, ideas for
improvements as github issues.


# Getting Started
## Installation

```bash
pip install git+https://github.com/plonerma/cordage.git
```

## Usage

To use cordage, you need a main function (e.g. `func`) which takes a dataclass configuration object as an argument.
Use `cordage.run(func)` to execute this function with arguments passed via the command line. Cordage pareses the
configuration and creates an output directory (if the function accepts `output_dir`, it will be passed as such).

See the examples in the examples directory for more details.
