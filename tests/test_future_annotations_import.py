from __future__ import annotations

from dataclasses import dataclass

import cordage


def test_future_annotations_import(global_config):

    @dataclass
    class Config:
        name: str = "foo"

    def run(config: Config):
        assert config.name == "bar"

    cordage.run(
        run,
        ["--name", "bar"],
        config_only=True,
        global_config=global_config,
    )
