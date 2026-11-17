from __future__ import annotations

import pytest
from dataclasses import dataclass

import cordage


@dataclass
class ModuleLevelConfig:
    name: str = "foo"


def test_future_annotations_import(global_config):
    def run(config: ModuleLevelConfig):
        assert config.name == "bar"

    cordage.run(
        run,
        ["--name", "bar"],
        config_only=True,
        global_config=global_config,
    )

@pytest.mark.skip
def test_future_annotations_import_hidden_config(global_config):
    """This test case would fail due to cordage being unable to recover
    HiddenConfig: It's a string due `from __future__ import annotations`
    and not in the module since it's defined only within the function.
    """

    @dataclass
    class HiddenConfig:
        name: str = "foo"

    def run(config: HiddenConfig):
        assert config.name == "bar"

    cordage.run(
        run,
        ["--name", "bar"],
        config_only=True,
        global_config=global_config,
    )
