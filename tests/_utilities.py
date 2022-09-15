import json
import os
import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import Any, Dict, Generator, Union

import tomlkit
from poetry.core.packages.dependency_group import MAIN_GROUP

PYPROJECT = "pyproject.toml"
LOCKFILE = "poetry.lock"


def load_tomlfile(path: Union[str, Path] = "./") -> tomlkit.TOMLDocument:
    return tomlkit.loads(Path(path).read_text())


@contextmanager
def update_tomlfile(
    file: Union[str, Path]
) -> Generator[tomlkit.TOMLDocument, None, None]:
    """
    Updates a toml file by reading then yielding the existing contents for mutation.
    """
    project_config = load_tomlfile(file)
    yield project_config
    Path(file).write_text(tomlkit.dumps(project_config))


@contextmanager
def assert_tomlfile_matches(
    file: Union[str, Path]
) -> Generator[tomlkit.TOMLDocument, None, None]:
    """
    Asserts that the toml file in the given directory (defaults to current)
    is matches the yielded object after the duration of the context.

    Yields the initial contents of the file which can be mutated for comparison.
    """
    project_config = load_tomlfile(file)
    yield project_config
    new_project_config = load_tomlfile(file)
    assert project_config == new_project_config


@contextmanager
def assert_tomlfile_unchanged(file: Union[str, Path]) -> Generator[None, None, None]:
    """
    Asserts that the toml file in the given directory (defaults to current)
    is unchanged during the duration of the context.
    """
    with assert_tomlfile_matches(file):
        yield


# Aliases for test readability

assert_pyproject_unchanged = partial(assert_tomlfile_unchanged, PYPROJECT)
assert_pyproject_matches = partial(assert_tomlfile_matches, PYPROJECT)
update_pyproject = partial(update_tomlfile, PYPROJECT)
assert_lockfile_unchanged = partial(assert_tomlfile_unchanged, LOCKFILE)
assert_lockfile_matches = partial(assert_tomlfile_matches, LOCKFILE)
load_lockfile = partial(load_tomlfile, LOCKFILE)
load_pyproject = partial(load_tomlfile, PYPROJECT)


def load_lockfile_packages() -> Dict[str, dict]:
    """
    Returns a mapping of package names to package information in the current lockfile
    """
    lockfile = load_lockfile()
    return {package["name"]: package for package in lockfile["package"]}


@contextmanager
def tmpchdir(new_dir: Union[str, Path]) -> Generator[None, None, None]:
    pwd = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(pwd)


def get_dependency_group(
    tomlfile_config: tomlkit.TOMLDocument, group: str = MAIN_GROUP
) -> Dict[str, str]:
    """
    Retrieve a dependency group from the poetry tool config in a tomlfile document.

    Defaults to the "main" group.

    The given tomlfile document may be modified to create empty collections as needed.
    """
    poetry_config = tomlfile_config["tool"]["poetry"]

    if group == MAIN_GROUP:
        if "dependencies" not in poetry_config:
            poetry_config["dependencies"] = tomlkit.table()

        return poetry_config["dependencies"]
    else:
        if "group" not in poetry_config:
            poetry_config["group"] = tomlkit.table(is_super_table=True)

        groups = poetry_config["group"]
        if group not in groups:
            dependencies_toml: dict[str, Any] = tomlkit.parse(
                f"[tool.poetry.group.{group}.dependencies]\n\n"
            )
            group_table = dependencies_toml["tool"]["poetry"]["group"][group]
            poetry_config["group"][group] = group_table

        if "dependencies" not in poetry_config["group"][group]:
            poetry_config["group"][group]["dependencies"] = tomlkit.table()

        return poetry_config["group"][group]["dependencies"]


def assert_io_contains(content: str, io) -> None:
    output = io.fetch_output()
    # Ensure the output can be retrieved again later
    io.fetch_output = lambda: output
    assert content in output


# Backport Path.is_relative_to from Python 3.9+ to older

if sys.version_info < (3, 9):

    def check_paths_relative(self, *other):
        try:
            self.relative_to(*other)
            return True
        except ValueError:
            return False

else:
    check_paths_relative = Path.is_relative_to
