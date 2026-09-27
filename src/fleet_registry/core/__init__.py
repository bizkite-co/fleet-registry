"""Business logic shared by the CLI and TUI.

Nothing in this package prints or imports Rich/Textual; functions return data
(pydantic models, dataclasses) and raise ``FleetError`` subclasses on failure.
"""


class FleetError(Exception):
    """Base class for errors the front-ends should show to the user verbatim."""
