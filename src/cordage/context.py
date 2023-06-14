import argparse
import dataclasses
import inspect
import sys
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Type, TypeVar, Union, get_args, get_origin

from docstring_parser import parse as parse_docstring

from .experiment import Experiment, Series, Trial
from .global_config import GlobalConfig, get_global_config
from .util import from_dict as config_from_dict
from .util import logger, nest_items, nested_update, read_dict_from_file


class MissingType:
    def __repr__(self):
        return "<MISSING>"


MISSING = MissingType()


T = TypeVar("T")

SUPPORTED_PRIMITIVES = (int, bool, str, float, Path)


class Singleton(type):
    _instances: Dict[Type, Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class TrialStack(metaclass=Singleton):
    def __init__(self):
        self.running: List[Trial] = []

    def push(self, trial: Trial):
        self.running.append(trial)

    def pop(self) -> Trial:
        return self.running.pop()

    def peek(self) -> Optional[Trial]:
        if len(self.running) > 0:
            return self.running[-1]
        else:
            return None

    def peek_id(self) -> Optional[str]:
        if len(self.running) > 0:
            return self.running[-1].experiment_id
        else:
            return None

    def __len__(self):
        return len(self.running)

    @contextmanager
    def with_trial_on_stack(self, trial: Trial):
        if trial.parent_id is None:
            trial.metadata.parent_id = self.peek_id()
        self.push(trial)
        try:
            with trial:
                yield trial
        finally:
            self.pop()


trial_stack: TrialStack = TrialStack()


class FunctionContext:
    """Wrapper for a function which accepts a dataclass configuration.

    This class can be used to:
    - parse argruments matching the config dataclass,
    - build a dictionary of the arguments expected by the function, and
    - call the function for each trial in a series.
    """

    global_config: GlobalConfig

    usage_str: str = "%(prog)s [-h] [config_file] <configuration options to overwrite>"

    def __init__(
        self,
        func: Callable,
        description: Optional[str] = None,
        config_cls: Optional[Type] = None,
        global_config: Union[str, PathLike, Dict, GlobalConfig, None] = None,
    ):
        self.global_config = get_global_config(global_config)
        self.set_function(func)
        self.set_config_cls(config_cls)
        self.set_description(description)
        self.construct_argument_parser()

    def set_description(self, description: Optional[str] = None):
        if description is None:
            if self.func.__doc__ is not None:
                self.description = parse_docstring(self.func.__doc__).short_description
            else:
                self.description = self.func_name

        else:
            self.description = description

    def set_config_cls(self, config_cls: Optional[Type] = None):
        # derive configuration class
        if config_cls is None:
            self.main_config_cls = self.func_parameters[self.global_config.param_names.config].annotation

        else:
            self.main_config_cls = config_cls

        if not dataclasses.is_dataclass(self.main_config_cls):
            raise TypeError(
                f"Configuration class could not be derived: Either pass a configuration dataclass via `config_cls` or"
                f"annotate the configuration parameter `{self.global_config.param_names.config}` with a dataclass."
            )

    @property
    def func(self) -> Callable:
        return self._func

    @property
    def func_parameters(self):
        return self._func_parameters

    @property
    def func_name(self):
        return self._func_name

    def set_function(self, func: Callable):
        self._func = func
        self._func_parameters = inspect.signature(func).parameters
        self._func_name = self.func.__name__

        if self.global_config.param_names.config not in self.func_parameters:
            raise TypeError(f"Callable must accept config argument (as `{self.global_config.param_names.config}`).")

    def construct_argument_parser(self):
        """Construct an argparser for a given config class."""
        # add parser arguments from dataclass

        self.argument_parser = argparse.ArgumentParser(description=self.description, usage=self.usage_str)

        self.add_arguments_to_parser(self.main_config_cls)

        self.argument_parser.add_argument(
            ".", metavar="config_file", nargs="?", help="Top-level config file to load.", type=Path, default=MISSING
        )

        self.argument_parser.add_argument(
            "--series-skip",
            type=int,
            metavar="n",
            help="Skip first n trials in the execution of a series.",
            default=MISSING,
            dest=self.global_config._series_skip_key,
        )

        self.argument_parser.add_argument(
            "--series-comment",
            action="store_true",
            help="Add a comment to the annotation of this series.",
            default=MISSING,
            dest=self.global_config._series_comment_key,
        )

    def _add_argument_to_parser(self, arg_name: str, arg_type: Any, help: str, **kw):
        # If the field is also a dataclass, recurse (nested config)
        if dataclasses.is_dataclass(arg_type):
            self.add_arguments_to_parser(arg_type, prefix=arg_name)

            self.argument_parser.add_argument(f"--{arg_name}", type=Path, default=MISSING, help=help, **kw)
        else:
            # Look the field annotation to determine which type of argument to add

            # Choice field
            if get_origin(arg_type) is Literal:
                # Value must be from this set
                choices = get_args(arg_type)

                literal_arg_type = type(choices[0])

                if any((not isinstance(c, literal_arg_type) for c in choices)):
                    raise TypeError(f"If Literal is used, all values must be of the same type ({arg_name}).")

                self.argument_parser.add_argument(
                    f"--{arg_name}", type=literal_arg_type, choices=choices, default=MISSING, help=help, **kw
                )

            elif get_origin(arg_type) is Union:
                args = get_args(arg_type)

                if len(args) == 2 and isinstance(None, args[1]):
                    # optional
                    self._add_argument_to_parser(arg_name, args[0], help=help, **kw)

                else:
                    raise TypeError("Config parser does not support Union annotations.")

            # Boolean field
            elif arg_type == bool:
                # Create a true and a false flag -> the destination is identical
                self.argument_parser.add_argument(
                    f"--{arg_name}", action="store_true", default=MISSING, help=help + " (set the value to True)", **kw
                )

                self.argument_parser.add_argument(
                    f"--not-{arg_name}",
                    dest=arg_name,
                    action="store_false",
                    default=MISSING,
                    help=help + " (set the value to False)",
                    **kw,
                )

            elif arg_type in SUPPORTED_PRIMITIVES:
                self.argument_parser.add_argument(f"--{arg_name}", type=arg_type, default=MISSING, help=help, **kw)

    def add_arguments_to_parser(self, config_cls: Type[T], prefix: Optional[str] = None):
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

            self._add_argument_to_parser(arg_name, field.type, help=help_text)

    def remove_missing_values(self, data: Mapping) -> Dict[str, Any]:
        return {k: v for k, v in data.items() if v is not MISSING}

    def construct_func_kwargs(self, trial: Trial):
        # construct arguments for the passed callable
        func_kw: Dict[str, Any] = {}

        # check if any other parameters are expected which can be resolved
        for name, param in self.func_parameters.items():
            assert param.kind != param.POSITIONAL_ONLY, "Cordage currently does not support positional only parameters."

            if name == self.global_config.param_names.config:
                # pass the configuration
                func_kw[name] = trial.config

            elif name == self.global_config.param_names.output_dir:
                # pass path to output directory
                if issubclass(param.annotation, str):
                    func_kw[name] = str(trial.output_dir)
                else:
                    func_kw[name] = trial.output_dir

            elif name == self.global_config.param_names.trial_object:
                # pass trial object
                func_kw[name] = trial

        return func_kw

    def parse_args(self, args=None) -> Experiment:
        if args is None:
            # args default to the system args
            args = sys.argv[1:]
        else:
            args = list(args)

        # construct parser
        argument_data: dict = vars(self.argument_parser.parse_args(args))
        argument_data = self.remove_missing_values(argument_data)

        # series comment might be given via the command line ("--series-skip")
        series_comment_flag = argument_data.pop(self.global_config._series_comment_key, False)

        config_path = argument_data.pop(".", None)

        argument_data = nest_items(argument_data.items())

        if config_path is not None:
            new_conf_data = read_dict_from_file(config_path)

            new_conf_data = nest_items(new_conf_data.items())

            series_spec = new_conf_data.pop(self.global_config._series_spec_key, None)

            nested_update(new_conf_data, argument_data)

            argument_data = new_conf_data

            # another series comment might be given via the config file ("__series-skip__")
            # in this case, the comments are added to another
            conf_file_comment = argument_data.pop(self.global_config._series_comment_key, None)
        else:
            series_spec = None
            conf_file_comment = None

        # series skip might be given via the command line ("--series-skip <n>") or a config file "__series-skip__"
        series_skip = argument_data.pop(self.global_config._series_skip_key, None)

        base_config = config_from_dict(self.main_config_cls, argument_data, strict=self.global_config.strict_mode)

        series: Series = Series(
            function=self.func_name,
            base_config=base_config,
            global_config=self.global_config,
            series_spec=series_spec,
            series_skip=series_skip,
            additional_info={"description": self.description, "parsed_arguments": args},
        )

        if series_comment_flag is True:
            if conf_file_comment is not None:
                # add the stdin commnent after the config file comment
                comment = conf_file_comment + "\n\n"
            else:
                # there is not comment in the config file, but user passes one via stdin
                comment = ""

            # get comment from stdin
            for line in sys.stdin:
                comment += line
            series.comment = comment

        elif conf_file_comment is not None:
            # only use the comment from the config file
            series.comment = conf_file_comment

        logger.debug("%d experiments found in configuration", len(series))

        if series.is_singular:
            return next(iter(series))
        else:
            return series

    def from_configuration(
        self,
        config=None,
        base_config=None,
        series_spec=None,
        series_skip: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> Experiment:
        _usage = "Either pass `config` or `base_config` and `series_spec`"

        if config is not None:
            assert base_config is None and series_spec is None and series_skip is None, _usage

            trial: Trial = Trial(
                function=self.func_name,
                config=config,
                global_config=self.global_config,
                additional_info={"description": self.description},
            )

            trial.comment = comment

            return trial

        else:
            assert base_config is not None and series_spec is not None

            series: Series = Series(
                function=self.func_name,
                base_config=base_config,
                global_config=self.global_config,
                series_spec=series_spec,
                series_skip=series_skip,
                additional_info={"description": self.description},
            )
            series.comment = comment
            return series

    def execute(self, experiment: Experiment):
        if isinstance(experiment, Trial):
            logger.info(f"Running trial (stack size: {len(trial_stack)})")

            # execute function with the constructed keyword arguments
            with trial_stack.with_trial_on_stack(experiment):
                func_kw = self.construct_func_kwargs(experiment)

                experiment.metadata.result = self.func(**func_kw)

        elif isinstance(experiment, Series):
            with experiment:
                for trial in experiment:
                    self.execute(trial)
        else:
            raise TypeError("Passed object must be Trial or Series")
