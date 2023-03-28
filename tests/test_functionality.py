from dataclasses import dataclass
from time import sleep
from typing import List

import cordage
from cordage import Experiment


@dataclass
class Config:
    a: int = 42
    b: str = "test"


def test_metadata(global_config):
    trial_store: List[cordage.Trial] = []

    global_config.central_metadata.use = True

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)
        sleep(1)

    cordage.run(func, args=[], global_config=global_config)

    trial = trial_store[0]

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

    rel_dir = trial.output_dir.relative_to(global_config.base_output_dir)

    central_metadata = global_config.central_metadata.path / rel_dir / "metadata.json"

    assert central_metadata.exists()

    central_annotations = global_config.central_metadata.path / rel_dir / "annotations.json"

    assert central_annotations.exists()

    experiment = Experiment.from_path(central_metadata)
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
