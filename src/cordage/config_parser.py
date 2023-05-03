import sys
from typing import Any, Dict, Generic, Mapping, Optional, Type, TypeVar, Union, get_args, get_origin

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
from .util import from_dict, nest_dict, nested_update, read_dict_from_file


class MissingType:
    def __repr__(self):
        return "<MISSING>"


MISSING = MissingType()


T = TypeVar("T")

SUPPORTED_PRIMITIVES = (int, bool, str, float, Path)


class ConfigurationParser(Generic[T]):
    def __init__(self, global_config: GlobalConfig, config_cls: Type[T], **kw):
        self.global_config: GlobalConfig = global_config
        self.main_config_cls: Type[T] = config_cls

        self.parser = self.construct_config_parser(**kw)

        self.description = kw.get("description")

    def parse_all(self, args=None) -> Series[T]:
        if args is None:
            # args default to the system args
            args = sys.argv[1:]
        else:
            args = list(args)

        # construct parser
        argument_data: dict = vars(self.parser.parse_args(args))
        argument_data = self.remove_missing_values(argument_data)

        config_path = argument_data.pop(".", None)

        argument_data = nest_dict(argument_data)

        if config_path is not None:
            new_conf_data = read_dict_from_file(config_path)

            new_conf_data = nest_dict(new_conf_data)

            series_spec = new_conf_data.pop(self.global_config.series_spec_key, None)

            nested_update(new_conf_data, argument_data)

            argument_data = new_conf_data

        else:
            series_spec = None

        # series skip might be given via the command line ("--series-skip <n>") or a config file "__series-skip__"
        series_skip = argument_data.pop(self.global_config.series_skip_key, None)

        base_config: T = from_dict(self.main_config_cls, argument_data)

        return Series(
            base_config=base_config,
            global_config=self.global_config,
            series_spec=series_spec,
            series_skip=series_skip,
            additional_info={"description": self.description, "parsed_arguments": args},
        )

    def construct_config_parser(self, **kw) -> argparse.ArgumentParser:
        """Construct an argparser for a given config class."""
        # add parser arguments from dataclass

        parser = argparse.ArgumentParser(**kw)

        self.add_arguments_to_parser(self.main_config_cls, parser)

        parser.add_argument(
            ".", metavar="config_file", nargs="?", help="Top-level config file to load.", type=Path, default=MISSING
        )

        parser.add_argument(
            "--series-skip",
            type=int,
            metavar="n",
            help="Skip first n trials in the execution of a series.",
            default=MISSING,
            dest=self.global_config.series_skip_key,
        )

        return parser

    def _add_argument_to_parser(self, parser: argparse.ArgumentParser, arg_name: str, arg_type: Any, **kw):
        # If the field is also a dataclass, recurse (nested config)
        if dataclasses.is_dataclass(arg_type):
            self.add_arguments_to_parser(arg_type, parser, prefix=arg_name)

            parser.add_argument(f"--{arg_name}", type=Path, default=MISSING, **kw)
        else:
            # Look the field annotation to determine which type of argument to add

            # Choice field
            if get_origin(arg_type) is Literal:
                # Value must be from this set
                choices = get_args(arg_type)

                literal_arg_type = type(choices[0])

                if any((not isinstance(c, literal_arg_type) for c in choices)):
                    raise TypeError(f"If Literal is used, all values must be of the same type ({arg_name}).")

                parser.add_argument(f"--{arg_name}", type=literal_arg_type, choices=choices, default=MISSING, **kw)

            elif get_origin(arg_type) is Union:
                args = get_args(arg_type)

                if len(args) == 2 and isinstance(None, args[1]):
                    # optional
                    self._add_argument_to_parser(parser, arg_name, args[0])

                else:
                    raise TypeError("Config parser does not support Union annotations.")

            # Boolean field
            elif arg_type == bool:
                # Create a true and a false flag -> the destination is identical
                if "help" in kw:
                    kw_true = {**kw, "help": kw["help"] + " (sets the value to True)"}
                    kw_false = {**kw, "help": kw["help"] + " (sets the value to False)"}
                else:
                    kw_true = kw_false = kw

                parser.add_argument(f"--{arg_name}", action="store_true", default=MISSING, **kw_true)

                parser.add_argument(
                    f"--not-{arg_name}", dest=arg_name, action="store_false", default=MISSING, **kw_false
                )

            elif arg_type in SUPPORTED_PRIMITIVES:
                parser.add_argument(f"--{arg_name}", type=arg_type, default=MISSING, **kw)

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

            self._add_argument_to_parser(parser, arg_name, field.type, help=help_text)

    def remove_missing_values(self, data: Mapping) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if v is not MISSING}
