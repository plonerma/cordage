from dataclasses import dataclass
from datetime import datetime
from typing import List

import pytest

import cordage
from cordage import Experiment, Series, Trial
from cordage.util import logger


@dataclass
class AlphaConfig:
    a: int
    b: str = "b_value"


@dataclass
class BetaConfig:
    a: str
    b: int = 0


@dataclass
class Config:
    """config_description.

    :param a: a_help_str
    :param d: wrong_help_text
    """

    alpha: AlphaConfig
    beta: BetaConfig = BetaConfig(a="a_value")

    a: str = "e_default"

    # these fields are used in test_more_trial_series for checking the configuration and output dir etc.
    alphas: int = 1
    betas: int = 1


def test_trial_series_list(global_config, resources_path):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, cordage_series, trial_store=trial_store):
        trial_store.append(cordage_trial)

        assert cordage_series.get_changing_fields() == {("alpha", "a"), ("alpha", "b"), ("beta", "a")}

    config_file = resources_path / "series_list.yml"

    cordage.run(func, args=[str(config_file)], global_config=global_config)

    assert len(trial_store) == 3
    assert trial_store[0].config.alpha.a == 1
    assert trial_store[0].config.alpha.b == "b1"
    assert trial_store[0].config.beta.a == "c1"
    assert trial_store[0].metadata.additional_info["trial_index"] == 0
    assert trial_store[1].config.alpha.a == 2
    assert trial_store[1].config.alpha.b == "b2"
    assert trial_store[1].config.beta.a == "c2"
    assert trial_store[1].metadata.additional_info["trial_index"] == 1
    assert trial_store[2].config.alpha.a == 3
    assert trial_store[2].config.alpha.b == "b3"
    assert trial_store[2].config.beta.a == "c3"
    assert trial_store[2].metadata.additional_info["trial_index"] == 2

    for i, trial in enumerate(trial_store):
        assert trial.output_dir == global_config.base_output_dir / "experiment" / str(i + 1)


def test_trial_series_loading(global_config, resources_path, capsys):
    def func(config: Config, cordage_trial: cordage.Trial):
        cordage_trial.add_tag(config.alpha.b)

        logger.warning("Trial with alpha.b=%s", config.alpha.b)

    config_file = resources_path / "series_list.yml"

    cordage.run(func, args=[str(config_file)], global_config=global_config)

    series = Experiment.all_from_path(global_config.base_output_dir)[0]

    assert isinstance(series, Series)

    trial_store = [trial.synchronize() for trial in series]

    assert len(trial_store) == 3

    assert all(isinstance(trial, Trial) for trial in trial_store)

    # test log stream
    captured = capsys.readouterr()

    for i, captured_line in enumerate(captured.err.strip().split("\n")):
        assert f"Trial with alpha.b=b{i+1}" in captured_line

    # after loading the series trials, the configs are merely nested dictionaries
    for i, trial in enumerate(trial_store):
        assert trial.config["alpha"]["b"] == f"b{i+1}"
        assert trial.has_tag(f"b{i+1}")

        assert isinstance(trial.metadata.start_time, datetime)

        # test logging was performed correctly
        assert trial.log_path.exists()

        with trial.log_path.open("r") as fp:
            log_lines = [line for line in fp]

            assert len(log_lines) == 1, "\n".join(log_lines)

            for j in range(3):
                expected_log_partial = f"Trial with alpha.b=b{j+1}"

                assert (expected_log_partial in log_lines[0]) == (i == j)


@pytest.mark.parametrize("letter", "abc")
def test_more_trial_series(global_config, resources_path, letter):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / f"series_{letter}.toml"

    cordage.run(func, args=[str(config_file), "--alpha.b", "b_incorrect"], global_config=global_config)

    assert len(trial_store) == trial_store[0].config.alphas * trial_store[0].config.betas

    for i, trial in enumerate(trial_store):
        assert trial.config.alpha.b == "b1"
        assert trial.config.beta.a == "c" + str(1 + (i // trial_store[0].config.alphas))
        assert trial.config.alpha.a == (1 + (i % trial_store[0].config.alphas))

        assert trial.metadata.additional_info["series_id"] == "experiment"

        if len(trial_store) <= 10:
            assert trial.experiment_id == f"experiment/{i+1}"
            assert trial.output_dir == global_config.base_output_dir / "experiment" / f"{i+1}"

        else:
            assert trial.experiment_id == f"experiment/{i+1:02}"
            assert trial.output_dir == global_config.base_output_dir / "experiment" / f"{i+1:02}"


def test_invalid_trial_series(global_config, resources_path):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / "series_invalid.json"

    with pytest.raises(ValueError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)

    assert (
        not global_config.base_output_dir.exists()
    ), "Since the configuration is invalid, the series should not be started and hence no output be created"


def test_trial_skipping(global_config, resources_path):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / "series_list.yml"

    cordage.run(func, args=[str(config_file), "--series-skip", "1"], global_config=global_config)

    assert len(trial_store) == 2

    assert trial_store[0].metadata.additional_info["trial_index"] == 1
    assert trial_store[0].config.alpha.a == 2
    assert trial_store[0].config.alpha.b == "b2"
    assert trial_store[0].config.beta.a == "c2"

    assert trial_store[1].metadata.additional_info["trial_index"] == 2
    assert trial_store[1].config.alpha.a == 3
    assert trial_store[1].config.alpha.b == "b3"
    assert trial_store[1].config.beta.a == "c3"

    for i, trial in enumerate(trial_store, start=1):
        assert trial.output_dir == global_config.base_output_dir / "experiment" / str(i + 1)
