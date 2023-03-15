import inspect
from typing import Callable, Type

from docstring_parser import parse as parse_docstring

from .configuration import parse_config
from .cordage_config import CordageConfig
from .trial import Trial

USAGE_STR = "%(prog)s [-h] [config_file] <configuration options to overwrite>"


def run(func: Callable, args=None, description=None, **kw):
    cordage_config = CordageConfig(**kw)

    func_parameters = inspect.signature(func).parameters

    # derive configuration class
    try:
        config_cls: Type = func_parameters[cordage_config.config_param_name].annotation
    except KeyError as exc:
        raise TypeError(f"Callable must accept config in `{cordage_config.config_param_name}`.") from exc

    if description is None:
        if func.__doc__ is not None:
            description = parse_docstring(func.__doc__).short_description
        else:
            description = func.__name__

    # parse configuration
    trial_config = parse_config(config_cls, cordage_config, args=args, description=description, usage=USAGE_STR)

    # create trial object
    trial = Trial(config=trial_config, cordage_config=cordage_config, metadata={"description": description})

    # execute function with the constructed keyword arguments
    with trial.run():
        # construct arguments for the passed callable
        func_kw = dict()

        # check if any other parameters are expected which can be resolved
        for name, param in func_parameters.items():
            assert param.kind != param.POSITIONAL_ONLY, "Cordage currently does not support positional only parameters."

            if name == cordage_config.config_param_name:
                # pass the configuration
                func_kw[cordage_config.config_param_name] = trial_config

            elif name == cordage_config.output_dir_param_name:
                # pass path to output directory
                if issubclass(param.annotation, str):
                    func_kw[name] = str(trial.output_dir)
                else:
                    func_kw[name] = trial.output_dir

            elif name == cordage_config.trial_object_param_name:
                # pass trial object
                func_kw[name] = trial

        func(**func_kw)
