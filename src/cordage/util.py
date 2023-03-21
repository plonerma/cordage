import dataclasses
import inspect
import logging
import sys
from datetime import datetime, timedelta
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Type, TypeVar, cast, get_args, get_origin

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

logger = logging.getLogger("cordage")

T = TypeVar("T")


def get_loader(extension):
    """Load relevant module for reading a file with the given extension."""
    if extension not in ("toml", "yaml", "yml", "yl", "json"):
        raise RuntimeError(f"Unrecognized file format: '.{extension}' (supported are .toml, .yaml, and .json).")

    loader: Callable

    if extension == "toml":
        try:
            from toml import load as toml_loader

            loader = toml_loader
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Package toml is required to read .{extension} files.") from exc

    elif extension in ("yaml", "yml", "yl"):
        try:
            from yaml import safe_load as yaml_loader

            loader = yaml_loader
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Package pyyaml is required to read .{extension} files.") from exc
    else:
        try:
            from json import load as json_loader

            loader = json_loader
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Package json is required to read .{extension} files.") from exc

    return loader


def read_config_file(path: PathLike) -> Dict[str, Any]:
    """Read config file.

    Can be of type toml, yaml, or json.
    """
    extension = Path(path).suffix[1:]

    loader = get_loader(extension)

    with open(path, "r", encoding="utf-8") as conf_file:
        return loader(conf_file)


def get_writer(extension):
    """Load relevant module for reading a file with the given extension."""
    if extension not in ("toml", "yaml", "yml", "yl", "json"):
        raise RuntimeError(f"Unrecognized file format: '.{extension}' (supported are .toml, .yaml, and .json).")

    writer: Callable

    if extension == "toml":
        try:
            from toml import dump as toml_dump

            writer = toml_dump
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Package toml is required to read .{extension} files.") from exc

    elif extension in ("yaml", "yml", "yl"):
        try:
            from yaml import dump as yaml_dump

            writer = yaml_dump
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Package pyyaml is required to write .{extension} files.") from exc
    else:
        try:
            from json import dump as json_dump

            writer = json_dump
        except ModuleNotFoundError as exc:
            raise RuntimeError(f"Package json is required to read .{extension} files.") from exc

    return writer


def write_config_file(path: PathLike, data: Mapping[str, Any]):
    """Save config file.

    Can be of type toml, yaml, or json.
    """
    extension = Path(path).suffix[1:]

    writer = get_writer(extension)

    with open(path, "w", encoding="utf-8") as conf_file:
        return writer(data, conf_file)


def flatten_dict(nested_dict, update_dict=None, prefix=None):
    """Update (or create) a flat dictionary.

    :param nested_dict: The nested dictionary whose items will be used.
    :param update_dict: A dictionary to update with the items from nested_dict (optional).
    """

    if update_dict is None:
        update_dict = {}

    for k, v in nested_dict.items():
        flat_k = k if prefix is None else f"{prefix}.{k}"

        if isinstance(v, dict):
            flatten_dict(v, update_dict=update_dict, prefix=flat_k)
        else:
            update_dict[flat_k] = v

    return update_dict


def is_field_required(field: dataclasses.Field) -> bool:
    return field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING


def from_dict(config_cls: Type[T], flat_data: Mapping) -> T:
    """Create a (potentially nested) configuration object from a mapping."""
    assert dataclasses.is_dataclass(config_cls)

    logger.debug("Constructing '%s'", config_cls.__name__)
    logger.debug(str(flat_data))

    config_kw = dict()

    for field in dataclasses.fields(config_cls):
        if not field.init:
            # Field is not set in the initializer
            continue

        if not dataclasses.is_dataclass(field.type):
            # The is not a dataclass -> can be set directly
            try:
                config_kw[field.name] = deserialize_value(flat_data[field.name], field.type)
            except KeyError as exc:
                # If the field is required, raise a KeyError, otherwise ignore
                if is_field_required(field):
                    raise KeyError(f"Field {field.name} in {config_cls} is required, but was not specified.") from exc
        else:
            # Field stores a dataclass instances
            inner_dict = dict()
            inner_conf_file = None

            logger.debug("Field '%s' has type '%s'", field.name, field.type.__name__)

            for k, v in flat_data.items():
                # Ingore all keys which do not start with the field name
                if not k.startswith(field.name):
                    continue

                if k == field.name:
                    # Remember the path for loading the config file later
                    inner_conf_file = v
                else:
                    # Normal field, remove the prefix and store the value
                    inner_dict[k.split(".", 1)[1]] = v

            if inner_conf_file:
                # load from configuration path first
                logger.info("Loading required configuration file '%s'", str(inner_conf_file))

                nested_loaded_data = read_config_file(inner_conf_file)

                # Flatten the nested data
                new_flat_data: Dict[str, Any] = flatten_dict(nested_loaded_data)

                # Overwrite all the given flat key-value pairs
                new_flat_data.update(inner_dict)

                inner_dict = new_flat_data

            config_kw[field.name] = from_dict(field.type, inner_dict)

    return cast(T, config_cls(**config_kw))


def to_dict(config) -> dict:
    """Represent the fields and values of configuration as a (nested) dict."""

    d = dataclasses.asdict(config)

    return nested_serialization(d)


def to_file(config, path: PathLike):
    """Write config to json, toml, or yaml file."""
    data = to_dict(config)
    write_config_file(path, data)


def nested_serialization(d):
    if isinstance(d, dict):
        return {k: nested_serialization(v) for k, v in d.items()}
    else:
        return serialize_value(d)


def serialize_value(value):
    if isinstance(value, Path):
        return str(value)

    elif isinstance(value, datetime):
        return datetime.isoformat(value)

    elif isinstance(value, timedelta):
        return value.total_seconds()

    elif dataclasses.is_dataclass(value):
        return to_dict(value)

    else:
        return value


def deserialize_value(value: Any, cls: Type):
    if not inspect.isclass(cls) and get_origin(cls) is Literal:
        # Value must be from this set
        choices = get_args(cls)
        arg_type = type(choices[0])

        if any((not isinstance(c, arg_type) for c in choices)):
            raise TypeError(f"If Literal is used, all values must be of the same type ({cls}).")

        if value not in choices:
            raise TypeError(f"Value {value} not in {cls}")
    else:
        assert inspect.isclass(cls)

        if issubclass(cls, Path):
            return Path(value)

        elif issubclass(cls, float):
            return float(value)

        elif issubclass(cls, datetime):
            return datetime.fromisoformat(value)

        elif issubclass(cls, timedelta):
            return timedelta(seconds=value)

        else:
            return value
