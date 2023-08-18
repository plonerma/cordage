import pytest
from config_classes import LongConfig, SimpleConfig

import cordage


def test_manual_output_dir(global_config, tmp_path):
    def func(config: SimpleConfig):
        pass

    experiment = cordage.run(
        func, args=["--output-dir", str(tmp_path / "some_specific_output_dir")], global_config=global_config
    )

    assert experiment.output_dir == tmp_path / "some_specific_output_dir"


def test_manual_output_dir_for_series(global_config, tmp_path, resources_path):
    def func(config: SimpleConfig, cordage_trial, output_dir):
        assert "trial_index" in cordage_trial.metadata.additional_info
        assert output_dir == tmp_path / "some_specific_output_dir" / str(
            cordage_trial.metadata.additional_info["trial_index"]
        )

    cordage.run(
        func,
        args=["--output-dir", str(tmp_path / "some_specific_output_dir"), str(resources_path / "series_simple.yaml")],
        global_config=global_config,
    )


def test_help(capfd, global_config):
    def func(config: LongConfig):
        """short_function_description

        long_description

        :param config: Configuration to use.
        """
        assert False, "This should not be executed."

    with pytest.raises(SystemExit):
        cordage.run(func, args=["--help"], global_config=global_config)

    out, err = capfd.readouterr()

    print(out)

    assert "a_help_str" in out
    assert "correct_help_text" in out
    assert "wrong_help_text" not in out
    assert ":param" not in out

    assert "short_function_description" in out
    assert "long_description" not in out
    assert "config_description" not in out

    first_line = out.split("\n")[0]

    assert "[config_file]" in first_line
    assert "<configuration options to overwrite>" in first_line


def test_explicit_description(capfd, global_config):
    def func(config: LongConfig):
        assert False, "This should not be executed."

    with pytest.raises(SystemExit):
        cordage.run(func, args=["--help"], global_config=global_config, description="EXPLICIT_DESCRIPTION")

    out, err = capfd.readouterr()

    assert "EXPLICIT_DESCRIPTION" in out
