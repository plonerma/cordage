from time import sleep
from typing import List

import pytest
from config_classes import SimpleConfig

import cordage
from cordage import Experiment, FunctionContext, Series, Trial


@pytest.mark.timeout(2)
def test_timing(global_config):
    def func(config: SimpleConfig, cordage_trial: cordage.Trial):  # noqa: ARG001
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


@pytest.mark.timeout(60)
def test_trial_id_collision(global_config):
    trial_store: List[cordage.Trial] = []

    def func(config: SimpleConfig, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    for _ in range(1010):
        cordage.run(func, args=[], global_config=global_config)

    assert str(trial_store[7].output_dir).endswith("_08")
    assert str(trial_store[42].output_dir).endswith("_43")
    assert str(trial_store[123].output_dir).endswith("__0124")
    assert str(trial_store[1009].output_dir).endswith("__1010")


@pytest.mark.timeout(1)
def test_function_context_from_configuration(global_config):
    def func(config: SimpleConfig):
        pass

    context = FunctionContext(func, global_config=global_config)

    trial = context.from_configuration(config=SimpleConfig())

    assert isinstance(trial, Trial)

    series = context.from_configuration(base_config={}, series_spec={"a": [1, 2, 3]})

    assert isinstance(series, Series)

    assert len(series) == 3


@pytest.mark.timeout(1)
def test_output_dir_path_correction(monkeypatch, tmp_path):
    def func(config: SimpleConfig):
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


def test_config_only(global_config):
    def func(config: SimpleConfig):
        pass

    cordage.run(func, args=[], global_config=global_config, config_only=True)

    # since no outputdir is assigned, the base dir should not be created
    assert not global_config.base_output_dir.exists()


def test_config_only_func_params(global_config):
    def func(config: SimpleConfig, output_dir):
        pass

    with pytest.raises(TypeError):
        # function should not need an output_dir
        cordage.run(func, args=[], global_config=global_config, config_only=True)
