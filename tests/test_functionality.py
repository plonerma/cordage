import json
from dataclasses import dataclass
from time import sleep
from typing import List

import cordage


@dataclass
class Config:
    a: int = 42
    b: str = "test"


def test_metadata(global_config):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)
        sleep(1)

    cordage.run(func, args=[], global_config=global_config)

    trial = trial_store[0]

    assert trial.metadata["duration"].total_seconds() < 1.1
    assert trial.metadata["duration"].total_seconds() > 0.9
    assert trial.metadata["status"] == "complete"

    metadata_path = trial.output_dir / "cordage.json"

    assert trial.metadata_path == metadata_path
    assert metadata_path.exists()

    with open(trial.output_dir / "cordage.json", encoding="utf-8") as f:
        metadata = json.load(f)

    assert metadata["duration"] < 1.1
    assert metadata["duration"] > 0.9
    assert metadata["status"] == "complete"

    rel_dir = trial.output_dir.relative_to(global_config.base_output_dir)

    central_metadata = global_config.central_metadata.path / rel_dir / "metadata.json"

    assert central_metadata.exists()

    with open(central_metadata, encoding="utf-8") as f:
        metadata = json.load(f)

    assert metadata["duration"] < 1.1
    assert metadata["duration"] > 0.9
    assert metadata["status"] == "complete"


def test_trial_id_collision(global_config):
    global_config.trial_id_format = "trial"
    global_config.output_dir_format = "{trial_id}"

    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    for _ in range(1010):
        cordage.run(func, args=[], global_config=global_config)

    assert trial_store[7].trial_id.endswith("_07")
    assert trial_store[42].trial_id.endswith("_42")
    assert trial_store[123].trial_id.endswith("__0123")
    assert trial_store[1009].trial_id.endswith("__1009")
