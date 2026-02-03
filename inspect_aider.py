
import aider

try:
    import aider.repo as repo_module
    print("Found aider.repo")
    print(dir(repo_module))
except ImportError:
    print("aider.repo not found")

print("\nAider contents:")
print(dir(aider))

# Try to find GitRepo
import pkgutil

print("\nScanning aider submodules:")
if hasattr(aider, "__path__"):
    for module_info in pkgutil.iter_modules(aider.__path__):
        print(f" - {module_info.name}")
