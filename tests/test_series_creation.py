import math

import pytest
from config_classes import NestedConfig as Config

import cordage
from cordage import Series


def test_trial_series_list(global_config, resources_path):
    trial_store: list[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    config_file = resources_path / "series_list.yml"

    series = cordage.run(func, args=[str(config_file)], global_config=global_config)

    assert isinstance(series, Series)

    assert series.get_changing_fields() == {("alpha", "a"), ("alpha", "b"), ("beta", "a")}

    for i, t in zip(range(1, 6), trial_store):
        assert t.metadata.additional_info["trial_index"] == i
        assert t.config.alpha.a == i
        assert t.config.alpha.b == f"b{i}"
        assert t.config.beta.a == f"c{i}"

        assert t.output_dir == global_config.base_output_dir / "experiment" / str(i)


@pytest.mark.parametrize("letter", "abc")
def test_more_trial_series(global_config, resources_path, letter):
    trial_store: list[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    config_file = resources_path / f"series_{letter}.toml"

    cordage.run(
        func, args=[str(config_file), "--alpha.b", "b_incorrect"], global_config=global_config
    )

    assert len(trial_store) == trial_store[0].config.alphas * trial_store[0].config.betas

    for i, trial in enumerate(trial_store, start=1):
        assert trial.config.alpha.b == "b1"
        assert trial.config.beta.a == "c" + str(math.ceil(i / trial_store[0].config.alphas))
        assert trial.config.alpha.a == 1 + ((i - 1) % trial_store[0].config.alphas)

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


@pytest.mark.parametrize(
    "args, expected_trials",
    [
        (("--series-skip", "3"), (4, 5)),
        (("--series-trial", "2"), (2,)),
    ],
)
def test_partial_series_execution(global_config, resources_path, expected_trials, args):
    trial_store: list[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    config_file = resources_path / "series_list.yml"

    cordage.run(func, args=[str(config_file), *args], global_config=global_config)

    assert len(trial_store) == len(expected_trials)

    for i, t in zip(expected_trials, trial_store):
        assert t.metadata.additional_info["trial_index"] == i
        assert t.config.alpha.a == i
        assert t.config.alpha.b == f"b{i}"
        assert t.config.beta.a == f"c{i}"

        assert t.output_dir == global_config.base_output_dir / "experiment" / str(i)
