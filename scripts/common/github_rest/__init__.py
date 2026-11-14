"""gh_client implementation modules. Callers come in only through `common.gh_client`.

Calls between modules go through `client.X` (common.gh_client), so tests that swap gh_client attributes also affect internal calls.
"""

# Make gh_client complete first even when a submodule is imported directly (fixes circular import order)
from common import gh_client  # noqa: F401
