from dataclasses import dataclass, field

import pytest

import cordage
from cordage import Experiment


@dataclass
class AlphaConfig:
    a: int
    b: str = "b_value"


@dataclass
class BetaConfig:
    a: str = "a_value"
    b: int = 0


@dataclass
class Config:
    """config_description.

    :param a: a_help_str
    :param d: wrong_help_text
    """

    alpha: AlphaConfig
    beta: BetaConfig = field(default_factory=BetaConfig)

    a: str = "e_default"

    # these fields are used in test_more_trial_series for checking the configuration and output dir etc.
    alphas: int = 1
    betas: int = 1


def test_trial_series_list(global_config, resources_path):
    global_config.output_dir_format = "nested/structure/experiment{collision_suffix}"

    series_path = global_config.base_output_dir / "nested" / "structure" / "experiment"

    def load_filtered(status=(), tag=()):
        return [exp for exp in Experiment.all_from_path(series_path) if exp.has_status(*status) and exp.has_tag(*tag)]

    def func(config: Config, cordage_trial: cordage.Trial):
        if config.alpha.a == 1:
            cordage_trial.add_tag("the_first")

        if config.alpha.a == 2:
            cordage_trial.add_tag("second")

            assert len(load_filtered()) == 2
            assert len(load_filtered(status=["complete"])) == 1
            assert len(load_filtered(status=["complete", "running"])) == 2

            cordage_trial.comment = "This is #not_the_first(?) run."

        if config.alpha.a == 3:
            cordage_trial.add_tag("not_the_first")

            raise RuntimeError()

    config_file = resources_path / "series_list.yml"

    with pytest.raises(RuntimeError):
        cordage.run(func, args=[str(config_file)], global_config=global_config)

    all_experiments = Experiment.all_from_path(series_path)

    # experiments are sorted
    assert (all_experiments[0].output_dir < all_experiments[1].output_dir) and (
        all_experiments[1].output_dir < all_experiments[2].output_dir
    )

    assert len(load_filtered()) == 3
    assert len(load_filtered(status=["complete"])) == 2
    assert len(load_filtered(tag=["not_the_first"])) == 2
    assert len(load_filtered(tag=["not_the_first", "the_first"], status=["complete"])) == 2
    assert len(load_filtered(tag=["not_the_first"], status=["complete"])) == 1

    # Since we only load top level experiments, only the series should show up
    assert len(Experiment.all_from_path(global_config.base_output_dir)) == 1


def test_annotation_comment(global_config, monkeypatch):
    TEST_COMMENT = "Some string"

    def func(config: Config, cordage_trial):
        print(cordage_trial.annotations)

    cordage.run(
        func,
        args=["--alpha.a", "1", "--experiment-comment", TEST_COMMENT],
        global_config=global_config,
    )

    exp = Experiment.from_path(global_config.base_output_dir / "experiment")
    assert exp.comment == TEST_COMMENT
    assert exp.annotations["comment"] == TEST_COMMENT


def test_annotation_comment_addition(global_config, resources_path):
    TEST_COMMENT = "Some string"
    EXPECTED_COMMENT = f"Config file comment\n\n{TEST_COMMENT}"

    def func(config: Config, cordage_trial):
        print(cordage_trial.annotations)

    conf_path = resources_path / "annotation.yaml"

    cordage.run(func, args=["--experiment-comment", TEST_COMMENT, str(conf_path)], global_config=global_config)

    exp = Experiment.from_path(global_config.base_output_dir / "experiment")
    assert exp.comment == EXPECTED_COMMENT
    assert exp.annotations["comment"] == EXPECTED_COMMENT


def test_config_annotation_comment(global_config, resources_path):
    EXPECTED_COMMENT = "Config file comment"

    def func(config: Config, cordage_trial):
        print(cordage_trial.annotations)

    conf_path = resources_path / "annotation.yaml"

    cordage.run(func, args=[str(conf_path)], global_config=global_config)

    exp = Experiment.from_path(global_config.base_output_dir / "experiment")
    assert exp.comment == EXPECTED_COMMENT
    assert exp.annotations["comment"] == EXPECTED_COMMENT


def test_function_name_saving(global_config, resources_path):
    def func(config: Config):
        pass

    conf_path = resources_path / "annotation.yaml"

    cordage.run(func, args=[str(conf_path)], global_config=global_config)


def test_aborted_trial(global_config):
    def func(config: AlphaConfig):
        if config.a == 1:
            raise KeyboardInterrupt()

    context = cordage.FunctionContext(func, global_config=global_config)

    trial = context.parse_args(["--a", "2"])
    context.execute(trial)
    assert trial.status == "complete"

    with pytest.raises(KeyboardInterrupt):
        trial = context.parse_args(["--a", "1"])
        context.execute(trial)
    assert trial.status == "aborted"
