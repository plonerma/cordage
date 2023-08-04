from dataclasses import dataclass

import cordage


@dataclass
class Config:
    a: int = 1
    b: str = "b_value"


def test_manual_output_dir(global_config, tmp_path):
    def func(config: Config):
        pass

    experiment = cordage.run(
        func, args=["--output-dir", str(tmp_path / "some_specific_output_dir")], global_config=global_config
    )

    assert experiment.output_dir == tmp_path / "some_specific_output_dir"


def test_manual_output_dir_for_series(global_config, tmp_path, resources_path):
    def func(config: Config, cordage_trial, output_dir):
        assert "trial_index" in cordage_trial.metadata.additional_info
        assert output_dir == tmp_path / "some_specific_output_dir" / str(
            cordage_trial.metadata.additional_info["trial_index"] + 1
        )

    cordage.run(
        func,
        args=["--output-dir", str(tmp_path / "some_specific_output_dir"), str(resources_path / "series_simple.yaml")],
        global_config=global_config,
    )
