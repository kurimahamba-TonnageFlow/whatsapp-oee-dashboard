"""
Shared safety gate for every manual live-integration script in this
folder.

None of these scripts are pytest tests. Each performs real reads
and/or writes against the live Supabase database when run directly
(`python scripts/manual_integration/<name>.py`). Importing this module
itself has no side effects - it only defines a function that a script
calls from inside its own run(), guarded by
`if __name__ == "__main__": run()`, never at import time.
"""

import os
import sys

ENV_VAR = "PULSE_ALLOW_LIVE_INTEGRATION"
CONFIRMATION_VALUE = "yes-run-against-live-supabase"


def require_live_confirmation(script_name, description):
    """Refuses to proceed (exits the process) unless the operator has
    explicitly opted in via an environment variable set to an exact,
    hard-to-type-by-accident phrase. Call this as the first line of a
    script's run() - never at import time or at module level."""
    print("=" * 70)
    print(f"MANUAL LIVE INTEGRATION SCRIPT: {script_name}")
    print(description)
    print()
    print("This performs REAL operations against the LIVE Supabase database.")
    print("It never runs on import and is never collected or run by pytest.")
    print(f"To proceed, set {ENV_VAR}={CONFIRMATION_VALUE!r} in the environment and re-run.")
    print("=" * 70)

    if os.environ.get(ENV_VAR) != CONFIRMATION_VALUE:
        print(f"\nRefusing to run: {ENV_VAR} is not set to the required confirmation value.")
        sys.exit(1)

    print("\nConfirmation received - proceeding against the LIVE database.\n")
