#!/bin/sh
set -eu
# HOME is fresh tmpfs; Docker creates bind-mount parents as root. Mount only the
# native credential file and symlink it into an independently writable HOME.
if [ -f /native-auth/auth.json ]; then
    mkdir -p "$HOME/.codex"
    ln -s /native-auth/auth.json "$HOME/.codex/auth.json"
fi
if [ -f /native-auth/claude-credentials.json ]; then
    mkdir -p "$CLAUDE_CONFIG_DIR"
    ln -s /native-auth/claude-credentials.json "$CLAUDE_CONFIG_DIR/.credentials.json"
    # Fresh non-account preferences only. Never copy host ~/.claude.json.
    printf '%s\n' '{"hasCompletedOnboarding":true,"bypassPermissionsModeAccepted":true}' > "$CLAUDE_CONFIG_DIR/.claude.json"
fi
exec "$@"
