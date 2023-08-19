from cleo.events.console_events import COMMAND, TERMINATE
from cleo.events.console_terminate_event import ConsoleTerminateEvent
from cleo.events.event_dispatcher import EventDispatcher
from poetry.console.application import Application
from poetry.console.commands.add import AddCommand
from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_relax.command import RelaxCommand

# Plugin registration with Poetry


def _command_factory() -> RelaxCommand:
    return RelaxCommand()


class RelaxPlugin(ApplicationPlugin):
    def activate(self, application: Application):
        application.command_loader.register_factory("relax", _command_factory)
        application.event_dispatcher.add_listener(TERMINATE, self._auto_relax)  # type: ignore

    def _auto_relax(
        self, event: ConsoleTerminateEvent, event_name: str, dispatcher: EventDispatcher
    ) -> None:
        # Do not run on failed commands
        if event.exit_code:
            return

        # Only run on `poetry add`
        if not isinstance(event.command, AddCommand):
            return

        # Only run on opt-in
        if (
            not event.command.poetry.pyproject.data.get("tool", {})
            .get("poetry-relax", {})
            .get("relax_on_add", False)
        ):
            return

        # Parse options from `poetry add ...` to send to `poetry relax`
        args = []
        group = "dev" if event.command.option("dev") else event.command.option("group")
        if group:
            args.extend(["--only", group])
        if event.command.option("dry-run"):
            args.append("--dry-run")
        if event.command.option("quiet"):
            args.append("--quiet")
        if event.command.option("verbose"):
            args.append("--verbose")
        if event.command.option("lock"):
            args.append("--lock")

        # Write a new line for readability
        event.command.io.write_line("")

        event.set_exit_code(event.command.call("relax", " ".join(args)))
