import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

import packaging.version
import pytest
from poetry.console.application import Application as PoetryApplication
from poetry.utils.env import EnvManager, VirtualEnv

from poetry_relax._core import POETRY_VERSION

from ._utilities import check_paths_relative, tmpchdir


@pytest.fixture(scope="session")
def poetry_cache_directory() -> Path:
    with tempfile.TemporaryDirectory(prefix="poetry-relax-test-cache") as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="session")
def poetry_application_factory(
    poetry_cache_directory: Path,
) -> Callable[[], PoetryApplication]:
    # Defined as a factory so we can use it in other session-scoped fixtures while
    # retaining independent instances per test
    def factory() -> PoetryApplication:
        application = PoetryApplication()
        application.poetry.config.merge(
            {
                "cache-dir": str(poetry_cache_directory),
                "virtualenvs": {
                    "in-project": True,
                    "system-site-packages": False,
                },
            }
        )
        return application

    yield factory


@pytest.fixture
def poetry_application(
    poetry_application_factory: Callable[[], PoetryApplication],
    poetry_project_path: Path,
) -> PoetryApplication:
    application = poetry_application_factory()

    # There are a few assertions in this style, as these fixtures were finicky to get
    # behaving correctly and we want to ensure our assumptions are correct before
    # tests run
    assert check_paths_relative(
        application.poetry.file.path, poetry_project_path
    ), f"""
        The poetry application's config file should be relative to the test project path:
            {poetry_project_path}
        but the following path was found:
            {application.poetry.file.path}"
        """

    yield application


@pytest.fixture(scope="session")
def base_poetry_project_path(
    poetry_application_factory: Callable[[], PoetryApplication]
) -> Path:
    with tempfile.TemporaryDirectory(prefix="poetry-relax-test-base") as tmpdir:
        # Create virtual environments in the temporary project
        os.environ["POETRY_VIRTUALENVS_IN_PROJECT"] = "true"

        init_process = subprocess.run(
            ["poetry", "init", "--no-interaction"],
            cwd=tmpdir,
            stderr=subprocess.PIPE,
            stdout=sys.stdout,
        )

        try:
            init_process.check_returncode()
        except subprocess.CalledProcessError as exc:
            init_error = init_process.stderr.decode().strip()
            raise RuntimeError(
                f"Failed to initialize test project: {init_error}"
            ) from exc

        # Hide that we are in a virtual environment already or Poetry will be refuse to
        # use one in the directory later
        os.environ.pop("VIRTUAL_ENV", None)

        # Create a virtual environment
        with tmpchdir(tmpdir):
            application = poetry_application_factory()
            env_manager = EnvManager(application.poetry)

            # Poetry expects a `str` in earlier versions
            if POETRY_VERSION < packaging.version.Version("1.4.0"):
                executable = sys.executable
            else:
                executable = Path(sys.executable)

            env = env_manager.create_venv(
                application.create_io(),
                executable,
                # Force required to create it despite tests generally being run inside a
                # virtual environment
                force=True,
            )

        tmp_path = Path(tmpdir).resolve()
        assert check_paths_relative(
            env.path, tmp_path
        ), f"""
            The virtual environment in the base test project should be in the 
            temporary directory:
                {tmp_path} 
            but was created at:
                {env.path}"
            """

        yield tmp_path


@pytest.fixture
def poetry_project_path(base_poetry_project_path: Path, tmp_path: Path) -> Path:
    project_path = tmp_path / "project"
    print(f"Creating test project at {project_path}")

    # Copy the initialized project into a clean temp directory
    shutil.copytree(base_poetry_project_path, project_path)

    # Change the working directory for the duration of the test
    with tmpchdir(project_path):
        yield project_path


@pytest.fixture(scope="session")
def seeded_base_poetry_project_path(
    base_poetry_project_path: Path, seeded_cloudpickle_version
) -> Path:
    with tempfile.TemporaryDirectory(prefix="poetry-relax-test-seeded-base") as tmpdir:
        seeded_base = Path(tmpdir).resolve() / "seeded-base"

        print(f"Creating base seeded project at {seeded_base}")

        # Copy the initialized project into a the directory
        shutil.copytree(base_poetry_project_path, seeded_base, symlinks=True)

        print(f"Installing 'cloudpickle=={seeded_cloudpickle_version}'")
        seed_process = subprocess.run(
            [
                "poetry",
                "add",
                f"cloudpickle=={seeded_cloudpickle_version}",
                "--no-interaction",
                "-v",
            ],
            cwd=seeded_base,
            stderr=subprocess.PIPE,
            stdout=sys.stdout,
            env={**os.environ},
        )

        try:
            seed_process.check_returncode()
        except subprocess.CalledProcessError as exc:
            seed_error = seed_process.stderr.decode().strip()
            raise RuntimeError(f"Failed to seed test project: {seed_error}") from exc

        print()  # Poetry does not print newlines at the end of install

        yield seeded_base


@pytest.fixture(scope="session")
def seeded_cloudpickle_version() -> str:
    yield "0.1.1"


@pytest.fixture
def seeded_poetry_project_path(
    seeded_base_poetry_project_path: Path,
    tmp_path: Path,
) -> Path:
    project_path = tmp_path / "seeded-project"
    print(f"Creating seeded test project at {project_path}")

    # Copy the initialized project into a clean temp directory
    shutil.copytree(seeded_base_poetry_project_path, project_path, symlinks=True)

    # Change the working directory for the duration of the test
    with tmpchdir(project_path):
        yield project_path


@pytest.fixture
def seeded_project_venv(
    seeded_poetry_project_path: Path, poetry_application_factory: PoetryApplication
) -> VirtualEnv:
    executable = seeded_poetry_project_path / ".venv" / "bin" / "python"

    assert executable.exists(), f"""
        The virtual environment should exist in the test project path but was not found at:
        {executable}"
        """

    manager = EnvManager(poetry=poetry_application_factory().poetry)

    print(f"Loading virtual environment at {executable}")
    env = manager.get(reload=True)

    assert check_paths_relative(
        env.path, seeded_poetry_project_path
    ), f"""
        The virtual environment in the test project should be in the project path:
            {seeded_poetry_project_path} 
        but the following path was activated:
            {env.path}"
        """

    # This will throw an exception if it fails
    env.run_python_script("import cloudpickle")

    yield env
