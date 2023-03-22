import dataclasses
import json

import pytest

from cordage import GlobalConfig
from cordage.util import to_dict


def test_global_config(global_config):
    assert dataclasses.is_dataclass(global_config)
    assert dataclasses.is_dataclass(global_config.central_metadata)

    # These should not throw TypeErrors
    json.dumps(to_dict(global_config.central_metadata))

    json.dumps(to_dict(global_config))


def test_format_string_validation(global_config):
    # This should be valid
    _ = GlobalConfig()

    with pytest.raises(KeyError):
        _ = dataclasses.replace(global_config, experiment_id_format="{non_existing_field}")

    with pytest.raises(KeyError):
        _ = dataclasses.replace(global_config, experiment_id_format="{experiment_id}")

    # Output dir should contain the experiment id
    _ = dataclasses.replace(global_config, output_dir_format="{experiment_id}")

    with pytest.raises(KeyError):
        _ = dataclasses.replace(global_config, output_dir_format="{non_existing_field}")

    with pytest.raises(ValueError):
        _ = dataclasses.replace(global_config, output_dir_format="{experiment_id:%Y}")
