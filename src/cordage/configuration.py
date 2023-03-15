import sys
from typing import Any, Dict, Mapping, Optional, Type, TypeVar, cast, get_args, get_origin

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

import argparse
import dataclasses
from os import PathLike
from pathlib import Path

from docstring_parser import parse as parse_docstring

from .util import read_config_file, write_config_file

T = TypeVar("T")


class MissingType:
    def __repr__(self):
        return "<MISSING>"


MISSING = MissingType()


def add_arguments_to_parser(config_cls: Type[T], parser: argparse.ArgumentParser, prefix: Optional[str] = None):
    """Recursively (if nested) iterate over all fields in the dataclass and add arguments to parser."""

    assert dataclasses.is_dataclass(config_cls)

    # read documentation of config dataclass. If no help metadata is given, this will be used a the help text.
    param_doc = {}
    if config_cls.__doc__ is not None:
        # parse doc text, to generate help text for fields
        for param in parse_docstring(config_cls.__doc__).params:
            param_doc[param.arg_name] = param.description

    # Iterate over all fields in the dataclass to add arguments to the parser
    for field in dataclasses.fields(config_cls):
        # Set prefixed argument name
        if prefix is not None:
            arg_name = f"{prefix}.{field.name}"
        else:
            arg_name = field.name

        # Retrieve help text
        help_text = field.metadata.get("help", param_doc.get(field.name))

        # If the field is also a dataclass, recurse (nested config)
        if dataclasses.is_dataclass(field.type):
            add_arguments_to_parser(field.type, parser, prefix=arg_name)

            parser.add_argument(f"--{arg_name}", type=Path, help=help_text, default=MISSING)
        else:
            # Look the field annotation to determine which type of argument to add

            # Choice field
            if get_origin(field.type) is Literal:
                # Value must be from this set
                choices = get_args(field.type)
                arg_type = type(choices[0])

                if any((not isinstance(c, arg_type) for c in choices)):
                    raise TypeError(
                        f"If Literal is used, all values must be of the same type ({config_cls}.{field.name})."
                    )

                parser.add_argument(f"--{arg_name}", type=arg_type, choices=choices, help=help_text, default=MISSING)

            # Boolean field
            elif issubclass(field.type, bool):
                # Create a true and a false flag -> the destination is identical
                parser.add_argument(
                    f"--{arg_name}", action="store_true", default=MISSING, help=help_text + " (sets the value to True)"
                )

                parser.add_argument(
                    f"--!{arg_name}",
                    dest="arg_name",
                    action="store_false",
                    default=MISSING,
                    help=help_text + " (sets the value to False)",
                )

            # Other types
            else:
                parser.add_argument(f"--{arg_name}", type=field.type, help=help_text, default=MISSING)


def construct_config_parser(config_cls: Type[T], cordage_config, **kw) -> argparse.ArgumentParser:
    """Construct an argparser for a given config class."""
    # add parser arguments from dataclass

    parser = argparse.ArgumentParser(**kw)

    add_arguments_to_parser(config_cls, parser)

    parser.add_argument(
        ".", metavar="config_file", nargs="?", help="Top-level config file to load.", type=Path, default=MISSING
    )

    return parser


def remove_missing_values(data: Mapping) -> Dict[str, Any]:
    return {k: v for k, v in data.items() if v is not MISSING}


def parse_config(config_cls: Type[T], cordage_config, args=None, **kw) -> T:
    # construct parser
    parser = construct_config_parser(config_cls, cordage_config, **kw)

    conf_data: dict = vars(parser.parse_args(args))
    conf_data = remove_missing_values(conf_data)

    return from_dict(config_cls, conf_data)


def flat_update(flat_dict, nested_dict, prefix=None):
    for k, v in nested_dict.items():
        flat_k = k if prefix is None else f"{prefix}.{k}"

        if isinstance(v, dict):
            flat_update(flat_dict, v, flat_k)
        else:
            flat_dict[flat_k] = v


def is_required(field: dataclasses.Field) -> bool:
    return field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


def from_dict(config_cls: Type[T], data: Mapping) -> T:
    """Create a (potentially nested) configuration object from a mapping."""
    assert dataclasses.is_dataclass(config_cls)

    flat_dict: Dict[str, Any] = dict()

    if "." in data:
        # load from configuration path first
        loaded_data = read_config_file(data["."])

        flat_update(flat_dict, loaded_data)

    for k, v in data.items():
        if k != ".":
            flat_dict[k] = v

    config_kw = dict()

    for field in dataclasses.fields(config_cls):
        if not field.init:
            continue

        if not dataclasses.is_dataclass(field.type):
            try:
                config_kw[field.name] = flat_dict[field.name]
            except KeyError as exc:
                if is_required(field):
                    raise KeyError(f"Field {field.name} in {config_cls} is required, but was not specified.") from exc
        else:
            inner_dict = dict()

            for k, v in flat_dict.items():
                if not k.startswith(field.name):
                    continue

                if k == field.name:
                    inner_dict["."] = v

                else:
                    inner_dict[k.split(".", 1)[1]] = v

            config_kw[field.name] = from_dict(field.type, inner_dict)

    return cast(T, config_cls(**config_kw))


def to_dict(config) -> dict:
    """Represent the fields and values of configuration as a (nested) dict."""

    d = dict()

    for field in dataclasses.fields(config):
        value = getattr(config, field.name)

        if dataclasses.is_dataclass(value):
            value = to_dict(value)

        d[field.name] = value

    return d


def to_file(config, path: PathLike):
    """Write config to json, toml, or yaml file."""
    data = to_dict(config)
    write_config_file(path, data)
