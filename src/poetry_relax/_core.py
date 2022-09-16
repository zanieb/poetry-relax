"""
Core utilities for the `poetry relax` functionality.
"""
import contextlib
import re
from copy import copy
from typing import TYPE_CHECKING, Callable, Iterable, Optional

from poetry.core.packages.dependency_group import MAIN_GROUP
from poetry.core.semver.version_range import VersionRange

if TYPE_CHECKING:
    from poetry.core.packages.dependency import Dependency
    from poetry.installation.installer import Installer
    from poetry.poetry import Poetry


# Regular expressions derived from `poetry.core.semver.helpers.parse_constraint`
# These are used to parse complex constraint strings into single constraints
AND_CONSTRAINT_SEPARATORS = re.compile(
    r"((?<!^)(?<![~=>< ,]) *(?<!-)[, ](?!-) *(?!,|$))"
)
OR_CONSTRAINT_SEPARATORS = re.compile(r"(\s*\|\|?\s*)")


def run_installer_update(
    poetry: "Poetry",
    installer: "Installer",
    dependencies: Iterable["Dependency"],
    dependency_group_name: str,
    poetry_config: dict,
    dry_run: bool,
    lockfile_only: bool,
    verbose: bool,
) -> int:
    """
    Run an installer update.

    Ensures that any existing dependencies in the given group are replaced with the new
    dependencies if their names match.

    New dependencies are also whitelisted to be updated during locking.
    """
    group = poetry.package.dependency_group(dependency_group_name)

    # Ensure if we are given a generator that we can consume it more than once
    dependencies = list(dependencies)

    for dependency in dependencies:
        with contextlib.suppress(ValueError):
            group.remove_dependency(dependency.name)
        group.add_dependency(dependency)

    # Refresh the locker
    poetry.set_locker(poetry.locker.__class__(poetry.locker.lock.path, poetry_config))
    installer.set_locker(poetry.locker)

    installer.set_package(poetry.package)
    installer.dry_run(dry_run)
    installer.verbose(verbose)
    installer.update()

    if lockfile_only:
        installer.lock()

    installer.whitelist([d.name for d in dependencies])

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
