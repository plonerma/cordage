from dataclasses import dataclass

import pytest

import cordage


@dataclass
class Config:
    a: int = 42
    b: str = "test"


def test_exception_logging(global_config):
    """If an (uncaught) exception is thrown in the experiment, it should be logged and noted in the metadata."""

    class SomeSpecificError(RuntimeError):
        pass

    def func(config: Config):
        raise SomeSpecificError("Exception42")

    context = cordage.FunctionContext(func, global_config=global_config)
    trial = context.parse_args([])

    with pytest.raises(SomeSpecificError):
        context.execute(trial)

    assert trial.has_status("failed")
    assert "exception" in trial.metadata.additional_info
    assert "Exception42" in trial.metadata.additional_info["exception"]["short"]
    assert "Exception42" in trial.metadata.additional_info["exception"]["traceback"]

    with open(trial.log_path, "r") as f:
        log_content = f.read()

    assert "Exception42" in log_content


def test_function_without_annotation(global_config):
    def func(config):
        pass

    with pytest.raises(TypeError) as e_info:
        cordage.run(func, args=[])

    assert "Configuration class could not be derived" in str(e_info.value)


def test_function_without_config_parameter(global_config):
    def func():
        pass

    with pytest.raises(TypeError) as e_info:
        cordage.run(func, args=[])

    assert "Callable must accept config" in str(e_info.value)


def test_function_invalid_object_to_execute(global_config):
    def func(config: Config):
        pass

    context = cordage.FunctionContext(func)

    with pytest.raises(TypeError) as e_info:
        context.execute(object())  # type: ignore

    assert "Passed object must be Trial or Series" in str(e_info.value)


def test_multiple_runtime_exceptions(global_config):
    metadata: cordage.Metadata = cordage.Metadata(function="no_function", global_config=global_config)

    with pytest.raises(TypeError):
        exp = cordage.Experiment(metadata, global_config=global_config)

    exp = cordage.Experiment(function="no_function", global_config=global_config)

    with pytest.raises(RuntimeError):
        print(exp.output_dir)

    assert "status: pending" in repr(exp)
