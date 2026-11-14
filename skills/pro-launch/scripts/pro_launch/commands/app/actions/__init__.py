"""`app` actions — one module per action.

New action: put a module in this folder that exports `ACTION = Action(name=..., run=..., configure=...)`.
Platform differences are handled by the backends in `scripts/app_input.py`, so actions need not know the platform.
"""
