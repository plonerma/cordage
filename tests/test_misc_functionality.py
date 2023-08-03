import logging
from dataclasses import dataclass
from time import sleep
from typing import List, cast

import pytest

import cordage
from cordage import Experiment, FunctionContext, Series, Trial


@dataclass
class Config:
    a: int = 42
    b: str = "test"


@pytest.mark.timeout(2)
def test_timing(global_config):
    def func(config: Config, cordage_trial: cordage.Trial):
        sleep(1)

    trial = cordage.run(func, args=[], global_config=global_config)

    assert trial.metadata.duration.total_seconds() < 1.1
    assert trial.metadata.duration.total_seconds() > 0.9
    assert trial.metadata.status == "complete"

    metadata_path = trial.output_dir / "cordage.json"

    assert trial.metadata_path == metadata_path
    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    assert metadata.duration.total_seconds() < 1.1
    assert metadata.duration.total_seconds() > 0.9
    assert metadata.status == "complete"


@pytest.mark.timeout(10)
def test_trial_id_collision(global_config):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    for _ in range(1010):
        cordage.run(func, args=[], global_config=global_config)

    assert str(trial_store[7].output_dir).endswith("_08")
    assert str(trial_store[42].output_dir).endswith("_43")
    assert str(trial_store[123].output_dir).endswith("__0124")
    assert str(trial_store[1009].output_dir).endswith("__1010")


@pytest.mark.timeout(1)
def test_metadata_loading_config_class_casting(global_config):
    def func(config: Config):
        pass

    trial = cordage.run(func, args=["--a", "1", "--b", "2"], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    # try loading as dict
    experiment = Experiment.from_path(metadata_path)
    assert isinstance(experiment.config, dict)
    assert experiment.config["a"] == 1
    assert experiment.config["b"] == "2"

    # try loading with config class
    experiment = Experiment.from_path(metadata_path, config_cls=Config)
    assert isinstance(experiment.config, Config)
    assert experiment.config.a == 1
    assert experiment.config.b == "2"


@pytest.mark.timeout(1)
def test_function_context_from_configuration(global_config):
    def func(config: Config):
        pass

    context = FunctionContext(func)

    trial = context.from_configuration(config=Config())

    assert isinstance(trial, Trial)

    series = context.from_configuration(base_config=Config(), series_spec={"a": [1, 2, 3]})

    assert isinstance(series, Series)

    assert len(series) == 3


@pytest.mark.timeout(1)
def test_output_dir_path_correction(global_config, monkeypatch, tmp_path):
    def func(config: Config):
        pass

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.chdir(run_dir)

    exp = cordage.run(func, args=[])

    output_dir = exp.output_dir.resolve()

    test_dir = tmp_path / "test"
    test_dir.mkdir()
    monkeypatch.chdir(test_dir)

    all_exp = Experiment.all_from_path("../run/results")

    assert len(all_exp) == 1
    assert str(all_exp[0].output_dir).startswith("..")
    assert all_exp[0].output_dir.resolve() == output_dir
    assert all_exp[0].result is None


@pytest.mark.timeout(1)
def test_nested_trial_logging(global_config, capsys):
    def foo(config: Config):
        log = logging.getLogger("test-logger")

        log.warning("in_inner_trial")

    def bar(config: Config, cordage_trial):
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

    def bar(config: Config, cordage_trial):
        log = logging.getLogger("test-logger")

        log.warning("before_inner_trial")

        inner_series = cordage.run(foo, args=[str(resources_path / "series_simple.yaml")], global_config=global_config)

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
