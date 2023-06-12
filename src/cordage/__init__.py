from os import PathLike
from typing import Callable, Dict, List, Optional, Type, Union

from dacite.exceptions import (
    DaciteError,
    DaciteFieldError,
    ForwardReferenceError,
    MissingValueError,
    StrictUnionMatchError,
    UnexpectedDataError,
    UnionMatchError,
    WrongTypeError,
)

from .context import FunctionContext
from .experiment import Experiment, Metadata, Series, Trial
from .global_config import GlobalConfig


def run(
    func: Callable,
    args: Optional[List[str]] = None,
    description: Optional[str] = None,
    config_cls: Optional[Type] = None,
    global_config: Union[PathLike, Dict, GlobalConfig, None] = None,
) -> Experiment:
    context = FunctionContext(func, description=description, config_cls=config_cls, global_config=global_config)
    experiment = context.parse_args(args)
    context.execute(experiment)
    return experiment


__all__ = [
    "run",
    "FunctionContext",
    "Experiment",
    "Trial",
    "Metadata",
    "GlobalConfig",
    "Series",
    "DaciteError",
    "DaciteFieldError",
    "WrongTypeError",
    "MissingValueError",
    "UnionMatchError",
    "StrictUnionMatchError",
    "ForwardReferenceError",
    "UnexpectedDataError",
]
