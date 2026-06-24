"""Hydration helpers for the runtime bridge.

After the cross-process transport plumbing moved to the closed ``pipelex-transport``
library, this package holds only ``hydration.py`` — the working-memory hydration
helpers used by core's ``delivery_executor`` and the open ``pipelex-api`` runner, and
imported across the boundary by ``pipelex-transport`` (they are on the allowed import
surface). It contains no host-runtime-specific imports — only Pipelex core types.
"""
