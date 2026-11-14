"""Lower layer shared by commands — emitting results · state · devices · browser · processes.

This layer never imports `commands/`. Dependencies always flow downward: commands → runtime.
Behavior that branches on `sys.platform` lives only in `procs.py`.
"""
