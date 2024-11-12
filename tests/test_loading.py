from datetime import datetime

import pytest
from config_classes import NestedConfig, SimpleConfig

import cordage
from cordage import Experiment, Series, Trial
from cordage.util import logger


@pytest.mark.timeout(1)
def test_metadata_loading_config_class_casting(global_config):
    def func(config: SimpleConfig):
        pass

    trial = cordage.run(func, args=["--a", "1", "--b", "2"], global_config=global_config)

    metadata_path = trial.output_dir / "cordage.json"

    assert metadata_path.exists()

    # try loading as dict
    experiment = Experiment.from_path(metadata_path)
    assert isinstance(experiment, Trial)
    with pytest.raises(AttributeError):
        assert isinstance(experiment.config, dict)
    assert isinstance(experiment.metadata.configuration, dict)
    assert experiment.metadata.configuration["a"] == 1
    assert experiment.metadata.configuration["b"] == "2"

    # try loading with config class
    experiment = Experiment.from_path(metadata_path, config_cls=SimpleConfig)
    assert isinstance(experiment, Trial)
    assert isinstance(experiment.config, SimpleConfig)
    assert experiment.config.a == 1
    assert experiment.config.b == "2"


def test_trial_series_loading(global_config, resources_path, capsys):
    def func(config: NestedConfig, cordage_trial: cordage.Trial):
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

    i = 1

    for captured_line in captured.err.strip().split("\n"):
        assert f"Trial with alpha.b=b{i-1}" not in captured_line

        if f"Trial with alpha.b=b{i}" in captured_line:
            i += 1

    assert i == 4

    # after loading the series trials, the configs are merely nested
    # dictionaries
    for i, trial in enumerate(trial_store):
        with pytest.raises(AttributeError):
            assert isinstance(trial.config, dict)

        config = trial.metadata.configuration

        assert config["alpha"]["b"] == f"b{i+1}"
        assert trial.has_tag(f"b{i+1}")

        assert isinstance(trial.metadata.start_time, datetime)

        # test logging was performed correctly
        assert trial.log_path.exists()

        with trial.log_path.open("r") as fp:
            log_lines = list(fp)

            for j in range(3):
                expected_log_partial = f"Trial with alpha.b=b{j+1}"

                if i == j:
                    assert any(expected_log_partial in line for line in log_lines)
                else:
                    assert not any(expected_log_partial in line for line in log_lines)


def test_trial_series_loading_with_config_class(global_config, resources_path):
    def func(config: NestedConfig, cordage_trial: cordage.Trial):
        cordage_trial.add_tag(config.alpha.b)

        logger.warning("Trial with alpha.b=%s", config.alpha.b)

    config_file = resources_path / "series_list.yml"

    series = cordage.run(func, args=[str(config_file)], global_config=global_config)

    output_dir = series.output_dir

    series = Experiment.from_path(output_dir, config_cls=NestedConfig)

    assert isinstance(series, Series)

    trial_store = [trial.synchronize() for trial in series]

    assert len(trial_store) == 3

    assert all(isinstance(trial, Trial) for trial in trial_store)

    # after loading the series trials, the configs are merely nested
    # dictionaries
    for i, trial in enumerate(trial_store):
        assert isinstance(trial.config, NestedConfig)
        assert trial.config.alpha.b == f"b{i+1}"
