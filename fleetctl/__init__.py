"""fleetctl - the .fleet remote agent runner dispatcher core.

This package is the single source of truth for the fleet dispatcher logic:
normalizing PM webhooks, resolving repos from the central registry, parsing
the per-repo ``.fleet/`` contract, rendering prompts, generating the trusted
host-side COI config, executing the bounded setup/agent/verify loop, and
publishing the result as a GitHub PR.

The Jenkins shared library (``vars/fleetDispatcher.groovy``) is a thin
orchestration wrapper around the ``fleetctl`` CLI so the same logic is used
locally (P0 smoke tests) and under Jenkins (P1/P2/P3).
"""

__version__ = "0.1.0"
