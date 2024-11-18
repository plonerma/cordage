import argparse
import dataclasses
import inspect
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Type,
    Union,
    get_args,
    get_origin,
)

from docstring_parser import parse as parse_docstring

from cordage.experiment import Experiment, Series, Trial
from cordage.global_config import GlobalConfig
from cordage.util import ConfigClass, logger, nest_items, nested_update, read_dict_from_file


class MissingType:
    def __repr__(self):
        return "<MISSING>"


MISSING = MissingType()


SUPPORTED_PRIMITIVES = (int, bool, str, float, Path)


class Singleton(type):
    _instances: ClassVar[Dict[Type, Any]] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class ExperimentStack(metaclass=Singleton):
    """Represents the stack of currently running experiments.

    This class is used internally, to determine whether an experiment
    was started from within another.
    """

    def __init__(self):
        self.running: List[Experiment] = []

    def push(self, experiment: Experiment):
        """Push a new experiment on the stack."""
        self.running.append(experiment)

    def pop(self) -> Experiment:
        """Pop the currently running experiment from the stack."""
        return self.running.pop()

    def peek(self) -> Optional[Experiment]:
        """Get the currently active experiment from the stack.

        If the stack is empty, None is returned.
        """
        if len(self.running) > 0:
            return self.running[-1]
        else:
            return None

    def peek_dir(self) -> Optional[Path]:
        """Get the output_dir of the currently running experiment.

        If the stack is empty, None is returned.
        """
        if len(self.running) > 0:
            return self.running[-1].output_dir
        else:
            return None

    def __len__(self):
        return len(self.running)

    @contextmanager
    def with_experiment_on_stack(self, experiment: Experiment):
        """Put a new experiment on the stack and set its `parent_dir`.

        The `parent_dir` will then point to the experiment which was
        running so far (i.e. the outer experiment)."""
        if self.peek() == experiment:
            yield experiment

        else:
            experiment.metadata.parent_dir = self.peek_dir()
            self.push(experiment)
            try:
                with experiment:
                    yield experiment
            finally:
                self.pop()


experiment_stack: ExperimentStack = ExperimentStack()


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
        func: Callable,  # expects a dataclass
        global_config: GlobalConfig,
        description: Optional[str] = None,
        config_cls: Optional[Type[ConfigClass]] = None,
    ):
        self.global_config = global_config
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
            self.main_config_cls = self.func_parameters[
                self.global_config.param_name_config
            ].annotation

        else:
            self.main_config_cls = config_cls

        if not dataclasses.is_dataclass(self.main_config_cls):
            msg = (
                "Configuration class could not be derived: Either pass a configuration dataclass "
                "via `config_cls` or annotate the configuration parameter "
                f"`{self.global_config.param_name_config}` with a dataclass."
            )
            raise TypeError(msg)

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

        if self.global_config.param_name_config not in self.func_parameters:
            msg = (
                "Callable must accept config argument (as "
                f"`{self.global_config.param_name_config}`)."
            )
            raise TypeError(msg)

    def construct_argument_parser(self):
        """Construct an argparser for a given config class."""
        # add parser arguments from dataclass

        self.argument_parser = argparse.ArgumentParser(
            description=self.description, usage=self.usage_str
        )

        self.argument_parser.add_argument(
            ".",
            metavar="config_file",
            nargs="?",
            help="Top-level config file to load (optional).",
            type=Path,
            default=MISSING,
        )

        self.argument_parser.add_argument(
            "--series-skip",
            type=int,
            metavar="N",
            help="Skip first N trials in the execution of a series.",
            default=MISSING,
            dest=self.global_config._series_skip_key,
        )

        if not self.global_config.config_only:
            self.argument_parser.add_argument(
                "--cordage-comment",
                type=str,
                help="Add a comment to the annotation of this series.",
                default=MISSING,
                dest=self.global_config._experiment_comment_key,
                metavar="COMMENT",
            )

            self.argument_parser.add_argument(
                "--output_dir",
                type=Path,
                help="Path to use as the output directory.",
                default=MISSING,
                dest=self.global_config._output_dir_key,
                metavar="PATH",
            )

        self.arg_group_config = self.argument_parser.add_argument_group("configuration")
        self.add_arguments_to_parser(self.main_config_cls)

    def _add_argument_to_parser(self, arg_name: str, arg_type: Any, help: str, **kw):  # noqa: A002
        # If the field is also a dataclass, recurse (nested config)
        if dataclasses.is_dataclass(arg_type):
            assert isinstance(arg_type, type)
            self.arg_group_config.add_argument(
                f"--{arg_name}", type=Path, default=MISSING, help=help, metavar="PATH", **kw
            )
            self.add_arguments_to_parser(arg_type, prefix=arg_name)

        # Look the fields annotation to determine which type of argument
        # to add

        # Choice field
        elif get_origin(arg_type) is Literal:
            # Value must be from this set
            choices = get_args(arg_type)

            literal_arg_type = type(choices[0])

            if any(not isinstance(c, literal_arg_type) for c in choices):
                msg = f"If Literal is used, all values must be of the same type ({arg_name})."
                raise TypeError(msg)

            self.arg_group_config.add_argument(
                f"--{arg_name}",
                type=literal_arg_type,
                choices=choices,
                default=MISSING,
                help=help,
                **kw,
            )

        elif get_origin(arg_type) is Union:
            args = [arg for arg in get_args(arg_type) if arg is not type(None)]

            if len(args) == 1:
                # optional
                self._add_argument_to_parser(arg_name, args[0], help=help, **kw)

            else:
                msg = (
                    f"Parameter `{arg_name}` could not be processed:"
                    "Config parser does not support Union annotations with more than one type "
                    "other than None."
                )
                raise TypeError(msg)

        # Boolean field
        elif arg_type is bool:
            # Create a true/false flag -> the destination is identical
            self.arg_group_config.add_argument(
                f"--{arg_name}",
                action="store_true",
                default=MISSING,
                help=help + " (set the value to True)",
                **kw,
            )

            self.arg_group_config.add_argument(
                f"--not-{arg_name}",
                dest=arg_name,
                action="store_false",
                default=MISSING,
                help=help + " (set the value to False)",
                **kw,
            )

        elif arg_type in SUPPORTED_PRIMITIVES:
            self.arg_group_config.add_argument(
                f"--{arg_name}", type=arg_type, default=MISSING, help=help, **kw
            )

    def add_arguments_to_parser(self, config_cls: Type, prefix: Optional[str] = None):
        """Add all fields in the (nested) config class to the parser.

        Recursively iterate over the fields adding arguments to the
        parser.
        """

        # read documentation of config dataclass. If no help metadata is
        # given, this will be used a the help text.
        param_doc = {}
        if config_cls.__doc__ is not None:
            # parse doc text, to generate help text for fields
            for param in parse_docstring(config_cls.__doc__).params:
                param_doc[param.arg_name] = param.description

        # Iterate over all fields in the dataclass to add arguments to
        # the parser
        for field in dataclasses.fields(config_cls):
            if not field.init:
                continue

            if prefix is None and field.name == self.global_config.param_name_output_dir:
                continue

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

        # check if any other parameters are expected which can be
        # resolved
        for name, param in self.func_parameters.items():
            assert (
                param.kind != param.POSITIONAL_ONLY
            ), "Cordage currently does not support positional only parameters."

            if name == self.global_config.param_name_config:
                # pass the configuration
                func_kw[name] = trial.config

            elif not self.global_config.config_only:
                if name == self.global_config.param_name_output_dir:
                    # pass path to output directory
                    if issubclass(param.annotation, str):
                        func_kw[name] = str(trial.output_dir)
                    else:
                        func_kw[name] = trial.output_dir

                elif name == self.global_config.param_name_trial_object:
                    # pass trial object
                    func_kw[name] = trial

        return func_kw

    def parse_args(self, args: Optional[List[str]] = None) -> Experiment:
        """Parse the command line arguments.

        Args:
            args: A list of arguments (usually from the CLI). If
              none, sys.argv[1:] is used.

        Returns:
            The resulting experiment (the resulting configuration of the
            experiment) is the result of the default values, a
            potentially loaded config file, and parameters passed via
            the CLI args.
        """

        if args is None:
            # args default to the system args
            args = sys.argv[1:]
        else:
            args = list(args)

        # construct parser
        argument_data: dict = vars(self.argument_parser.parse_args(args))
        argument_data = self.remove_missing_values(argument_data)

        conf_file_comment: Optional[str] = None
        cli_series_comment: Optional[str] = None

        series_kw = {
            "function": self.func_name,
            "global_config": self.global_config,
            "additional_info": {"description": self.description, "parsed_arguments": args},
        }

        if not self.global_config.config_only:
            cli_series_comment = argument_data.pop(
                self.global_config._experiment_comment_key, None
            )
            series_kw["output_dir"] = argument_data.pop(self.global_config._output_dir_key, None)

        config_path = argument_data.pop(".", None)

        argument_data = nest_items(argument_data.items())

        if config_path is not None:
            new_conf_data = read_dict_from_file(config_path)

            new_conf_data = nest_items(new_conf_data.items())

            series_kw["series_spec"] = new_conf_data.pop(self.global_config._series_spec_key, None)

            nested_update(new_conf_data, argument_data)

            argument_data = new_conf_data

            if not self.global_config.config_only:
                # another series comment might be given via the confi
                # g file
                # in this case, the comments are added to another
                conf_file_comment = argument_data.pop(
                    self.global_config._experiment_comment_key, None
                )
        else:
            series_kw["series_spec"] = None

        # series skip might be given via the command line
        # ("--series-skip <n>") or a config file "__series-skip__"
        series_kw["series_skip"] = argument_data.pop(self.global_config._series_skip_key, None)
        series_kw["base_config"] = argument_data
        series_kw["config_cls"] = self.main_config_cls

        series: Series = Series(**series_kw)

        if not self.global_config.config_only:
            if cli_series_comment is not None and conf_file_comment is not None:
                series.comment = conf_file_comment + "\n\n" + cli_series_comment
            else:
                series.comment = conf_file_comment or cli_series_comment or ""

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
        """Execute a given experiment.

        The function of this `FunctionContext` is called with the
        configuration given by the experiment.
        """
        if isinstance(experiment, Trial):
            if self.global_config.config_only:
                # execute function with the constructed keyword
                # arguments
                func_kw = self.construct_func_kwargs(experiment)
                experiment.metadata.result = self.func(**func_kw)

            else:
                # only use stack if full feature-set is used
                with experiment_stack.with_experiment_on_stack(experiment):
                    func_kw = self.construct_func_kwargs(experiment)
                    experiment.metadata.result = self.func(**func_kw)

        elif isinstance(experiment, Series):
            if self.global_config.config_only:
                for trial in experiment:
                    self.execute(trial)
            else:
                with experiment_stack.with_experiment_on_stack(experiment):
                    for trial in experiment:
                        self.execute(trial)

        else:
            msg = "Passed object must be Trial or Series"
            raise TypeError(msg)
