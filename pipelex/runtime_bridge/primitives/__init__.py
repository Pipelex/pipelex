"""Boundary primitives for the runtime bridge.

Working-memory hydration (``hydration.py``) and library + memory rehydration
(``rehydration.py``): the helpers a receiver of a transported payload uses to
rebuild typed state. Used by core's ``delivery_executor``, the transported
PipeFunc path, and the open ``pipelex-api`` runner, and imported by out-of-tree
transport/orchestration plugins (they are on the allowed import surface). No
host-runtime-specific imports — only Pipelex core types.
"""
