# users/utils/__init__.py
#
# When this package was created, Python stopped resolving `from .utils import …`
# to the flat utils.py file and started treating utils/ as the package.
# We load the flat file via importlib (by path) and register it in sys.modules
# so every existing import in views.py and management commands continues to work.

import sys as _sys
import importlib.util as _ilu
import os as _os

_flat_name = "users._utils_flat"
if _flat_name not in _sys.modules:
    _spec = _ilu.spec_from_file_location(
        _flat_name,
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "utils.py"),
    )
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules[_flat_name] = _mod
    _spec.loader.exec_module(_mod)

else:
    _mod = _sys.modules[_flat_name]

# Dynamic symbol forwarding: Expose all public symbols and functions from the flat utils.py
for _attr in dir(_mod):
    if not _attr.startswith('_'):
        globals()[_attr] = getattr(_mod, _attr)

__all__ = [attr for attr in dir(_mod) if not attr.startswith('_')]




