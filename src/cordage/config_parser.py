import sys
from typing import Any, Dict, Generic, Mapping, Optional, Type, TypeVar, get_args, get_origin

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

import argparse
import dataclasses
from pathlib import Path

from docstring_parser import parse as parse_docstring

from .experiment import Series
from .global_config import GlobalConfig
from .util import flatten_dict, from_dict, read_config_file


class MissingType:
    def __repr__(self):
        return "<MISSING>"


MISSING = MissingType()


T = TypeVar("T")


class ConfigurationParser(Generic[T]):
    def __init__(self, global_config: GlobalConfig, config_cls: Type[T], **kw):
        self.global_config: GlobalConfig = global_config
        self.main_config_cls: Type[T] = config_cls

        self.parser = self.construct_config_parser(**kw)

        self.description = kw.get("description")

    def parse_all(self, args=None) -> Series[T]:
        # construct parser
        conf_data: dict = vars(self.parser.parse_args(args))
        conf_data = self.remove_missing_values(conf_data)

        if "." in conf_data:
            config_path = conf_data.pop(".")

            nested_loaded_data = read_config_file(config_path)

            series_spec = nested_loaded_data.pop(self.global_config.series_spec_key, None)

            new_conf_data = flatten_dict(nested_loaded_data)
            new_conf_data.update(conf_data)

            conf_data = new_conf_data

        else:
            series_spec = None

        base_config: T = from_dict(self.main_config_cls, conf_data)

        return Series(
            base_config=base_config,
            global_config=self.global_config,
            series_spec=series_spec,
            additional_info={
                "description": self.description,
            },
        )

    def construct_config_parser(self, **kw) -> argparse.ArgumentParser:
        """Construct an argparser for a given config class."""
        # add parser arguments from dataclass

        parser = argparse.ArgumentParser(**kw)

        self.add_arguments_to_parser(self.main_config_cls, parser)

        parser.add_argument(
            ".", metavar="config_file", nargs="?", help="Top-level config file to load.", type=Path, default=MISSING
        )

        return parser

    def add_arguments_to_parser(
        self, config_cls: Type[T], parser: argparse.ArgumentParser, prefix: Optional[str] = None
    ):
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
            help_text = field.metadata.get("help", param_doc.get(field.name, ""))

            # If the field is also a dataclass, recurse (nested config)
            if dataclasses.is_dataclass(field.type):
                self.add_arguments_to_parser(field.type, parser, prefix=arg_name)

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

                    parser.add_argument(
                        f"--{arg_name}", type=arg_type, choices=choices, help=help_text, default=MISSING
                    )

                # Boolean field
                elif issubclass(field.type, bool):
                    # Create a true and a false flag -> the destination is identical
                    parser.add_argument(
                        f"--{arg_name}",
                        action="store_true",
                        default=MISSING,
                        help=help_text + " (sets the value to True)",
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

    def remove_missing_values(self, data: Mapping) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if v is not MISSING}
