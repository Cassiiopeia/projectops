"""`web` actions — one module per action.

New action: put a module in this folder that exports `ACTION = Action(name=..., run=..., needs=..., configure=...)`.
`web` scans this folder via `registry.discover_actions`, so `commands/web/__init__.py` needs no change.
For `needs`, see `registry.NEEDS`.
"""
