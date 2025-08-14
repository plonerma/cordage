import dataclasses
import logging
import typing
from collections.abc import Generator, Iterable, Mapping
from datetime import datetime, timedelta
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    Callable,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)

import dacite
import dacite.exceptions

if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance

import cordage.exceptions

logger = logging.getLogger("cordage")


TrialIndicesEntry = Union[tuple[Optional[int], Optional[int]], int]
TrialIndices = list[TrialIndicesEntry]


ConfigClass = TypeVar("ConfigClass", bound="DataclassInstance")

serialization_map: dict[type[Any], Callable[..., Any]] = {
    Path: str,
    datetime: datetime.isoformat,
    timedelta: lambda v: v.total_seconds(),
}

deserialization_map: dict[type[Any], Callable[..., Any]] = {
    datetime: lambda v: datetime.fromisoformat(v),
    timedelta: lambda v: timedelta(seconds=v),
}

types_to_cast: list[type[Any]] = [Path, float, bool, int, str, tuple]


def get_loader(extension: str) -> Callable:
    """Load module for reading a file with the given extension."""
    msg = f"Unrecognized file format: '.{extension}' (supported are .toml, .yaml, and .json)."
    if extension not in ("toml", "yaml", "yml", "yl", "json"):
        raise RuntimeError(msg)

    loader: Callable

    if extension == "toml":
        try:
            from toml import load as toml_loader  # noqa: PLC0415

            loader = toml_loader
        except ModuleNotFoundError as exc:
            msg = f"Package toml is required to read .{extension} files."
            raise RuntimeError(msg) from exc

    elif extension in ("yaml", "yml", "yl"):
        try:
            from yaml import safe_load as yaml_loader  # noqa: PLC0415

            loader = yaml_loader
        except ModuleNotFoundError as exc:
            msg = f"Package pyyaml is required to read .{extension} files."
            raise RuntimeError(msg) from exc
    else:
        try:
            from json import load as json_loader  # noqa: PLC0415

            loader = json_loader
        except ModuleNotFoundError as exc:
            msg = f"Package json is required to read .{extension} files."
            raise RuntimeError(msg) from exc

    return loader


def read_dict_from_file(path: PathLike) -> dict[str, Any]:
    """Read dictionary from toml, yaml, or json file.

    The file-type is inferred from the file extension.
    """
    extension = Path(path).suffix[1:]

    loader = get_loader(extension)

    with open(path, encoding="utf-8") as conf_file:
        return loader(conf_file)


def get_writer(extension: str) -> Callable:
    """Load module for reading a file with the given extension."""
    if extension not in ("toml", "yaml", "yml", "yl", "json"):
        msg = f"Unrecognized file format: '.{extension}' (supported are .toml, .yaml, and .json)."
        raise RuntimeError(msg)

    writer: Callable

    if extension == "toml":
        try:
            from toml import dump as toml_dump  # noqa: PLC0415

            writer = toml_dump
        except ModuleNotFoundError as exc:
            msg = f"Package toml is required to read .{extension} files."
            raise RuntimeError(msg) from exc

    elif extension in ("yaml", "yml", "yl"):
        try:
            from yaml import dump as yaml_dump  # noqa: PLC0415

            writer = yaml_dump
        except ModuleNotFoundError as exc:
            msg = f"Package pyyaml is required to write .{extension} files."
            raise RuntimeError(msg) from exc
    else:
        try:
            from json import dump as json_dump  # noqa: PLC0415

            writer = json_dump
        except ModuleNotFoundError as exc:
            msg = f"Package json is required to read .{extension} files."
            raise RuntimeError(msg) from exc

    return writer


def write_dict_to_file(path: PathLike, data: Mapping[str, Any]):
    """Write dictionary to toml, yaml, or json file.

    The file-type is inferred from the file extension.
    """
    extension = Path(path).suffix[1:]

    writer = get_writer(extension)

    with open(path, "w", encoding="utf-8") as conf_file:
        return writer(data, conf_file)


# no separator
@overload
def flattened_items(
    nested_dict: dict[Any, Any], *, sep: Literal[None] = None, prefix: tuple[Any, ...] = ()
) -> Generator[tuple[tuple[Any, ...], Any], None, None]: ...


# spearator given
@overload
def flattened_items(
    nested_dict: dict[Any, Any], *, sep: str, prefix: tuple[str, ...] = ()
) -> Generator[tuple[str, Any], None, None]: ...


def flattened_items(
    nested_dict: dict,
    *,
    sep: Optional[str] = None,
    prefix: tuple[Any, ...] = (),
) -> Generator[Union[tuple[str, Any], tuple[tuple[Any, ...], Any]], None, None]:
    """Iter over all items in a nested dictionary."""
    for k, v in nested_dict.items():
        flat_k: tuple = (
            *prefix,
            k,
        )

        if isinstance(v, dict):
            for ik, iv in flattened_items(v, prefix=flat_k):
                if sep is None:
                    yield ik, iv
                else:
                    yield sep.join(ik), iv
        elif sep is None:
            yield flat_k, v
        else:
            yield sep.join(flat_k), v


def nested_update(target_dict: dict, update_dict: Mapping):
    """Update a nested dictionary."""
    for k, v in update_dict.items():
        if isinstance(v, Mapping) and k in target_dict and isinstance(target_dict[k], dict):
            nested_update(target_dict[k], v)
        else:
            target_dict[k] = v

    return target_dict


def nest_items(flat_items: Iterable[tuple[Union[str, tuple[Any, ...]], Any]]) -> dict[str, Any]:
    """Unflatten a dict.

    If any keys contain '.', sub-dicts will be created.
    """
    nested_dict: dict[str, Any] = {}
    dicts_to_nest: list[str] = []

    for k, v in flat_items:
        k_tuple: tuple[Any, ...]
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


def from_dict(data_class: type[ConfigClass], data: Mapping, *, strict: bool = True) -> ConfigClass:
    config = dacite.Config(cast=types_to_cast, type_hooks=deserialization_map, strict=strict)
    try:
        return dacite.from_dict(data_class, data, config)
    except dacite.exceptions.WrongTypeError as e:
        msg = (
            f"Configuration incomplete: {e}.\n"
            f"Use '{e.field_path}' to specify the field via the command line or set the field in "
            "a configuration file."
        )
        raise cordage.exceptions.WrongTypeError(msg) from e

    except dacite.exceptions.MissingValueError as e:
        msg = (
            f"Configuration incomplete: {e}.\n"
            f"Use '{e.field_path}' to specify the field via the command line or set the field in "
            "a configuration file."
        )
        raise cordage.exceptions.MissingValueError(msg) from e

    except dacite.exceptions.DaciteError as e:
        msg = f"Configuration incorrect: {e}."
        raise cordage.exceptions.CordageError(msg) from e


def from_file(config_cls: type[ConfigClass], path: PathLike, **kwargs) -> ConfigClass:
    data: Mapping = read_dict_from_file(path)
    return from_dict(config_cls, data, **kwargs)


def apply_nested_type_mapping(data: Mapping, type_mapping: Mapping[type, Callable]):
    result = {}

    for k, v in data.items():
        result[k] = v

        if isinstance(v, Mapping):
            result[k] = apply_nested_type_mapping(v, type_mapping)

        else:
            for t, func in type_mapping.items():
                if isinstance(v, t):
                    result[k] = func(v)
                    break

    return result


def get_nested_field(dataclass_instance, field_name: str) -> Any:
    assert dataclasses.is_dataclass(dataclass_instance)

    value = dataclass_instance

    for k in field_name.split("."):
        value = getattr(value, k)

    return value


def set_nested_field(dataclass_instance, field_name: str, value: Any):
    *first_keys, last_key = field_name.split(".")

    obj = dataclass_instance
    for k in first_keys:
        obj = getattr(obj, k)

    setattr(obj, last_key, value)


def to_dict(data: Union[ConfigClass, Mapping]) -> dict:
    """Represent the fields and values of configuration as a dict."""
    mapping: Mapping

    if dataclasses.is_dataclass(data):
        mapping = dataclasses.asdict(data)
    else:
        mapping = cast(Mapping, data)

    return apply_nested_type_mapping(mapping, serialization_map)


def to_file(dataclass_instance, path: PathLike):
    """Write config to json, toml, or yaml file."""
    return write_dict_to_file(path, to_dict(dataclass_instance))


def config_output_dir_type(
    config_cls: type["DataclassInstance"], param_name_output_dir: str
) -> Union[type[str], type[Path], None]:
    for field in dataclasses.fields(config_cls):
        if field.name == param_name_output_dir:
            if field.type in (str, "str"):
                return str
            elif field.type in (Path, "Path"):
                return Path
            else:
                msg = f"You must annotate `output_dir` as str or Path: got {field.type}."
                raise TypeError(msg)
    return None
