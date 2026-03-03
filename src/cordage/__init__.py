import logging
import sys
from collections.abc import Callable
from dataclasses import replace
from os import PathLike

import cordage.exceptions
from cordage.context import FunctionContext
from cordage.experiment import Experiment, Metadata, Series, Status, Trial
from cordage.global_config import GlobalConfig

logger = logging.getLogger("cordage")


def run(
    func: Callable,
    args: list[str] | None = None,
    *,
    description: str | None = None,
    config_cls: type | None = None,
    global_config: PathLike | dict | GlobalConfig | None = None,
    **kw,
) -> Experiment:
    try:
        _global_config = replace(GlobalConfig.resolve(global_config), **kw)
        context = FunctionContext(
            func,
            description=description,
            config_cls=config_cls,
            global_config=_global_config,
        )
        experiment = context.parse_args(args)
        context.execute(experiment)
        return experiment
    except cordage.exceptions.CordageError as e:
        if _global_config.catch_exception:
            logger.critical(str(e))
            sys.exit(1)
        else:
            raise


__all__ = [
    "Experiment",
    "FunctionContext",
    "GlobalConfig",
    "Metadata",
    "Series",
    "Status",
    "Trial",
    "run",
]
