import logging
from typing import cast

import pytest
from config_classes import SimpleConfig as Config

import cordage
from cordage import Series


@pytest.mark.timeout(1)
def test_nested_trial_logging(global_config, capsys):
    def foo(config: Config):  # noqa: ARG001
        log = logging.getLogger("test-logger")

        log.warning("in_inner_trial")

    def bar(config: Config, cordage_trial):  # noqa: ARG001
        log = logging.getLogger("test-logger")

        log.warning("before_inner_trial")

        inner_trial = cordage.run(foo, args=[], global_config=global_config)

        log.warning("after_inner_trial")

        assert inner_trial.parent_dir == cordage_trial.output_dir

    cordage.run(bar, args=[], global_config=global_config)

    captured = capsys.readouterr()

    # 42 should appear exactly once in the resulting log output
    assert captured.err.count("in_inner_trial") == 1
    assert captured.err.find("before_inner_trial") < captured.err.find("in_inner_trial")
    assert captured.err.find("in_inner_trial") < captured.err.find("after_inner_trial")


@pytest.mark.timeout(1)
def test_nested_series_logging(global_config, capsys, resources_path):
    def foo(config: Config):
        log = logging.getLogger("test-logger")

        log.warning(f"in_inner_trial_{config.a}")

    def bar(config: Config, cordage_trial):  # noqa: ARG001
        log = logging.getLogger("test-logger")

        log.warning("before_inner_trial")

        inner_series = cordage.run(
            foo, args=[str(resources_path / "series_simple.yaml")], global_config=global_config
        )

        log.warning("after_inner_trial")

        assert inner_series.parent_dir == cordage_trial.output_dir
        for trial in cast(Series, inner_series):
            assert trial.parent_dir == inner_series.output_dir

    cordage.run(bar, args=[], global_config=global_config)

    captured = capsys.readouterr()

    # 42 should appear exactly once in the resulting log output
    assert captured.err.count("in_inner_trial") == 3
    assert captured.err.find("before_inner_trial") < captured.err.find("inner_trial_1")
    assert captured.err.find("in_inner_trial_1") < captured.err.find("in_inner_trial_2")
    assert captured.err.find("in_inner_trial_2") < captured.err.find("in_inner_trial_3")
    assert captured.err.find("in_inner_trial_3") < captured.err.find("after_inner_trial")
