import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

import poetry
import pytest
from cleo.io.outputs.output import Verbosity
from poetry.console.application import Application as PoetryApplication
from poetry.utils.env import VirtualEnv

from poetry_relax import RelaxCommand

from ._utilities import (
    PoetryCommandTester,
    assert_io_contains,
    assert_pyproject_matches,
    assert_pyproject_unchanged,
    check_paths_relative,
    get_dependency_group,
    load_lockfile_packages,
    tmpchdir,
    update_pyproject,
)


@pytest.fixture
def relax_command(poetry_application: PoetryApplication):
    """
    Return a cleo command tester for the `poetry relax` command.
    """
    # Using a command tester is significantly faster than running subprocesses but
    # requires a little more setup
    command = RelaxCommand()
    tester = PoetryCommandTester(command, poetry_application)

    yield tester

    # Display output for debugging tests
    print(tester.io.fetch_output(), end="")
    print(tester.io.fetch_error(), file=sys.stderr, end="")


@pytest.fixture
def seeded_relax_command(
    relax_command: PoetryCommandTester,
    seeded_poetry_project_path: Path,
    poetry_application_factory: Callable[[], PoetryApplication],
    seeded_project_venv: VirtualEnv,
):
    # Update the application for the command to the seeded version
    application = poetry_application_factory()
    relax_command.configure_for_application(application)

    # Assert that the update above was successful
    assert check_paths_relative(
        relax_command.command.poetry.file.path, seeded_poetry_project_path
    ), f"""
        The poetry application's config file should be relative to the test project path:
            {seeded_poetry_project_path}
        but the following path was found:
            {relax_command.command.poetry.file.path}"
        """

    yield relax_command


@pytest.fixture(autouse=True)
def autouse_poetry_project_path(poetry_project_path):
    # All tests in this module should auto-use the project path for isolation
    yield poetry_project_path


@pytest.mark.parametrize("extra_options", ["", "--update", "--lock"])
def test_newly_initialized_project(
    relax_command: PoetryCommandTester, extra_options: str
):
    with assert_pyproject_unchanged():
        relax_command.execute(extra_options)

    assert relax_command.status_code == 0
    assert_io_contains("No dependencies to relax", relax_command.io)


def test_group_does_not_exist(relax_command: PoetryCommandTester):
    with assert_pyproject_unchanged():
        relax_command.execute("--only iamnotagroup")

    assert relax_command.status_code == 1
    assert_io_contains("Group(s) not found: iamnotagroup", relax_command.io)


def test_with_no_pyproject_toml(
    relax_command: PoetryCommandTester, poetry_project_path: Path
):
    os.remove(poetry_project_path / "pyproject.toml")

    # The error type differs depending on the test fixture used to set up the
    # command, so we cover both
    with pytest.raises((RuntimeError, FileNotFoundError), match="pyproject.toml"):
        relax_command.execute("--check")


def test_help(relax_command: PoetryCommandTester):
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
def test_single_simple_dependency_updated(
    relax_command: PoetryCommandTester, version: str
):
    # Add test package with pin
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = f"^{version}"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        expected_config["tool"]["poetry"]["dependencies"]["test"] = f">={version}"

    assert relax_command.status_code == 0


def test_multiple_dependencies_updated(relax_command: PoetryCommandTester):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["foo"] = "^1.0"
        pyproject["tool"]["poetry"]["dependencies"]["bar"] = "^2.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        expected_config["tool"]["poetry"]["dependencies"]["foo"] = ">=1.0"
        expected_config["tool"]["poetry"]["dependencies"]["bar"] = ">=2.0"

    assert relax_command.status_code == 0


def test_single_dependency_updated_in_group(relax_command: PoetryCommandTester):
    # Add test package with pin
    with update_pyproject() as config:
        get_dependency_group(config, "dev")["test"] = "^1.0"

    relax_command.command.reset_poetry()

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--only dev")

        get_dependency_group(expected_config, "dev")["test"] = ">=1.0"

    assert relax_command.status_code == 0


def test_single_dependency_updated_in_group_with_deprecated_option(
    relax_command: PoetryCommandTester,
):
    # Add test package with pin
    with update_pyproject() as config:
        get_dependency_group(config, "dev")["test"] = "^1.0"

    relax_command.command.reset_poetry()

    with assert_pyproject_matches() as expected_config:
        # Uses `--group` instead of `--only`
        relax_command.execute("--group dev")

        get_dependency_group(expected_config, "dev")["test"] = ">=1.0"

    assert relax_command.status_code == 0
    assert_io_contains(
        "The `--group` option is deprecated; use `--only` instead.", relax_command.io
    )


def test_single_dependency_updated_in_multiple_groups(
    relax_command: PoetryCommandTester,
):
    with update_pyproject() as config:
        get_dependency_group(config)["test"] = "^1.0"
        get_dependency_group(config, "foo")["test"] = "^2.0"
        get_dependency_group(config, "bar")["test"] = "^3.0"

        # Cover inclusion of optional groups
        config["tool"]["poetry"]["group"]["bar"]["optional"] = True

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        get_dependency_group(expected_config)["test"] = ">=1.0"
        get_dependency_group(expected_config, "foo")["test"] = ">=2.0"
        get_dependency_group(expected_config, "bar")["test"] = ">=3.0"

    assert relax_command.status_code == 0


def test_group_with_no_dependencies_is_skipped(
    relax_command: PoetryCommandTester,
):
    with update_pyproject() as config:
        get_dependency_group(config, "foo")
        get_dependency_group(config, "bar")["test"] = "^3.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        get_dependency_group(expected_config, "foo")
        get_dependency_group(expected_config, "bar")["test"] = ">=3.0"

    assert relax_command.status_code == 0
    assert_io_contains("No dependencies to relax in group 'foo'", relax_command.io)


def test_multiple_dependencies_updated_in_multiple_groups(
    relax_command: PoetryCommandTester,
):
    with update_pyproject() as config:
        get_dependency_group(config)["a"] = "^1.0"
        get_dependency_group(config, "foo")["b"] = "^2.0"
        get_dependency_group(config, "bar")["c"] = "^3.0"

        # Cover inclusion of optional groups
        config["tool"]["poetry"]["group"]["bar"]["optional"] = True

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        get_dependency_group(expected_config)["a"] = ">=1.0"
        get_dependency_group(expected_config, "foo")["b"] = ">=2.0"
        get_dependency_group(expected_config, "bar")["c"] = ">=3.0"

    assert relax_command.status_code == 0


@pytest.mark.parametrize(
    "input_version,output_version",
    [
        ("^1.4,!=1.5", ">=1.4,!=1.5"),
        ("!=1.5,^1.4", "!=1.5,>=1.4"),
        ("^1.4 || !=1.5", ">=1.4 || !=1.5"),
        ("^1.4, !=1.5", ">=1.4, !=1.5"),
        ("^1.4, !=1.5", ">=1.4, !=1.5"),
        (">=1.4, !=1.5", ">=1.4, !=1.5"),
        ("^1.4, <= 2.5", ">=1.4, <= 2.5"),
    ],
)
def test_multiple_constraint_dependency_only_updates_caret(
    relax_command: PoetryCommandTester, input_version, output_version
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["prefect"] = input_version

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        expected_config["tool"]["poetry"]["dependencies"]["prefect"] = output_version

    assert relax_command.status_code == 0


@pytest.mark.parametrize("version", ["==1", ">=1.0", ">=1.0b1,<=2.0", "<=2.0.0"])
def test_single_dependency_without_caret_constraint_not_updated(
    relax_command: PoetryCommandTester, version: str
):
    # Add test package with pin
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = version

    with assert_pyproject_unchanged():
        relax_command.execute()

    assert relax_command.status_code == 0


def test_dependency_updated_in_one_group_does_not_affect_other_groups(
    relax_command: PoetryCommandTester,
):
    with update_pyproject() as config:
        get_dependency_group(config)["test"] = "^1.0"
        get_dependency_group(config, "foo")["test"] = "^2.0"
        get_dependency_group(config, "bar")["test"] = "^3.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--only foo")

        get_dependency_group(expected_config)["test"] = "^1.0"
        get_dependency_group(expected_config, "foo")["test"] = ">=2.0"
        get_dependency_group(expected_config, "bar")["test"] = "^3.0"

    assert relax_command.status_code == 0


def test_group_excluded_with_without_is_not_affected(
    relax_command: PoetryCommandTester,
):
    with update_pyproject() as config:
        get_dependency_group(config)["test"] = "^1.0"
        get_dependency_group(config, "foo")["test"] = "^2.0"
        get_dependency_group(config, "bar")["test"] = "^3.0"

    with assert_pyproject_matches() as expected_config:
        relax_command.execute("--without foo")

        get_dependency_group(expected_config)["test"] = ">=1.0"
        get_dependency_group(expected_config, "foo")["test"] = "^2.0"
        get_dependency_group(expected_config, "bar")["test"] = ">=3.0"

    assert relax_command.status_code == 0


def test_dependency_with_additional_options(relax_command: PoetryCommandTester):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = {
            "version": "^1.0",
            "allow-prereleases": True,
        }

    with assert_pyproject_matches() as expected_config:
        relax_command.execute()

        expected_config["tool"]["poetry"]["dependencies"]["test"] = {
            "version": ">=1.0",
            "allow-prereleases": True,
        }

    assert relax_command.status_code == 0


def test_dependency_updated_with_validity_check(
    seeded_relax_command: PoetryCommandTester,
    seeded_project_venv: VirtualEnv,
    seeded_cloudpickle_version: str,
):
    with update_pyproject() as config:
        config["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^1.0"
        get_dependency_group(config, "dev")["cloudpickle"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        seeded_relax_command.execute("--check")

        expected_config["tool"]["poetry"]["dependencies"]["cloudpickle"] = ">=1.0"
        get_dependency_group(expected_config, "dev")["cloudpickle"] = ">=1.0"

    assert seeded_relax_command.status_code == 0
    new_cloudpickle_version = seeded_project_venv.run_python_script(
        "import cloudpickle; print(cloudpickle.__version__)"
    ).strip()
    assert (
        new_cloudpickle_version == seeded_cloudpickle_version
    ), f"The dependency should not be updated but has version {new_cloudpickle_version}"


def test_dependency_relax_aborted_when_constraint_is_not_satisfiable(
    seeded_relax_command: PoetryCommandTester,
):
    with update_pyproject() as pyproject:
        # Configure the pyproject with a version that does not exist
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^999.0"

        # Configure a valid version in another group — should not be relaxed
        get_dependency_group(pyproject, "dev")["cloudpickle"] = "^1.0"

    with assert_pyproject_unchanged():
        seeded_relax_command.execute("--check")

    assert seeded_relax_command.status_code == 1
    assert_io_contains(
        "Aborted relax due to failure during dependency update",
        seeded_relax_command.io,
    )


def test_dependency_relax_aborted_when_package_does_not_exist(
    seeded_relax_command: PoetryCommandTester,
):
    fake_name = uuid.uuid4().hex

    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"][fake_name] = "^1.0"

        # Configure a valid dependency in another group — should not be relaxed
        get_dependency_group(pyproject, "dev")["cloudpickle"] = "^1.0"

    with assert_pyproject_unchanged():
        seeded_relax_command.execute("--check")

    assert seeded_relax_command.status_code == 1
    assert_io_contains(
        "Aborted relax due to failure during dependency update",
        seeded_relax_command.io,
    )


def test_update_flag_upgrades_dependency_after_relax(
    seeded_relax_command: PoetryCommandTester,
    seeded_project_venv: VirtualEnv,
    seeded_cloudpickle_version: str,
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        seeded_relax_command.execute("--update", verbosity=Verbosity.DEBUG)

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


def test_lock_flag_only_updates_lockfile_after_relax(
    seeded_relax_command: PoetryCommandTester,
    seeded_project_venv: VirtualEnv,
    seeded_cloudpickle_version: str,
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        seeded_relax_command.execute("--lock", verbosity=Verbosity.DEBUG)

        expected_config["tool"]["poetry"]["dependencies"]["cloudpickle"] = ">=1.0"

    assert seeded_relax_command.status_code == 0

    lockfile_pkgs = load_lockfile_packages()
    lock_cloudpickle_version = lockfile_pkgs["cloudpickle"]["version"]
    assert (
        lock_cloudpickle_version != seeded_cloudpickle_version
    ), f"The dependency should be updated in the lockfile but has version {lock_cloudpickle_version}"
    assert (
        int(lock_cloudpickle_version.partition(".")[0]) > 1
    ), f"The dependency should be updated to the next major version but has version {lock_cloudpickle_version}"

    new_cloudpickle_version = seeded_project_venv.run_python_script(
        "import cloudpickle; print(cloudpickle.__version__)"
    ).strip()
    assert (
        new_cloudpickle_version == seeded_cloudpickle_version
    ), f"The dependency should not be upgraded but has version {new_cloudpickle_version}"


@pytest.mark.parametrize("extra_options", ["", "--update", "--lock", "--check"])
def test_dry_run_flag_prevents_changes(
    extra_options: str,
    seeded_relax_command: PoetryCommandTester,
    seeded_project_venv: VirtualEnv,
    seeded_cloudpickle_version: str,
):
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["cloudpickle"] = "^1.0"

    with assert_pyproject_unchanged():
        seeded_relax_command.execute(f"--dry-run {extra_options}")

    assert seeded_relax_command.status_code == 0

    new_cloudpickle_version = seeded_project_venv.run_python_script(
        "import cloudpickle; print(cloudpickle.__version__)"
    ).strip()

    assert (
        new_cloudpickle_version == seeded_cloudpickle_version
    ), f"The dependency should not be upgraded but has version {new_cloudpickle_version}"

    if "--check" in extra_options:
        assert_io_contains(
            "Checking dependencies in group 'main' for relaxable constraints",
            seeded_relax_command.io,
        )
    assert_io_contains(
        "Skipped update of config file due to dry-run flag.", seeded_relax_command.io
    )


def test_python_dependency_is_ignored(relax_command: PoetryCommandTester):
    # TODO: Consider changing this behavior before stable release.
    #       There are some peculiar issues with this though.

    # Add Python package with pin
    with update_pyproject() as config:
        config["tool"]["poetry"]["dependencies"]["python"] = "^3.8"

    with assert_pyproject_unchanged():
        relax_command.execute("--check")

    assert relax_command.status_code == 0


def test_invoked_from_subdirectory(
    relax_command: PoetryCommandTester, poetry_project_path: Path
):
    child_dir = poetry_project_path / "child"
    child_dir.mkdir()

    # Add test package with pin
    with update_pyproject() as pyproject:
        pyproject["tool"]["poetry"]["dependencies"]["test"] = "^1.0"

    with assert_pyproject_matches() as expected_config:
        # Change directories for execution of the package
        with tmpchdir(child_dir):
            relax_command.execute()

        expected_config["tool"]["poetry"]["dependencies"]["test"] = ">=1.0"

    assert relax_command.status_code == 0
