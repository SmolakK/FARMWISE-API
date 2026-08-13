"""Source-checkout compatibility wrapper.

Installed users should run ``farmwise-api`` or import
``farmwise_api.server.main:app``. This top-level module is deliberately not
included in the wheel.
"""

from farmwise_api.cli import __getattr__, run

__all__ = ["app", "run"]


if __name__ == "__main__":
    run()
