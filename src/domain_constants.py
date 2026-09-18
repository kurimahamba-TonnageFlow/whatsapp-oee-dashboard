# ==========================================================
# TONNAGEFLOW PULSE
# Domain Constants
# ==========================================================
#
# Side-effect-free. No imports beyond the standard library, no
# input(), no I/O, nothing that runs a moment after this module is
# imported. Safe for both the HTTP API (src/engineering_api.py) and
# the interactive CLI (src/main.py) to import without pulling in the
# other.
#
# ENGINEERS is the single source of truth for the approved engineer
# names - src/main.py's CLI and src/engineering_api.py's login
# validation both read this same tuple, so the list is never
# duplicated. Order matches src/main.py's original, pre-existing
# `engineers` list exactly (not alphabetical, not the PDF handover's
# listing order) - the CLI's numbered "1 - Aaron, 2 - Yago, ..." menu
# depends on this order, so it must never change without a deliberate
# decision to change CLI behaviour.

ENGINEERS = (
    "Aaron",
    "Yago",
    "Steve",
    "Dan",
    "Kuri",
    "Alfie",
)
