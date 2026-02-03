import os

import astra
import astra.core.orchestrator


def test_print_paths():
    print(f"\nDEBUG: astra.__file__ = {astra.__file__}")
    print(f"DEBUG: astra.core.orchestrator.__file__ = {astra.core.orchestrator.__file__}")
    print(f"DEBUG: os.getcwd() = {os.getcwd()}")
