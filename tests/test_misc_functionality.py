from dataclasses import dataclass
from time import sleep
from typing import List

import cordage
from cordage import Experiment, FunctionContext, Series, Trial


@dataclass
class Config:
    a: int = 42
    b: str = "test"


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


def test_trial_id_collision(global_config):
    global_config.trial_id_format = "experiment"
    global_config.output_dir_format = "{experiment_id}"

    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    for _ in range(1010):
        cordage.run(func, args=[], global_config=global_config)

    assert trial_store[7].experiment_id.endswith("_08")
    assert trial_store[42].experiment_id.endswith("_43")
    assert trial_store[123].experiment_id.endswith("__0124")
    assert trial_store[1009].experiment_id.endswith("__1010")


def test_return_value_capturing_dict(global_config):
    def func(config: Config, cordage_trial):
        return dict(a=1, b="string")

    trial = cordage.run(func, args=[], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    return_value = metadata.result

    assert len(return_value) == 2
    assert "a" in return_value
    assert "b" in return_value

    assert return_value["a"] == 1
    assert return_value["b"] == "string"


def test_return_value_capturing_float(global_config):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial, trial_store=trial_store):
        return 0.0

    trial = cordage.run(func, args=[], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    assert isinstance(metadata.result, float)
    assert metadata.result == 0.0


def test_return_value_capturing_unserializable(global_config):
    class SomeObject:
        pass

    def func(config: Config, cordage_trial):
        return SomeObject()

    trial = cordage.run(func, args=[], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    assert metadata.result is None


def test_return_config_class_casting(global_config):
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


def test_function_context_from_configuration(global_config):
    def func(config: Config):
        pass

    context = FunctionContext(func)

    trial = context.from_configuration(config=Config())

    assert isinstance(trial, Trial)

    series = context.from_configuration(base_config=Config(), series_spec={"a": [1, 2, 3]})

    assert isinstance(series, Series)

    assert len(series) == 3


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
