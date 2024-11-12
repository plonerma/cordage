import logging

import pytest
from config_classes import SimpleConfig as Config

import cordage

log = logging.getLogger(__name__)


def test_exception_logging(global_config):
    """If an (uncaught) exception is thrown in the experiment, it should
    be logged and noted in the metadata."""

    class SomeSpecificError(RuntimeError):
        pass

    def func(config: Config):  # noqa: ARG001
        msg = "Exception42"
        raise SomeSpecificError(msg)

    context = cordage.FunctionContext(func, global_config=global_config)
    trial = context.parse_args([])

    with pytest.raises(SomeSpecificError):
        context.execute(trial)

    assert trial.has_status("failed")
    assert "exception" in trial.metadata.additional_info
    assert "Exception42" in trial.metadata.additional_info["exception"]["short"]
    assert "Exception42" in trial.metadata.additional_info["exception"]["traceback"]

    with open(trial.log_path) as f:
        log_content = f.read()

    assert "Exception42" in log_content


def test_function_without_annotation():
    def func(config):
        pass

    with pytest.raises(TypeError) as e_info:
        cordage.run(func, args=[])

    assert "Configuration class could not be derived" in str(e_info.value)


def test_function_without_config_parameter():
    def func():
        pass

    with pytest.raises(TypeError) as e_info:
        cordage.run(func, args=[])

    assert "Callable must accept config" in str(e_info.value)


def test_function_invalid_object_to_execute(global_config):
    def func(config: Config):
        pass

    context = cordage.FunctionContext(func, global_config=global_config)

    with pytest.raises(TypeError) as e_info:
        context.execute(object())  # type: ignore

    assert "Passed object must be Trial or Series" in str(e_info.value)


def test_multiple_runtime_exceptions(global_config):
    metadata: cordage.Metadata = cordage.Metadata(
        function="no_function", global_config=global_config, configuration={}
    )

    with pytest.raises(TypeError):
        exp = cordage.Experiment(metadata, global_config=global_config)

    exp = cordage.Experiment(function="no_function", global_config=global_config, configuration={})

    with pytest.raises(RuntimeError):
        log.info(str(exp.output_dir))

    assert "status: pending" in repr(exp)
