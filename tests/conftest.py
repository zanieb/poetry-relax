import pytest

# Improve diff display for assertions in utilities
# Note: This must occur before import of the module
pytest.register_assert_rewrite("tests._utilities")

from ._fixtures import *
