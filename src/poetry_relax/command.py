from typing import Any, List, cast

# cleo is not PEP 561 compliant must be ignored
# See https://github.com/python-poetry/cleo/pull/254
from cleo.helpers import option  # type: ignore
from poetry.console.commands.init import InitCommand
from poetry.console.commands.installer_command import InstallerCommand
from poetry.core.factory import Factory
from tomlkit.toml_document import TOMLDocument

from poetry_relax._core import (
    drop_caret_bound_from_dependency,
    extract_dependency_config_for_group,
    run_installer_update,
)


def _pretty_group(group: str) -> str:
    return f" in group <c1>{group!r}</c1>"


class RelaxCommand(InitCommand, InstallerCommand):
    """
    Implementation of `poetry relax`.
    """

    # This inherits from `InitCommand` and `InstallerCommand` for access to internal
    # utilities

    name = "relax"
    description = "Relax project dependencies."
    options = [
        option(
            "group",
            "-G",
            description=(
                "A group to relax constraints in. If not provided, all groups are used."
                # If a group is specified, it is treated like the Poetry `--only` flag.
            ),
            flag=False,
            default=None,
            multiple=True,
        ),
        option(
            "dry-run",
            None,
            description=("Output the operations but do not execute anything."),
        ),
        option(
            "lock",
            None,
            description="Run a lock file update after changing the constraints.",
        ),
        option(
            "check",
            None,
            description=(
                "Check if versions are valid after changing the constraints by running "
                "the Poetry solver."
            ),
        ),
        option(
            "update", None, description="Run an update after changing the constraints."
        ),
    ]
    help = (
        "The <c1>relax</> command removes upper version constraints designated by "
        "carets (<c2>^</>)."
    )

    def handle(self) -> int:
        """
        The plugin entrypoint for the `poetry relax` command.
        """

        # The following implemention relies heavily on internal Poetry objects and
        # is based on the `poetry add` implementation which is available under the MIT
        # license.

        # Read poetry file as a dictionary
        if self.io.is_verbose():
            self.line(f"Using poetry file at {self.poetry.file.path}")
        pyproject_config: dict[str, Any] = self.poetry.file.read()
        poetry_config = pyproject_config["tool"]["poetry"]

        groups = cast(List[str], self.option("group")) or list(
            # Use all groups by default, including optional groups
            sorted(self.poetry.package.dependency_group_names(include_optional=True))
        )
        if not groups:
            self.info("No groups specified.")
            return 1

        # Validate the groups using Poetry's internal handler
        self._validate_group_options({"group": set(groups)})

        updated_dependencies = {}  # Dependencies updated per group

        for group in groups:
            # Load dependencies in the given group
            pretty_group = _pretty_group(group)
            self.info(
                f"Checking dependencies{pretty_group} for relaxable constraints..."
            )

            dependency_config = extract_dependency_config_for_group(
                group, poetry_config
            )
            if dependency_config is None:
                self.line(f"No dependencies found{pretty_group}.")
                continue

            # Parse the dependencies
            target_dependencies = [
                Factory.create_dependency(name, constraints)
                for name, constraints in dependency_config.items()
                if name != "python"
            ]

            if not target_dependencies:
                self.line("No dependencies to relax{pretty_group}.")
                return 0

            if self.io.is_verbose():
                self.line(
                    f"Found {len(target_dependencies)} dependencies{pretty_group}."
                )

            # Construct new dependency objects with the max constraint removed
            new_dependencies = [
                drop_caret_bound_from_dependency(d) for d in target_dependencies
            ]

            updated_dependencies[group] = [
                (old.pretty_constraint, new)
                for old, new in zip(target_dependencies, new_dependencies)
                # We use the pretty constraint in updates to retain the user's string
                if old.pretty_constraint != new.pretty_constraint
            ]

            if self.io.is_verbose():
                self.line(
                    f"Proposing updates to {len(updated_dependencies[group])} "
                    f"dependencies{pretty_group}."
                )

        updated_count = sum(len(deps) for deps in updated_dependencies.values())
        if not updated_count:
            self.info("No dependency constraints to relax.")
            return 0

        self.line(f"Proposing updates to {updated_count} dependencies.")

        # Validate that the update is valid by running the installer
        if self.option("update") or self.option("check") or self.option("lock"):
            if self.io.is_verbose():
                for group in groups:
                    for old_constraint, dependency in updated_dependencies[group]:
                        self.info(
                            f"Proposing update for <c1>{dependency.name}</> constraint from "
                            f"<c2>{old_constraint}</> to <c2>{dependency.pretty_constraint}</>"
                            f"{_pretty_group(group)}"
                        )

            should_not_update = self.option("dry-run") or not (
                self.option("update") or self.option("lock")
            )
            if should_not_update:
                self.info("Checking new dependencies can be solved...")
            else:
                self.info("Running Poetry package installer...")

            # Cosmetic new line
            self.line("")

            # Check for a valid installer otherwise it will be hidden with no message
            try:
                assert self.installer is not None
            except AssertionError:
                self.line("Poetry did not instantiate an installer for the plugin.")
                self.line("Aborting!", style="fg=red;options=bold")
                return 1

            try:
                status = run_installer_update(
                    poetry=self.poetry,
                    installer=self.installer,
                    lockfile_only=self.option("lock"),
                    dependencies_by_group={
                        group: (d for _, d in deps)
                        for group, deps in updated_dependencies.items()
                    },
                    poetry_config=poetry_config,
                    dry_run=should_not_update,
                    verbose=self.io.is_verbose(),
                    silent=(
                        # Do not display installer output by default, it's confusing
                        should_not_update
                        and not self.io.is_verbose()
                    ),
                )
            except Exception as exc:
                self.line(str(exc), style="fg=red;options=bold")
                status = 1
            else:
                if self.option("check"):
                    self.line("\nDependency check successful.")
        else:
            if not self.option("check"):
                self.info("Skipping check for valid versions.")

            status = 0

        # Cosmetic new line
        self.line("")

        for group in groups:
            dependency_config = extract_dependency_config_for_group(
                group, poetry_config
            )
            if dependency_config is None:
                continue

            for old_constraint, dependency in updated_dependencies[group]:
                # Mutate the dependency config (and consequently the pyproject config)
                name = dependency.name
                if isinstance(dependency_config[name], dict):
                    dependency_config[name]["version"] = dependency.pretty_constraint
                else:
                    dependency_config[name] = dependency.pretty_constraint

                # Display the final updates since they can be buried by the installer update
                self.info(
                    f"Updated <c1>{dependency.pretty_name}</> constraint from "
                    f"<c2>{old_constraint}</> to <c2>{dependency.pretty_constraint}</>"
                    f"{_pretty_group(group)}"
                )

        if status == 0 and not self.option("dry-run"):
            assert isinstance(pyproject_config, TOMLDocument)
            self.poetry.file.write(pyproject_config)
            self.info("Updated config file with relaxed constraints.")

        elif status != 0:
            self.line(
                "Aborted relax due to failure during dependency update.",
                style="fg=red;options=bold",
            )
        else:
            self.info("Skipped update of config file due to dry-run flag.")

        return status
