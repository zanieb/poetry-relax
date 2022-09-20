from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_relax.command import RelaxCommand

# Plugin registration with Poetry


def _command_factory() -> RelaxCommand:
    return RelaxCommand()


class RelaxPlugin(ApplicationPlugin):
    def activate(self, application: Application):
        application.command_loader.register_factory("relax", _command_factory)
