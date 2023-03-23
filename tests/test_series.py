from dataclasses import dataclass
from typing import List

import pytest

import cordage


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

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / "test_config_series_list.yml"

    cordage.run(func, args=[str(config_file)], global_config=global_config)

    assert len(trial_store) == 3
    assert trial_store[0].config.alpha.a == 1
    assert trial_store[0].config.alpha.b == "b1"
    assert trial_store[0].config.beta.a == "c1"
    assert trial_store[1].config.alpha.a == 2
    assert trial_store[1].config.alpha.b == "b2"
    assert trial_store[1].config.beta.a == "c2"
    assert trial_store[2].config.alpha.a == 3
    assert trial_store[2].config.alpha.b == "b3"
    assert trial_store[2].config.beta.a == "c3"

    for i, trial in enumerate(trial_store):
        assert trial.output_dir == global_config.base_output_dir / "experiment" / str(i + 1)


@pytest.mark.parametrize("letter", "abc")
def test_more_trial_series(global_config, resources_path, letter):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / f"test_config_series_{letter}.toml"

    cordage.run(func, args=[str(config_file), "--alpha.b", "b_incorrect"], global_config=global_config)

    assert len(trial_store) == trial_store[0].config.alphas * trial_store[0].config.betas

    for i, trial in enumerate(trial_store):
        assert trial.config.alpha.b == "b1"
        assert trial.config.beta.a == "c" + str(1 + (i // trial_store[0].config.alphas))
        assert trial.config.alpha.a == (1 + (i % trial_store[0].config.alphas))

        assert trial.metadata["series_id"] == "experiment"

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

    config_file = resources_path / "test_config_series_invalid.json"

    with pytest.raises(ValueError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)

    assert (
        not global_config.base_output_dir.exists()
    ), "Since the configuration is invalid, the series should not be started and hence no output be created"
