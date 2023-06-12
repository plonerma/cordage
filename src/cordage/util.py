import dataclasses
import logging
from datetime import datetime, timedelta
from os import PathLike
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Tuple, Type, TypeVar, Union, cast

import dacite

logger = logging.getLogger("cordage")

T = TypeVar("T")


serialization_map: Dict[Type[Any], Callable[..., Any]] = {
    Path: str,
    datetime: datetime.isoformat,
    timedelta: lambda v: v.total_seconds(),
}

deserialization_map: Dict[Type[Any], Callable[..., Any]] = {
    datetime: lambda v: datetime.fromisoformat(v),
    timedelta: lambda v: timedelta(seconds=v),
}

types_to_cast: List[Type[Any]] = [Path, float, bool, int, str, tuple]


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


def read_dict_from_file(path: PathLike) -> Dict[str, Any]:
    """Read dictionary from toml, yaml, or json file.

    The file-type is inferred from the file extension.
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


def write_dict_to_file(path: PathLike, data: Mapping[str, Any]):
    """Write dictionary to toml, yaml, or json file.

    The file-type is inferred from the file extension.
    """
    extension = Path(path).suffix[1:]

    writer = get_writer(extension)

    with open(path, "w", encoding="utf-8") as conf_file:
        return writer(data, conf_file)


def flattened_items(nested_dict: Dict[Any, Any], prefix: tuple = (), sep=None):
    """Iter over all items in a nested dictionary."""
    for k, v in nested_dict.items():
        flat_k = prefix + (k,)

        if isinstance(v, dict):
            for ik, iv in flattened_items(v, flat_k):
                if sep is None:
                    yield ik, iv
                else:
                    yield sep.join(ik), iv
        else:
            if sep is None:
                yield flat_k, v
            else:
                yield sep.join(flat_k), v


def nested_update(target_dict: Dict, update_dict: Mapping):
    """Update a nested dictionary."""
    for k, v in update_dict.items():
        if isinstance(v, Mapping) and k in target_dict and isinstance(target_dict[k], dict):
            nested_update(target_dict[k], v)
        else:
            target_dict[k] = v

    return target_dict


def nest_items(flat_items: Iterable[Tuple[Union[str, Tuple[str, ...]], Any]]) -> Dict[str, Any]:
    """Unflatten a dict.

    If any keys contain '.', sub-dicts will be created.
    """
    nested_dict: Dict[str, Any] = {}
    dicts_to_nest: List[str] = []

    for k, v in flat_items:
        k_tuple: Tuple[str, ...]
        if isinstance(k, tuple):
            k_tuple = k
        else:
            # if key is of the form "a.b", split into tuple
            k_tuple = tuple(k.split("."))

        prefix = k_tuple[0]
        remainder = k_tuple[1:]

        if len(remainder) == 0:
            nested_dict[prefix] = v

        else:
            if prefix not in nested_dict:
                nested_dict[prefix] = {}
                dicts_to_nest.append(prefix)

            nested_dict[prefix][remainder] = v

    for k in dicts_to_nest:
        nested_dict[k] = nest_items(nested_dict[k].items())

    return nested_dict


def from_dict(data_class: Type[T], data: Mapping, strict: bool = True) -> T:
    config = dacite.Config(cast=types_to_cast, type_hooks=deserialization_map, strict=strict)
    return dacite.from_dict(data_class, data, config)


def from_file(config_cls: Type[T], path: PathLike, **kwargs):
    data: Mapping = read_dict_from_file(path)
    return from_dict(config_cls, data, **kwargs)


def apply_nested_type_mapping(data: Mapping, type_mapping: Mapping[Type, Callable]):
    result = {}

    for k, v in data.items():
        if isinstance(v, Mapping):
            v = apply_nested_type_mapping(v, type_mapping)

        for t, func in type_mapping.items():
            if isinstance(v, t):
                v = func(v)

        result[k] = v

    return result


def to_dict(data: Any) -> dict:
    """Represent the fields and values of configuration as a (nested) dict."""
    mapping: Mapping

    if dataclasses.is_dataclass(data):
        mapping = dataclasses.asdict(data)
    else:
        mapping = cast(Mapping, data)

    return apply_nested_type_mapping(mapping, serialization_map)


def to_file(dataclass_instance, path: PathLike):
    """Write config to json, toml, or yaml file."""
    return write_dict_to_file(path, to_dict(dataclass_instance))
