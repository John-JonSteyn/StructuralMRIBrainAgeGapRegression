"""Pull the FastSurfer Docker images."""

from __future__ import annotations

import subprocess
import sys


FastSurferImageNames = [
    "deepmi/fastsurfer:cpu-v2.4.2",
    "deepmi/fastsurfer:cuda-v2.4.2",
]


def RunCommand(Command: list[str]) -> None:
    """Run a shell command and stop if it fails."""
    print(f"Running: {' '.join(Command)}")
    subprocess.run(Command, check=True)


def Main() -> None:
    RunCommand(["docker", "--version"])

    for FastSurferImageName in FastSurferImageNames:
        RunCommand(["docker", "pull", FastSurferImageName])

    RunCommand(["docker", "image", "ls", "deepmi/fastsurfer"])


if __name__ == "__main__":
    try:
        Main()
    except FileNotFoundError:
        print("Docker was not found. Install Docker and ensure it is available on PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as Error:
        print(f"Command failed with exit code {Error.returncode}.")
        sys.exit(Error.returncode)