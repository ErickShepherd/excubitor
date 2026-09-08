# Legacy Claude guard integration

This is the older hook installation surface. It is separate from the Ralph CLI;
use the [current installation guide](install.md) and [quickstart](ralph-quickstart.md)
for explicitly started jobs. Do not run this installer as part of ordinary CLI setup.

These hooks register at Claude user scope. In particular the default-branch guard
can affect ordinary edits even without a loop. The environment-based guards have
different activation conditions. This integration does not establish task-scoped
unattended support for another vendor or a verified sandbox.

## Historical installation commands

Requires Python 3.11+ and `git`. For Claude Code:

```bash
git clone https://github.com/ErickShepherd/excubitor.git && cd excubitor
scripts/install.sh          # symlinks skills/* and hooks/* into ~/.claude, and idempotently
                            # registers the four guards in ~/.claude/settings.json
```

Or register the hooks by hand in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Edit|Write|NotebookEdit",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-default-branch.py", "timeout": 10}]},
      {"matcher": "Bash",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-loop-vc.py", "timeout": 10}]},
      {"matcher": "*",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-one-unit.py", "timeout": 10}]},
      {"matcher": "Bash|Edit|Write|NotebookEdit",
       "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/guard-self-integrity.py", "timeout": 10}]}
    ]
  }
}
```
