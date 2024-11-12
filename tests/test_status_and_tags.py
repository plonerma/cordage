import logging

import pytest
from config_classes import AlphaConfig
from config_classes import NestedConfig as Config

import cordage
from cordage import Experiment

log = logging.getLogger(__name__)


def test_trial_series_list(global_config, resources_path):
    global_config.output_dir_format = "nested/structure/experiment{collision_suffix}"

    series_path = global_config.base_output_dir / "nested" / "structure" / "experiment"

    def load_filtered(status=(), tag=()):
        return [
            exp
            for exp in Experiment.all_from_path(series_path)
            if exp.has_status(*status) and exp.has_tag(*tag)
        ]

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

    # Since we only load top level experiments, only the series should
    # show up
    assert len(Experiment.all_from_path(global_config.base_output_dir)) == 1


def test_annotation_comment(global_config):
    test_comment = "Some string"

    def func(config: Config, cordage_trial):  # noqa: ARG001
        log.info(str(cordage_trial.annotations))

    cordage.run(
        func,
        args=["--alpha.a", "1", "--cordage-comment", test_comment],
        global_config=global_config,
    )

    exp = Experiment.from_path(global_config.base_output_dir / "experiment")
    assert exp.comment == test_comment
    assert exp.annotations["comment"] == test_comment


def test_annotation_comment_addition(global_config, resources_path):
    test_comment = "Some string"
    expected_comment = f"Config file comment\n\n{test_comment}"

    def func(config: Config, cordage_trial):  # noqa: ARG001
        log.info(str(cordage_trial.annotations))

    conf_path = resources_path / "annotation.yaml"

    cordage.run(
        func, args=["--cordage-comment", test_comment, str(conf_path)], global_config=global_config
    )

    exp = Experiment.from_path(global_config.base_output_dir / "experiment")
    assert exp.comment == expected_comment
    assert exp.annotations["comment"] == expected_comment


def test_config_annotation_comment(global_config, resources_path):
    expected_comment = "Config file comment"

    def func(config: Config, cordage_trial):  # noqa: ARG001
        log.info(str(cordage_trial.annotations))

    conf_path = resources_path / "annotation.yaml"

    cordage.run(func, args=[str(conf_path)], global_config=global_config)

    exp = Experiment.from_path(global_config.base_output_dir / "experiment")
    assert exp.comment == expected_comment
    assert exp.annotations["comment"] == expected_comment


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
