"""
Core utilities for the `poetry relax` functionality.
"""
import contextlib
import functools
import re
import sys
from copy import copy
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Optional

import packaging.version
from poetry.core.packages.dependency_group import MAIN_GROUP

if TYPE_CHECKING:
    # See https://github.com/python-poetry/cleo/pull/254 for ignore
    from cleo.io.io import IO  # type: ignore
    from poetry.core.packages.dependency import Dependency
    from poetry.installation.installer import Installer
    from poetry.poetry import Poetry

if sys.version_info < (3, 8):  # Python 3.7 support
    import pkg_resources

    POETRY_VERSION = packaging.version.Version(
        pkg_resources.get_distribution("poetry").version
    )
else:
    import importlib.metadata as importlib_metadata

    POETRY_VERSION = packaging.version.Version(importlib_metadata.version("poetry"))


if POETRY_VERSION < packaging.version.Version("1.3.0"):
    from poetry.core.semver.version_range import VersionRange
else:
    from poetry.core.constraints.version import VersionRange


if POETRY_VERSION < packaging.version.Version("1.3.0"):
    # Poetry 1.2.x defined a different name for Cleo 1.x
    # isort: off
    from poetry.console.exceptions import (  # type: ignore
        PoetrySimpleConsoleException as PoetryConsoleError,
    )
else:
    from poetry.console.exceptions import PoetryConsoleError  # noqa: F401


# Regular expressions derived from `poetry.core.semver.helpers.parse_constraint`
# These are used to parse complex constraint strings into single constraints
AND_CONSTRAINT_SEPARATORS = re.compile(
    r"((?<!^)(?<![~=>< ,]) *(?<!-)[, ](?!-) *(?!,|$))"
)
OR_CONSTRAINT_SEPARATORS = re.compile(r"(\s*\|\|?\s*)")


@contextlib.contextmanager
def patch_io_writes(io: "IO", patch_function: Callable):
    """
    Patches writes to the given IO object to call the `patch_function`.
    """
    write_line = io.write_line
    write = io.write

    # See https://github.com/python/mypy/issues/708 for method override type ignores
    io.write_line = functools.partial(patch_function, write_line)  # type: ignore
    io.write = functools.partial(patch_function, write)  # type: ignore

    try:
        yield
    finally:
        io.write_line = write_line  # type: ignore
        io.write = write  # type:ignore


def run_installer_update(
    poetry: "Poetry",
    installer: "Installer",
    dependencies_by_group: Dict[str, Iterable["Dependency"]],
    poetry_config: dict,
    dry_run: bool,
    lockfile_only: bool,
    verbose: bool,
    silent: bool,
) -> int:
    """
    Run an installer update.

    Ensures that any existing dependencies in the given groups are replaced with the new
    dependencies if their names match.

    New dependencies are also whitelisted to be updated during locking.
    """

    for group_name, dependencies in dependencies_by_group.items():
        group = poetry.package.dependency_group(group_name)

        # Ensure if we are given a generator that we can consume it more than once
        dependencies = list(dependencies)

        for dependency in dependencies:
            with contextlib.suppress(ValueError):
                group.remove_dependency(dependency.name)
            group.add_dependency(dependency)

    # Refresh the locker
    poetry.set_locker(poetry.locker.__class__(poetry.locker.lock, poetry_config))
    installer.set_locker(poetry.locker)
    installer.only_groups(dependencies_by_group.keys())
    installer.set_package(poetry.package)
    installer.dry_run(dry_run)
    installer.verbose(verbose)
    installer.update()

    if lockfile_only:
        installer.lock()

    installer.whitelist([d.name for d in dependencies])

    last_line: str = ""

    def update_messages_for_dry_run(write, message, **kwargs):
        nonlocal last_line

        # Prevent duplicate messages unless they're whitespace
        # TODO: Determine the root cause of duplicates
        if message.strip() and message == last_line:
            return
        last_line = message

        if dry_run:
            message = message.replace("Updating", "Would update")
            message = message.replace("Installing", "Checking")
            message = message.replace("Skipped", "Would skip")

        return write(message, **kwargs)

    def silence(*args, **kwargs):
        pass

    with patch_io_writes(
        installer._io,
        silence if silent else update_messages_for_dry_run,  # type: ignore
    ):
        return installer.run()


def extract_dependency_config_for_group(
    group: str, poetry_config: dict
) -> Optional[dict]:
    """
    Retrieve the dictionary of dependencies defined for the given group in the poetry
    config.

    Returns `None` if the group does not exist or does not have any dependencies.
    """
    if group == MAIN_GROUP:
        return poetry_config.get("dependencies", None)

    return poetry_config.get("group", {}).get(group, {}).get("dependencies", None)


def drop_upper_bound_from_version_range(constraint: VersionRange) -> VersionRange:
    """
    Drop the upper bound from a version range constraint.
    """
    return VersionRange(constraint.min, max=None, include_min=constraint.include_min)


def mutate_constraint(constraints: str, callback: Callable[[str], str]) -> str:
    """
    Given a string of constraints, parse into single constraints, replace each one with
    the result of `callback`, then join into the original constraint string.

    Attempts to support modification of parts of constraint strings with minimal
    changes to the original format.

    Trailing and leading whitespace will be stripped.
    """
    # If the poetry helpers were used to parse the constraints, the user's constraints
    # can be modified which can be undesirable. For example, ">2.5,!=2.7" would be
    # changed to ">2.5,<2.7 || > 2.7".
    if constraints == "*":
        return callback(constraints)

    # Parse _or_ expressions first
    or_constraints = re.split(OR_CONSTRAINT_SEPARATORS, constraints.strip())

    # Note a capture group was used so re.split returns the captured separators as well
    # We need to retain these for joining the string after callbacks are performed
    # It's easiest to just mutate the lists rather than performing fancy zips
    for i in range(0, len(or_constraints), 2):
        # Parse _and_ expressions
        and_constraints = re.split(
            AND_CONSTRAINT_SEPARATORS,
            # Trailing `,` allowed but not retained — following Poetry internals
            or_constraints[i].rstrip(",").strip(),
        )

        # If there are no _and_ expressions, this will still be called once
        for j in range(0, len(and_constraints), 2):
            and_constraints[j] = callback(and_constraints[j])

        or_constraints[i] = "".join(and_constraints)

    return "".join(or_constraints)


def drop_upper_bound_from_caret_constraint(constraint: str) -> str:
    """
    Replace a caret constraint string with an equivalent lower-bound only constraint.

    If the constraint is not a caret constraint, it will be returned unchanged.
    """
    if constraint.startswith("^"):
        return constraint.replace("^", ">=", 1)
    else:
        return constraint


def drop_caret_bound_from_dependency(dependency: "Dependency") -> "Dependency":
    """
    Generate a new dependency with no upper bound from an existing dependency.

    If the dependency does not use a caret constraint to specify its upper bound,
    it will not be changed but a new copy will be returned.
    """
    new_version = mutate_constraint(
        dependency.pretty_constraint, drop_upper_bound_from_caret_constraint
    )

    # Copy the existing dependency to retain as much information as possible
    new_dependency = copy(dependency)

    # Update the constraint to the new version
    # The property setter parses this into a proper constraint type
    new_dependency.constraint = new_version  # type: ignore

    return new_dependency
