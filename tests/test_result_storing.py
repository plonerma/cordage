import re
from pathlib import Path
from typing import List

from config_classes import SimpleConfig as Config

import cordage
from cordage import Experiment


def test_dict_return_value(global_config):
    def func(config: Config, cordage_trial):  # noqa: ARG001
        return {"a": 1, "b": "string", "c": Path(".")}

    trial = cordage.run(func, args=[], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    return_value = metadata.result

    assert len(return_value) == 3
    assert "a" in return_value
    assert "b" in return_value
    assert "c" in return_value

    assert return_value["a"] == 1
    assert return_value["b"] == "string"
    assert return_value["c"] == "."


def test_path_return_value(global_config):
    def func(config: Config, cordage_trial):  # noqa: ARG001
        return {"a": 1, "b": "string", "c": Path(".")}

    trial = cordage.run(func, args=[], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    return_value = metadata.result

    assert len(return_value) == 3
    assert "a" in return_value
    assert "b" in return_value
    assert "c" in return_value

    assert return_value["a"] == 1
    assert return_value["b"] == "string"
    assert return_value["c"] == "."


def test_float_return_value(global_config):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial, trial_store=trial_store):  # noqa: ARG001
        return 0.0

    trial = cordage.run(func, args=[], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    assert isinstance(metadata.result, float)
    assert metadata.result == 0.0


def test_unserializable_return_value(global_config, capsys):
    class SomeObject:
        pass

    def func(config: Config, cordage_trial):  # noqa: ARG001
        return SomeObject()

    trial = cordage.run(func, args=[], global_config=global_config)

    captured = capsys.readouterr()

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    experiment = Experiment.from_path(metadata_path)
    metadata = experiment.metadata

    assert metadata.result is None

    pattern = r"^.+WARNING.+Cannot serialize .+SomeObject object"

    assert re.search(pattern, captured.err) is not None
