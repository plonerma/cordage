from typing import List

import pytest
from config_classes import NestedConfig as Config

import cordage
from cordage import Series


def test_trial_series_list(global_config, resources_path):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    config_file = resources_path / "series_list.yml"

    series = cordage.run(func, args=[str(config_file)], global_config=global_config)

    assert isinstance(series, Series)

    assert series.get_changing_fields() == {("alpha", "a"), ("alpha", "b"), ("beta", "a")}

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
        assert trial.output_dir == global_config.base_output_dir / "experiment" / str(i)


@pytest.mark.parametrize("letter", "abc")
def test_more_trial_series(global_config, resources_path, letter):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    config_file = resources_path / f"series_{letter}.toml"

    cordage.run(
        func, args=[str(config_file), "--alpha.b", "b_incorrect"], global_config=global_config
    )

    assert len(trial_store) == trial_store[0].config.alphas * trial_store[0].config.betas

    for i, trial in enumerate(trial_store):
        assert trial.config.alpha.b == "b1"
        assert trial.config.beta.a == "c" + str(1 + (i // trial_store[0].config.alphas))
        assert trial.config.alpha.a == (1 + (i % trial_store[0].config.alphas))

        assert trial.metadata.parent_dir is not None
        assert trial.metadata.parent_dir.parts[-1] == "experiment"

        if len(trial_store) <= 10:
            assert trial.output_dir == global_config.base_output_dir / "experiment" / f"{i}"

        else:
            assert trial.output_dir == global_config.base_output_dir / "experiment" / f"{i:02}"


def test_invalid_trial_series(global_config, resources_path):
    def func(config: Config, cordage_trial: cordage.Trial):
        pass

    config_file = resources_path / "series_invalid.json"

    with pytest.raises(ValueError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)


def test_trial_skipping(global_config, resources_path):
    trial_store: List[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
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
        assert trial.output_dir == global_config.base_output_dir / "experiment" / str(i)
