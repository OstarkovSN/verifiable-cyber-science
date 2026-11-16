#!/bin/sh
set -eu
# HOME is fresh tmpfs; Docker creates bind-mount parents as root. Keep the
# native client home writable without copying the read-only native auth file.
mkdir -p "$HOME/.codex"
if [ -f /native-auth/auth.json ]; then
    ln -s /native-auth/auth.json "$HOME/.codex/auth.json"
fi
exec "$@"
