from dataclasses import dataclass
from typing import List

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


def test_trial_series_a(global_config, resources_path):
    global_config.trial_id_format = "trial"
    global_config.output_dir_format = "{trial_id}"

    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / "test_config_series_a.yml"

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


def test_trial_series_b(global_config, resources_path):
    global_config.trial_id_format = "trial"
    global_config.output_dir_format = "{trial_id}"

    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):
        trial_store.append(cordage_trial)

    config_file = resources_path / "test_config_series_b.toml"

    cordage.run(func, args=[str(config_file), "--alpha.b", "b_incorrect"], global_config=global_config)

    assert len(trial_store) == 6

    for i, trial in enumerate(trial_store):
        assert trial.config.alpha.b == "b1"
        assert trial.config.beta.a == "c" + str(1 + (i // 3))
        assert trial.config.alpha.a == (1 + (i % 3))
