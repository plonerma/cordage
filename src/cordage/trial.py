import json
from contextlib import contextmanager
from datetime import datetime
from math import floor, log10
from pathlib import Path
from typing import Any, Callable, Dict

from .configuration import to_dict
from .global_config import GlobalConfig
from .util import serialize_value


class Trial:
    def __init__(self, config, global_config, metadata):
        super().__init__()

        self.config = config
        self.global_config = global_config
        self.metadata: Dict[str, Any] = {"status": "waiting", "output_dir": None, **metadata}

    @property
    def central_metadata_path(self):
        rel_path = self.output_dir.relative_to(self.global_config.base_output_dir)
        return self.global_config.central_metadata_store / rel_path.parent / (rel_path.name + ".json")

    @property
    def metadata_path(self):
        return self.output_dir / "cordage.json"

    @property
    def trial_id(self):
        return self.metadata["trial_id"]

    @property
    def output_dir(self) -> Path:
        assert self.metadata["output_dir"] is not None, "Trial has not been started yet."
        return self.metadata["output_dir"]

    @contextmanager
    def run(self):
        try:
            self.start()
            yield
            self.end(status="complete")
        except KeyboardInterrupt:
            self.end(status="aborted")
            raise
        except Exception as exc:
            self.handle_exception(exc)
            self.end(status="failed")
            raise

    def start(self):
        """Start the execution of a trial.

        Set start time, create output directory, registers run, etc.
        """
        self.metadata.update(start_time=datetime.now(), status="running")
        self.create_output_dir()
        self.save_metadata()

    def end(self, status: str = "undecided"):
        """End the execution of a trial.

        Write metadata, close logs, etc.
        """
        end_time = datetime.now()
        self.metadata.update(
            end_time=end_time,
            duration=end_time - self.metadata["start_time"],
            status=status,
            config=to_dict(self.config),
            global_configuration=to_dict(self.global_config),
        )
        self.save_metadata()

    def create_output_dir(self):
        ideal_trial_id = self.global_config.trial_id_format.format(**self.metadata)

        self.metadata["trial_id"] = ideal_trial_id

        path = self.global_config.base_output_dir / self.global_config.output_dir_format.format(**self.metadata)

        i = 1
        while path.exists():
            level = floor(log10(i) / 2) + 1

            self.metadata["trial_id"] = ideal_trial_id + "_" * level + str(i).zfill(2 * level)
            path = self.global_config.base_output_dir / self.global_config.output_dir_format.format(**self.metadata)

            i += 1

        # found a path that does not exist yet
        path.mkdir(parents=True)
        self.metadata["output_dir"] = path

    def handle_exception(self, exc):
        pass

    def save_metadata(self):
        md_dict = {k: serialize_value(v) for k, v in self.metadata.items()}

        # save metadata in output dir
        with open(self.metadata_path, "w", encoding="utf-8") as fp:
            json.dump(md_dict, fp)

        if self.global_config.use_central_metadata_store:
            # rel exeriment path
            central_md_path = self.central_metadata_path
            central_md_path.parent.mkdir(parents=True, exist_ok=True)

            with open(central_md_path, "w", encoding="utf-8") as fp:
                json.dump(md_dict, fp)

    @classmethod
    def make_config(cls, func: Callable, global_config: GlobalConfig):
        pass
