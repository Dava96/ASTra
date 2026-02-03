import os
import sys

# Ensure the project root is in sys.path so 'astra' can be imported correctly.
# This avoids the hang caused by adding '.' (the tests directory) to the path.
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
