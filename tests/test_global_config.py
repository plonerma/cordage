import dataclasses
import json

from cordage.configuration import to_dict


def test_global_config(global_config):
    assert dataclasses.is_dataclass(global_config)
    assert dataclasses.is_dataclass(global_config.central_metadata)

    # These should not throw TypeErrors
    json.dumps(to_dict(global_config.central_metadata))

    json.dumps(to_dict(global_config))
