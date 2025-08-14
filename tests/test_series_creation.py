import math
from dataclasses import replace

import pytest
from config_classes import NestedConfig as Config

import cordage
from cordage import Series
from cordage.context import TrialIndexMixin


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


@pytest.mark.parametrize("zero_pad", (True, False))
@pytest.mark.parametrize("letter", "abc")
def test_more_trial_series(global_config, resources_path, letter, zero_pad):
    global_config = replace(global_config, zero_pad_trial_output_dir=zero_pad)

    trial_store: list[cordage.Trial] = []

    def func(config: Config, cordage_trial: cordage.Trial, trial_store=trial_store):  # noqa: ARG001
        trial_store.append(cordage_trial)

    config_file = resources_path / f"series_{letter}.toml"

    cordage.run(
        func,
        args=[str(config_file), "--alpha.b", "b_incorrect"],
        global_config=global_config,
    )

    assert len(trial_store) == trial_store[0].config.alphas * trial_store[0].config.betas

    for i, trial in enumerate(trial_store, start=1):
        assert trial.config.alpha.b == "b1"
        assert trial.config.beta.a == "c" + str(math.ceil(i / trial_store[0].config.alphas))
        assert trial.config.alpha.a == 1 + ((i - 1) % trial_store[0].config.alphas)

        assert trial.metadata.parent_dir is not None
        assert trial.metadata.parent_dir.parts[-1] == "experiment"

        if len(trial_store) < 10 or not zero_pad:
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
        (("--trial-index", "4-"), (4, 5)),
        (("--trial-index", "2"), (2,)),
        (("--trial-index", "2, 3"), (2, 3)),
        (("--trial-index", "1, 3-5"), (1, 3, 4, 5)),
        (("--trial-index", "-3"), (1, 2, 3)),
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


@pytest.mark.parametrize(
    "text,match",
    [
        ("1-5", (1, 5)),
        (" 1-5", (1, 5)),
        ("1 -5", (1, 5)),
        ("1- 5 ", (1, 5)),
        ("7", 7),
        (" 6", 6),
        ("7 ", 7),
        (" 4 ", 4),
        ("7 ", 7),
        (" 6", 6),
        ("2-78", (2, 78)),
        ("5-", (5, None)),
        ("-8", (None, 8)),
        ("10-20", (10, 20)),
        ("-", False),
        ("-5-8", False),
        ("a-b", False),
        ("3-4-5", False),
    ],
)
def test_trial_range_entry_matching(text, match):
    m = TrialIndexMixin()
    if match is False:
        with pytest.raises(ValueError):
            m.match_trial_range_entry(text)

    else:
        assert m.match_trial_range_entry(text) == match


@pytest.mark.parametrize(
    "text,match",
    [
        ("1-5, 2-78, -8,7", [(1, 5), (2, 78), (None, 8), 7]),
        ("7, 6, 3", [7, 6, 3]),
        ("10-20, 1, 2, 5-6", [(10, 20), 1, 2, (5, 6)]),
        ("a, a-b, 4", False),
        ("1, 3-4-5, 5, 3", False),
    ],
)
def test_trial_range_matching(text, match):
    m = TrialIndexMixin()
    if not match:
        with pytest.raises(ValueError):
            m.match_trial_range(text)

    else:
        assert m.match_trial_range(text) == match
