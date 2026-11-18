# Scientist run traces

Open [index.html](index.html) locally or use the [web viewer](https://ostarkovsn.github.io/verifiable-cyber-science/traces/). Each of the four tasks has a Codex run and a Claude Code run. The HTML and JSON present the same exported records.

Each run JSON has these fields:

```json
{
  "task": "The complete natural-language question",
  "harness": {"name": "Native client", "requested_model": "Recorded model"},
  "messages": [
    {
      "id": "cycle-001",
      "messages": [],
      "produced_code": [],
      "user_feedback": []
    }
  ]
}
```

`messages` groups the recorded activity by scientist cycle. Its nested message list contains the supplied study inputs, agent messages, tool calls and results, operator responses, submitted scientific report and independent checking results. Tool results retain their call identifiers. `produced_code` contains the full submitted Lean proof, its review extraction and retained checker snapshots referenced in that cycle. `user_feedback` preserves the decision and reason, with the review authority identified. A cycle ending in a request or interruption can have no review decision.

Study instruction and task files are shown as inputs. The launcher assembled its stdin prompt from these files, the cycle number and the accumulated decisions and responses; no separate verbatim stdin-prompt capture was retained. Native events without timestamps remain untimed. The recovered Claude lake stream replaces its overlapping prefix once.

The public projection omits credentials, provider reasoning blocks and binary attachments, normalizes private host paths, and replaces article bodies or page images with DOI references. Original tool calls and their result associations remain visible. Code records contain both the original source hash and the exported-content hash. PDFs are not included.

## Export saved runs

```sh
uv run vcs-trace-export --source-map /path/to/source-map.json --output traces
```

The source map points to retained native logs and frozen proof/decision files. It stays outside the published output. The exporter accepts explicit per-cycle input responses, checking records and publication omissions, so a reviewed source map determines the export without guessing which proof or decision belongs to a cycle.
