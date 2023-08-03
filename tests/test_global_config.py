import dataclasses
import json

import pytest

from cordage import GlobalConfig
from cordage.util import to_dict


def test_global_config(global_config):
    assert dataclasses.is_dataclass(global_config)

    json.dumps(to_dict(global_config))


def test_format_string_validation(global_config):
    # This should be valid
    _ = GlobalConfig()

    with pytest.raises(KeyError):
        _ = dataclasses.replace(global_config, output_dir_format="{non_existing_field}")

    _ = dataclasses.replace(global_config, output_dir_format="{collision_suffix}")

    with pytest.raises(ValueError):
        _ = dataclasses.replace(global_config, output_dir_format="{function:%Y}")
