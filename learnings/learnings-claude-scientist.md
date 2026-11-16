## Implementer
- Claude Code 2.1.325 `--bare` explicitly disables OAuth/keychain and requires API-key auth; isolated subscription runs must omit it and instead use a fresh HOME plus project/local settings and strict MCP config.
- With `CLAUDE_CONFIG_DIR` set, Claude's minimal fresh onboarding preferences belong at `$CLAUDE_CONFIG_DIR/.claude.json`; standalone readonly credentials symlinked at `$CLAUDE_CONFIG_DIR/.credentials.json` suffice for real Docker `auth status` without copying host profile state.
- Claude stream-json can return exit zero for `error_max_turns` and error results; host acceptance must require terminal `type=result`, `subtype=success`, `is_error=false` and stop on structured auth/quota errors.
