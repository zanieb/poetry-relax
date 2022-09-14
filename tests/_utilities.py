from pathlib import Path
from typing import Union, Generator, Dict, Any
from contextlib import contextmanager
import tomlkit
import os
import json
import sys
from poetry.core.packages.dependency_group import MAIN_GROUP


def load_pyproject(path: Union[str, Path] = "./pyproject.toml") -> tomlkit.TOMLDocument:
    return tomlkit.loads(path.read_text())


def load_lockfile(path: Union[str, Path] = "./poetry.lock") -> dict:
    return json.loads(path.read_text())


@contextmanager
def update_pyproject(
    dirpath: Union[str, Path] = "."
) -> Generator[tomlkit.TOMLDocument, None, None]:
    """
    Asserts that the pyproject.toml file in the given directory (defaults to current)
    is matches the yielded object after the duration of the context.

    Yields the initial contents of the file which can be mutated for comparison.
    """
    pyproject_path = Path(dirpath) / "pyproject.toml"
    project_config = load_pyproject(pyproject_path)
    yield project_config
    pyproject_path.write_text(tomlkit.dumps(project_config))


@contextmanager
def assert_pyproject_matches(
    dirpath: Union[str, Path] = "."
) -> Generator[tomlkit.TOMLDocument, None, None]:
    """
    Asserts that the pyproject.toml file in the given directory (defaults to current)
    is matches the yielded object after the duration of the context.

    Yields the initial contents of the file which can be mutated for comparison.
    """
    pyproject_path = Path(dirpath) / "pyproject.toml"
    project_config = load_pyproject(pyproject_path)
    yield project_config
    new_project_config = load_pyproject(pyproject_path)
    assert project_config == new_project_config


@contextmanager
def assert_pyproject_unchanged(
    dirpath: Union[str, Path] = "."
) -> Generator[None, None, None]:
    """
    Asserts that the pyproject.toml file in the given directory (defaults to current)
    is unchanged during the duration of the context.
    """
    with assert_pyproject_matches(dirpath):
        yield


@contextmanager
def tmpchdir(new_dir: Union[str, Path]) -> Generator[None, None, None]:
    pwd = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(pwd)


def get_dependency_group(
    pyproject_config: tomlkit.TOMLDocument, group: str = MAIN_GROUP
) -> Dict[str, str]:
    """
    Retrieve a dependency group from the poetry tool config in a pyproject document.

    Defaults to the "main" group.

    The given pyproject document may be modified to create empty collections as needed.
    """
    poetry_config = pyproject_config["tool"]["poetry"]

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
    print(output)
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
