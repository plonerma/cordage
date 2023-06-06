from dataclasses import dataclass
from time import sleep
from typing import List

import cordage
from cordage import Experiment


@dataclass
class Config:
    a: int = 42
    b: str = "test"


def test_timing(global_config):
    def func(config: Config, cordage_trial: cordage.Trial):
        sleep(1)

    series = cordage.run(func, args=[], global_config=global_config)

    trial = next(iter(series))

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

    series = cordage.run(func, args=[], global_config=global_config)
    trial = next(iter(series))

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

    series = cordage.run(func, args=[], global_config=global_config)
    trial = next(iter(series))

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

    series = cordage.run(func, args=[], global_config=global_config)

    trial = next(iter(series))

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    assert metadata.result is None
