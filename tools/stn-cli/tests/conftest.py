"""Keep the suite hermetic: stn_cli.tui loads the user theme at import time,
so point resolution at a path that cannot exist before any test imports it.
Individual theme tests pass explicit paths and are unaffected."""

import os

os.environ["STN_CONFIG"] = "/nonexistent/stn-test-no-theme.toml"
