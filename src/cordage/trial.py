from contextlib import contextmanager
from datetime import datetime
from math import floor, log10
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .global_config import GlobalConfig


class Trial:
    def __init__(self, config, global_config, metadata):
        super().__init__()

        self.config = config
        self.global_config = global_config
        self.metadata: Dict[str, Any] = {"status": "waiting", **metadata}
        self._output_dir: Optional[Path] = None

    @property
    def output_dir(self) -> Path:
        assert self._output_dir is not None, "Trial has not been started yet."
        return self._output_dir

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

    def end(self, status: str = "undecided"):
        """End the execution of a trial.

        Write metadata, close logs, etc.
        """
        end_time = datetime.now()
        self.metadata.update(end_time=end_time, duration=end_time - self.metadata["start_time"], status=status)

    def create_output_dir(self):
        ideal_path = self.global_config.output_dir_format.format(**self.metadata)
        path = self.global_config.base_output_dir / ideal_path

        i = 1
        while path.exists():
            level = floor(log10(i) / 2) + 1
            path = self.global_config.base_output_dir / (ideal_path + "_" * level + str(i).zfill(2 * level))
            i += 1

        # found a path that does not exist yet
        path.mkdir(parents=True)
        self._output_dir = path

    def handle_exception(self, exc):
        pass

    @classmethod
    def make_config(cls, func: Callable, global_config: GlobalConfig):
        pass
