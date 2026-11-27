import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

import cordage
from cordage import GlobalConfig
from cordage.util import to_dict


def test_global_config(global_config: "DataclassInstance"):
    assert dataclasses.is_dataclass(global_config)

    json.dumps(to_dict(global_config))


def test_format_string_validation(global_config):
    # This should be valid
    _ = GlobalConfig()

    with pytest.raises(KeyError):
        _ = dataclasses.replace(global_config, output_dir_format="{non_existing_field}")

    _ = dataclasses.replace(global_config, output_dir_format="{collision_suffix}")

    with pytest.raises(ValueError):
        _ = dataclasses.replace(global_config, output_dir_format="{function:%Y}")


@dataclasses.dataclass
class OuterConfig:
    value: int = 1


@dataclasses.dataclass
class InnerConfig:
    value: int = 1


def nested_func(config: InnerConfig):
    return {"ok": True, "value": config.value}


def _metadata(run_dir: Path) -> dict:
    with (run_dir / "cordage.json").open() as f:
        return json.load(f)


def test_nested_run_inherits_outer_global_config(global_config):
    global_config = dataclasses.replace(
        global_config, output_dir_format="parent{collision_suffix}"
    )

    def outer_func(config: OuterConfig):
        inner = cordage.run(nested_func, args=["--value", "1"])
        return {"inner_dir": str(inner.output_dir), "value": config.value}

    outer = cordage.run(
        outer_func, args=["--value", "1"], config_cls=OuterConfig, global_config=global_config
    )

    inner_dir = Path(outer.result["inner_dir"])

    outer_meta = _metadata(outer.output_dir)
    inner_meta = _metadata(inner_dir)

    assert inner_meta["global_config"]["base_output_dir"] == str(global_config.base_output_dir)
    assert (
        inner_meta["global_config"]["base_output_dir"]
        == outer_meta["global_config"]["base_output_dir"]
    )
    assert inner_dir.parent == global_config.base_output_dir
    assert inner_meta["parent_dir"] == str(outer.output_dir)  # already works today


def test_explicit_nested_global_config_still_wins(global_config, tmp_path):
    global_config = dataclasses.replace(
        global_config, output_dir_format="parent{collision_suffix}"
    )

    other = dataclasses.replace(
        cordage.GlobalConfig(),
        base_output_dir=tmp_path / "other-base",
        output_dir_format="explicit{collision_suffix}",
    )

    def outer_with_explicit(config: OuterConfig):
        inner = cordage.run(
            nested_func,
            args=["--value", "1"],
            global_config=other,
        )
        return {"inner_dir": str(inner.output_dir), "value": config.value}

    outer = cordage.run(
        outer_with_explicit,
        args=["--value", "1"],
        config_cls=OuterConfig,
        global_config=global_config,
    )
    inner_meta = _metadata(Path(outer.result["inner_dir"]))
    assert inner_meta["global_config"]["base_output_dir"] == str(other.base_output_dir)
