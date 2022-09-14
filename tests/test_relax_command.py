import subprocess
import pytest
import os
import sys
import uuid

from typing import Callable
from pathlib import Path
from cleo.testers.command_tester import CommandTester
from poetry_relax import RelaxCommand
from poetry.console.application import Application as PoetryApplication
from poetry.utils.env import VirtualEnv


from ._utilities import (
    assert_pyproject_matches,
    assert_pyproject_unchanged,
    tmpchdir,
    update_pyproject,
    get_dependency_group,
    assert_io_contains,
)


@pytest.fixture
def relax_command(poetry_application: PoetryApplication):
    """
    Return a cleo command tester for the `poetry relax` command.
    """
    # Using a command tester is significantly faster than running subprocesses but
    # requires a little more setup
    command = RelaxCommand()
    tester = CommandTester(command)

    poetry_application.add(command)

    yield tester

    # Display output for debugging tests
    print(tester.io.fetch_output(), end="")
    print(tester.io.fetch_error(), file=sys.stderr, end="")


@pytest.fixture
def seeded_relax_command(
    relax_command: CommandTester,
    seeded_poetry_project_path: Path,
    poetry_application_factory: Callable[[], PoetryApplication],
    seeded_project_venv: VirtualEnv,
):
    # Update the application for the command to the seeded version
    application = poetry_application_factory()
    application.add(relax_command.command)

    # Assert that the update above was successful
    assert relax_command.command.poetry.file.path.is_relative_to(
        seeded_poetry_project_path
    ), f"""
        The poetry application's config file should be relative to the test project path:
            {seeded_poetry_project_path}
        but the following path was found:
            {relax_command.command.poetry.file.path}"
        """

    # The following is necessary to set up the command and is usually handled by
    # poetry.console.application.Application.__init__ on command dispatch. The tester
    # appears to bypass these handlers so we duplicate the setup here
    relax_command.command.set_env(seeded_project_venv)
    application.configure_installer_for_command(relax_command.command, relax_command.io)

    yield relax_command


@pytest.fixture(autouse=True)
def autouse_poetry_project_path(poetry_project_path):
    # All tests in this module should auto-use the project path for isolation
    yield poetry_project_path


@pytest.mark.parametrize("extra_options", ["", "--update", "--lock"])
def test_newly_initialized_project(relax_command: CommandTester, extra_options: str):
    with assert_pyproject_unchanged():
        relax_command.execute(extra_options)

    assert relax_command.status_code == 0
    assert_io_contains("No dependencies to relax", relax_command.io)


def test_group_does_not_exist(relax_command: CommandTester):
    with assert_pyproject_unchanged():
        relax_command.execute("--group iamnotagroup")

    assert relax_command.status_code == 1
    assert_io_contains(
        "No dependencies found in group 'iamnotagroup'", relax_command.io
    )


def test_with_no_pyproject_toml(
    relax_command: CommandTester, poetry_project_path: Path
):
    os.remove(poetry_project_path / "pyproject.toml")

    # The error type differs depending on the test fixture used to set up the
    # command, so we cover both
    with pytest.raises((RuntimeError, FileNotFoundError), match="pyproject.toml"):
        relax_command.execute()


def test_help(relax_command: CommandTester):
    with assert_pyproject_unchanged():
        relax_command.execute("--help")

    assert relax_command.status_code == 0
    assert_io_contains("No dependencies to relax", relax_command.io)


def test_available_in_poetry_cli():
    output = subprocess.check_output(["poetry", "relax", "--help"]).decode()
    assert "Relax project dependencies" in output
    assert "Usage:" in output
    assert "Options:" in output


@pytest.mark.parametrize("version", ["1", "1.0", "1.0b1", "2.0.0"])
def test_single_simple_dependency_updated(relax_command: CommandTester, version: str):
    # Add test package with pin
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = f"^{version}"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check")

        expected_config["tool"]["poetry"]["dependencies"]["test"] = f">={version}"

    assert relax_command.status_code == 0


def test_multiple_dependencies_updated(relax_command: CommandTester):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["foo"] = "^1.0"
        pyproject["tool"]["poetry"]["dependencies"]["bar"] = "^2.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check")

        expected_config["tool"]["poetry"]["dependencies"]["foo"] = ">=1.0"
        expected_config["tool"]["poetry"]["dependencies"]["bar"] = ">=2.0"

    assert relax_command.status_code == 0


def test_single_dependency_updated_in_group(relax_command: CommandTester):
    # Add test package with pin
    with update_pyproject() as config:
        get_dependency_group(config, "dev")["test"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check --group dev")

        get_dependency_group(expected_config, "dev")["test"] = ">=1.0"

    assert relax_command.status_code == 0


@pytest.mark.parametrize(
    "input_version,output_version",
    [
        ("^1.4,!=1.5", ">=1.4,!=1.5"),
        ("!=1.5,^1.4", "!=1.5,>=1.4"),
        ("^1.4 || !=1.5", ">=1.4 || !=1.5"),
        ("^1.4 && !=1.5", ">=1.4 && !=1.5"),
        ("^1.4 && !=1.5", ">=1.4 && !=1.5"),
        (">=1.4 && !=1.5", ">=1.4 && !=1.5"),
        ("^1.4 && <= 2.5", ">=1.4 && <= 2.5"),
    ],
)
def test_multiple_constraint_dependency_only_updates_caret(
    relax_command: CommandTester, input_version, output_version
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["prefect"] = input_version

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check")

        expected_config["tool"]["poetry"]["dependencies"]["prefect"] = output_version

    assert relax_command.status_code == 0


@pytest.mark.parametrize(
    "input_version,output_version",
    [
        ("^1.4,!=1.5", ">=1.4,!=1.5"),
        ("!=1.5,^1.4", "!=1.5,>=1.4"),
        ("^1.4 || !=1.5", ">=1.4 || !=1.5"),
        ("^1.4 && !=1.5", ">=1.4 && !=1.5"),
        ("^1.4 && !=1.5", ">=1.4 && !=1.5"),
        (">=1.4 && !=1.5", ">=1.4 && !=1.5"),
        ("^1.4 && <= 2.5", ">=1.4 && <= 2.5"),
    ],
)
def test_multiple_constraint_dependency_only_updates_caret(
    relax_command: CommandTester, input_version, output_version
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["prefect"] = input_version

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check")

        expected_config["tool"]["poetry"]["dependencies"]["prefect"] = output_version

    assert relax_command.status_code == 0


@pytest.mark.parametrize("version", ["==1", ">=1.0", ">=1.0b1,<=2.0", "<=2.0.0"])
def test_single_dependency_without_caret_constraint_not_updated(
    relax_command: CommandTester, version: str
):
    # Add test package with pin
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = version

    with assert_pyproject_unchanged():
        relax_command.execute("--no-check")

    assert relax_command.status_code == 0


def test_dependency_updated_in_one_group_does_not_affect_other_groups(
    relax_command: CommandTester,
):
    with update_pyproject() as config:
        get_dependency_group(config)["test"] = "^1.0"
        get_dependency_group(config, "foo")["test"] = "^2.0"
        get_dependency_group(config, "bar")["test"] = "^3.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check --group foo")

        get_dependency_group(expected_config)["test"] = "^1.0"
        get_dependency_group(expected_config, "foo")["test"] = ">=2.0"
        get_dependency_group(expected_config, "bar")["test"] = "^3.0"

    assert relax_command.status_code == 0


def test_dependency_with_additional_options(relax_command: CommandTester):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = {
            "version": "^1.0",
            "allow-prereleases": True,
        }

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--no-check")

        expected_config["tool"]["poetry"]["dependencies"]["test"] = {
            "version": ">=1.0",
            "allow-prereleases": True,
        }

    assert relax_command.status_code == 0


def test_dependency_updated_with_validity_check(
    seeded_relax_command: CommandTester,
    seeded_project_venv: VirtualEnv,
    seeded_cloudpickle_version: str,
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        seeded_relax_command.execute()

        expected_config["tool"]["poetry"]["dependencies"]["cloudpickle"] = ">=1.0"

    assert seeded_relax_command.status_code == 0
    new_cloudpickle_version = seeded_project_venv.run_python_script(
        "import cloudpickle; print(cloudpickle.__version__)"
    ).strip()
    assert (
        new_cloudpickle_version == seeded_cloudpickle_version
    ), f"The dependency should not be updated but has version {new_cloudpickle_version}"


def test_dependency_relax_aborted_when_constraint_is_not_satisfiable(
    seeded_relax_command: CommandTester,
):
    with update_pyproject() as pyproject:
        # Configure the pyproject with a version that does not exist
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^999.0"

    with assert_pyproject_unchanged():
        seeded_relax_command.execute()

    assert seeded_relax_command.status_code == 1
    assert_io_contains(
        "Aborted relax operation due to failure during dependency update",
        seeded_relax_command.io,
    )


def test_dependency_relax_aborted_when_package_does_not_exist(
    seeded_relax_command: CommandTester,
):
    fake_name = uuid.uuid4().hex

    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"][fake_name] = "^1.0"

    with assert_pyproject_unchanged():
        seeded_relax_command.execute()

    assert seeded_relax_command.status_code == 1
    assert_io_contains(
        "Aborted relax operation due to failure during dependency update",
        seeded_relax_command.io,
    )


def test_dependency_relaxed_then_upgraded(
    seeded_relax_command: CommandTester,
    seeded_project_venv: VirtualEnv,
    seeded_cloudpickle_version: str,
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        seeded_relax_command.execute("--update")

        expected_config["tool"]["poetry"]["dependencies"]["cloudpickle"] = ">=1.0"

    assert seeded_relax_command.status_code == 0
    new_cloudpickle_version = seeded_project_venv.run_python_script(
        "import cloudpickle; print(cloudpickle.__version__)"
    ).strip()
    assert (
        new_cloudpickle_version != seeded_cloudpickle_version
    ), f"The dependency should be updated but has initial version {new_cloudpickle_version}"
    assert (
        int(new_cloudpickle_version[0]) > 1
    ), f"The dependency should be updated to the next major version but has version {new_cloudpickle_version}"


def test_python_dependency_is_ignored(relax_command: CommandTester):
    # TODO: Consider changing this behavior before stable release.
    #       There are some peculiar issues with this though.

    # Add Python package with pin
    with update_pyproject() as config:
        config["tool"]["poetry"]["dependencies"]["python"] = "^3.8"

    with assert_pyproject_unchanged():
        relax_command.execute()

    assert relax_command.status_code == 0


def test_invoked_from_subdirectory(
    relax_command: CommandTester, poetry_project_path: Path
):
    child_dir = poetry_project_path / "child"
    child_dir.mkdir()

    # Add test package with pin
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        # Change directories for execution of the package
        with tmpchdir(child_dir):
            relax_command.execute("--no-check")

        expected_config["tool"]["poetry"]["dependencies"]["test"] = ">=1.0"

    assert relax_command.status_code == 0
