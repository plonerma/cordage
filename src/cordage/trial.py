import json
from contextlib import contextmanager
from datetime import datetime
from math import floor, log10
from pathlib import Path
from traceback import format_exc
from typing import Any, Callable, Dict

from .configuration import nested_serialization
from .global_config import GlobalConfig


class Trial:
    def __init__(self, config, global_config, metadata):
        self.metadata: Dict[str, Any] = {
            "status": "waiting",
            "output_dir": None,
            "config": config,
            "global_config": global_config,
            **metadata,
        }

    @property
    def config(self):
        return self.metadata["config"]

    @property
    def global_config(self):
        return self.metadata["global_config"]

    @property
    def central_metadata_path(self):
        rel_path = self.output_dir.relative_to(self.global_config.base_output_dir)
        return self.global_config.central_metadata.path / rel_path / "metadata.json"

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
        self.metadata["exception"] = {"short": repr(exc), "traceback": format_exc()}

    def save_metadata(self):
        md_dict = nested_serialization(self.metadata)

        # save metadata in output dir
        with open(self.metadata_path, "w", encoding="utf-8") as fp:
            json.dump(md_dict, fp)

        if self.global_config.central_metadata.use:
            # rel exeriment path
            central_md_path = self.central_metadata_path
            central_md_path.parent.mkdir(parents=True, exist_ok=True)

            with central_md_path.open("w", encoding="utf-8") as fp:
                json.dump(md_dict, fp)

            with (central_md_path.parent / "files.json").open("w", encoding="utf-8") as fp:
                json.dump(self.produce_file_tree(self.output_dir), fp)

    @classmethod
    def make_config(cls, func: Callable, global_config: GlobalConfig):
        pass

    def produce_file_tree(self, path, level=0):
        max_level = self.global_config.file_tree.max_level
        max_files = self.global_config.file_tree.max_files

        if path.is_dir():
            if level > self.global_config.file_tree.max_level:
                return f"Maximum depth of {max_level} exceeded."

            dir_dict = {}

            for i, p in enumerate(path.iterdir()):
                if i == max_files:
                    return f"Maximum number of files ({max_files}) exceeded."

                dir_dict[p.name] = self.produce_file_tree(p, level=level + 1)

            return dir_dict

        elif path.is_file():
            return path.stat().st_size
        else:
            return None
