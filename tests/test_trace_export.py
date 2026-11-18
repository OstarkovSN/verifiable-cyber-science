import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from vcs_trace_export import ExportError, Sanitizer, _build_run, export, export_run, main, parse_trace, render_run
from vcs_messages import plain_feedback


def trace(tmp_path, rows, name="trace.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return path


def test_codex_updates_one_call_and_keeps_result_at_completion(tmp_path):
    rows = [
        {"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "lean Model.lean"}},
        {"type": "item.updated", "item": {"id": "item_1", "type": "command_execution", "command": "lean Model.lean", "aggregated_output": "partial"}},
        {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": "Checking the model."}},
        {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "lean Model.lean", "aggregated_output": "error: unsolved goals", "exit_code": 1}},
        {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "lean Model.lean", "aggregated_output": "error: unsolved goals", "exit_code": 1}},
    ]
    result = parse_trace(trace(tmp_path, rows))
    assert [r["type"] for r in result] == ["tool_call", "message", "tool_result"]
    assert result[0]["call_id"] == result[2]["call_id"]
    assert result[2]["exit_code"] == 1
    assert result[2]["content"] == "error: unsolved goals"
    assert result[2]["source_line"] == 4


def test_claude_message_snapshots_tool_ids_and_private_reasoning(tmp_path):
    rows = [
        {"type": "system", "session_id": "private-session", "account": "private@example.com"},
        {"type": "assistant", "uuid": "a", "message": {"id": "m", "content": [
            {"type": "thinking", "thinking": "do not publish", "signature": "secret"},
            {"type": "text", "text": "First"},
            {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "lean Model.lean"}}]}},
        {"type": "assistant", "uuid": "b", "message": {"id": "m", "content": [
            {"type": "thinking", "thinking": "still private"}, {"type": "text", "text": "First complete"},
            {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "lean Model.lean"}}]}},
        {"type": "user", "uuid": "c", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "tool-1", "content": "passed", "is_error": False}]}},
    ]
    rows.append(rows[-1])
    result = parse_trace(trace(tmp_path, rows))
    assert len(result) == 3
    assert result[0]["content"] == "First complete"
    assert result[1]["call_id"] == result[2]["call_id"]
    assert "private" not in json.dumps(result)
    assert "signature" not in json.dumps(result)


def test_response_item_calls_and_outputs(tmp_path):
    rows = [
        {"type": "response_item", "payload": {"type": "message", "channel": "analysis", "content": [{"type": "output_text", "text": "private"}]}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call1", "arguments": '{"cmd":"lean Model.lean"}'}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "call1", "output": "passed"}},
    ]
    result = parse_trace(trace(tmp_path, rows))
    assert len(result) == 2
    assert result[0]["input"] == {"cmd": "lean Model.lean"}
    assert result[0]["call_id"] == result[1]["call_id"]


def test_sanitizer_does_not_change_scientific_numbers_or_doi():
    clean = Sanitizer({"host-secret": "[private host]"})
    value = clean.text("host-secret /home/alice/project 0.99820675 285 https://doi.org/10.1234/test alice@example.com")
    assert "alice" not in value
    assert "0.99820675 285 https://doi.org/10.1234/test" in value
    assert clean.text("https://example.org/home/author/paper") == "https://example.org/home/author/paper"
    with pytest.raises(ExportError, match="credential"):
        clean.text("api_key='" + "a" * 40 + "'")


def test_secret_rejection_happens_before_output_created(tmp_path):
    f = tmp_path / "Model.lean"
    f.write_text("-- sk-proj-" + "x" * 40)
    mapping = tmp_path / "sources.json"
    mapping.write_text(json.dumps({"runs": [{"id": "run", "task": "task", "harness": "Codex", "cycles": [
        {"produced_code": ["Model.lean"]}]}]}))
    with pytest.raises(ExportError):
        export(mapping, tmp_path / "public")
    assert not (tmp_path / "public").exists()


def test_cycle_boundaries_code_feedback_and_html_escaping(tmp_path):
    (tmp_path / "task.md").write_text("Predict a black ball <script>bad()</script>")
    (tmp_path / "instructions.md").write_text("A long protocol")
    (tmp_path / "clarification.md").write_text("A recorded clarification")
    (tmp_path / "Model.lean").write_text("theorem answer : 2 + 2 = 4 := by decide\n")
    spec = {"id": "balls-codex", "task": "Balls", "harness": {"name": "Codex", "model": "model"},
            "task_file": "task.md", "instructions_file": "instructions.md", "initial_feedback_file": "clarification.md", "cycles": [
                {"id": "cycle-001", "produced_code": ["Model.lean"], "user_feedback": {"decision": "reject", "authority": "personal user", "reason": "<img src=x>"}},
                {"id": "cycle-002", "events": [{"type": "message", "role": "assistant", "content": "revision"}], "user_feedback": {"decision": "accept", "authority": "delegated assistant", "reason": "Acceptance receipt prose", "binding": "receipt-only-binding"}},
            ]}
    run = export_run(spec, tmp_path, Sanitizer())
    assert run["messages"][0]["produced_code"][0]["content"].endswith("by decide\n")
    assert run["messages"][1]["messages"][0]["content"] == "revision"
    assert len(run["messages"][1]["messages"]) == 1
    rendered = render_run(run, "balls-codex", "Balls", ["Study instructions", "Task", "Initial clarification"])
    assert "<script>bad()" not in rendered
    assert "&lt;script&gt;bad()" in rendered
    assert 'href="index.html"' in rendered
    assert 'href="balls-codex.json"' in rendered
    assert run["messages"][1]["user_feedback"] == "accepted"
    assert run["messages"][0]["user_feedback"] == "<img src=x>"
    assert "delegated assistant" not in rendered
    assert "Acceptance receipt prose" not in rendered
    assert "receipt-only-binding" not in rendered
    assert 'id="cycle-002-review" class="feedback" data-searchable>accepted</p>' in rendered
    assert "<title>Balls — Codex</title>" in rendered
    assert "<h1>Balls</h1><p>Codex · model</p>" in rendered
    assert run["task"] == (tmp_path / "task.md").read_text()
    assert '<details class=""><summary>Instructions</summary>' in rendered
    assert '<details class=""><summary>Clarification</summary>' in rendered
    assert '<div class="label">Task</div>' in rendered
    assert 'href="#cycle-001-code"' in rendered
    assert 'id="cycle-001-code"' in rendered
    assert 'href="#cycle-001-review"' in rendered
    assert 'id="cycle-001-review"' in rendered
    assert 'href="#cycle-002-code"' not in rendered


def test_acceptance_feedback_loaded_from_file_is_status_only(tmp_path):
    (tmp_path / "decision.json").write_text(json.dumps({"decision": "accept", "reason": "Private receipt prose"}))
    spec = {"id": "run", "task": "Task", "harness": "Codex", "cycles": [{"user_feedback": "decision.json"}]}
    run = _build_run(spec, tmp_path, Sanitizer())
    assert run["messages"][0]["user_feedback"] == "accepted"
    assert "Private receipt prose" not in json.dumps(run)


def test_sanitized_code_has_distinct_original_and_exported_hashes(tmp_path):
    (tmp_path / "Model.lean").write_text("-- generated in /home/alice/science\ntheorem answer : True := by trivial\n")
    spec = {"id": "run", "task": "Task", "harness": "Codex", "cycles": [{"produced_code": ["Model.lean"]}]}
    run = _build_run(spec, tmp_path, Sanitizer())
    code = run["messages"][0]["produced_code"][0]
    assert code["original_sha256"] != code["exported_sha256"]
    assert "theorem answer : True := by trivial" in code["content"]


def test_publication_omission_is_explicit_and_keeps_tool_call(tmp_path):
    source = trace(tmp_path, [
        {"type": "item.completed", "item": {"id": "i1", "type": "command_execution", "command": "pdftotext article.pdf -", "aggregated_output": "A full paper body", "exit_code": 0}},
    ])
    spec = {"id": "run", "task": "Task", "harness": "Claude", "cycles": [{"traces": [source.name],
        "publication_omissions": {"trace.jsonl:i1": {"doi": "https://doi.org/10.1234/test"}}}]}
    run = export_run(spec, tmp_path, Sanitizer())
    events = run["messages"][0]["messages"]
    assert events[0]["input"]["command"] == "pdftotext article.pdf -"
    assert events[1]["output"] == "https://doi.org/10.1234/test"
    assert "publication_omission" not in json.dumps(run)
    assert "A full paper body" not in json.dumps(run)
    assert 'href="https://doi.org/10.1234/test"' in render_run(run)
    spec["cycles"][0]["publication_omissions"] = {"not-found": {}}
    with pytest.raises(ExportError, match="does not match"):
        export_run(spec, tmp_path, Sanitizer())


def test_added_host_events_are_not_published_as_conversation(tmp_path):
    path = trace(tmp_path, [{"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": "Ready for checking"}}])
    spec = {"id": "run", "task": "Task", "harness": "Codex", "cycles": [{
        "events": [{"type": "message", "role": "user", "content": "Supplied observation"}],
        "traces": [path.name],
        "after_events": [{"type": "host_check", "content": {"verdict": "proved"}}],
    }]}
    messages = export_run(spec, tmp_path, Sanitizer())["messages"][0]["messages"]
    assert [m["type"] for m in messages] == ["message", "message"]


def test_mixed_article_output_retains_exact_scientist_spans(tmp_path):
    source = trace(tmp_path, [{"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
        "command": "cat article.txt; cat report.txt; lean Model.lean", "aggregated_output":
        "Full article body\nSCIENTIST NOTE: heat capacity is negative here.\nCHECKER: proved\n", "exit_code": 0}}])
    omission = {"doi": "https://doi.org/10.1234/first",
                "references": ["https://doi.org/10.1234/first", "https://doi.org/10.5678/second"],
                "retained_output": ["SCIENTIST NOTE: heat capacity is negative here.", "CHECKER: proved\n"]}
    spec = {"id": "run", "task": "Task", "harness": "Codex", "cycles": [{"traces": [source.name],
        "publication_omissions": {"trace.jsonl:i1": omission}}]}
    run = export_run(spec, tmp_path, Sanitizer())
    result = run["messages"][0]["messages"][1]
    assert isinstance(result["output"], str)
    assert result["output"] == ("https://doi.org/10.1234/first\n\nhttps://doi.org/10.5678/second\n\n"
                                 "SCIENTIST NOTE: heat capacity is negative here.\n\nCHECKER: proved\n")
    assert "Full article body" not in json.dumps(result)
    assert 'href="https://doi.org/10.5678/second"' in render_run(run)
    omission["retained_output"] = "A fabricated scientist note"
    with pytest.raises(ExportError, match="not an exact source span"):
        export_run(spec, tmp_path, Sanitizer())


def test_native_structured_tool_output_is_not_treated_as_added_omission(tmp_path):
    native = {"type": "publication_omission", "reason": "a genuine native tool response", "doi": "https://doi.org/10.1234/native"}
    source = trace(tmp_path, [
        {"type": "response_item", "payload": {"type": "function_call", "call_id": "c1", "name": "tool", "arguments": "{}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c1", "output": native}},
    ])
    run = export_run({"id": "run", "task": "Task", "harness": "Codex", "cycles": [{"traces": [source.name]}]}, tmp_path, Sanitizer())
    assert run["messages"][0]["messages"][1]["output"] == native
    assert "a genuine native tool response" in render_run(run)


def test_pdf_files_and_payloads_are_rejected(tmp_path):
    (tmp_path / "article.pdf").write_bytes(b"%PDF-1.7")
    base = {"id": "run", "task": "task", "harness": "Codex"}
    with pytest.raises(ExportError, match="PDF"):
        export_run({**base, "cycles": [{"produced_code": ["article.pdf"]}]}, tmp_path, Sanitizer())
    with pytest.raises(ExportError, match="PDF"):
        export_run({**base, "cycles": [{"events": [{"type": "tool_result", "content": "%PDF-1.7"}]}]}, tmp_path, Sanitizer())


def test_actual_cli_writes_portable_offline_pages(tmp_path):
    mapping = tmp_path / "private-source-map.json"
    mapping.write_text(json.dumps({"runs": [{"id": "run", "task": "Lake", "harness": "Claude", "cycles": [
        {"id": "request-001", "events": [{"role": "assistant", "type": "message", "content": "Please supply observations"}]}]}]}))
    output = tmp_path / "public"
    result = CliRunner().invoke(main, ["--source-map", str(mapping), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert {p.name for p in output.iterdir()} == {"run.json", "run.html", "index.html"}
    assert 'href="run.html"' in (output / "index.html").read_text()
    assert str(tmp_path) not in (output / "run.json").read_text()
    assert "https://" not in (output / "index.html").read_text()


def test_bibliography_publishes_only_titles_and_doi_links(tmp_path):
    (tmp_path / "bibliography.json").write_text(json.dumps({"paper": {"doi": "10.1234/paper", "title": ["A <scp>NaCl</scp> model"], "private_source_path": "/private/raw.pdf"}}))
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"bibliography_file": "bibliography.json", "runs": [{"id": "run", "task": "Task", "harness": "Claude", "cycles": [{}]}]}))
    export(mapping, tmp_path / "out")
    refs = json.loads((tmp_path / "out/references.json").read_text())
    assert refs == [{"title": "A NaCl model", "doi": "https://doi.org/10.1234/paper"}]
    index = (tmp_path / "out/index.html").read_text()
    assert 'href="https://doi.org/10.1234/paper"' in index
    assert "/private/raw.pdf" not in index


def test_public_projection_has_only_requested_fields_and_keeps_native_content(tmp_path):
    (tmp_path / "Model.lean").write_text("theorem answer : True := by trivial\n")
    native_output = '{"source_sha256":"historical-value","binding":"old-native-receipt"}'
    source = trace(tmp_path, [
        {"type": "item.completed", "item": {"id": "opaque-tool-id", "type": "command_execution", "command": "cat old-receipt.json", "aggregated_output": native_output, "exit_code": 1}},
        {"type": "item.completed", "item": {"id": "assistant-id", "type": "agent_message", "text": "Human TUI feedback: this native message stays exact."}},
    ])
    spec = {"id": "test-run", "task": "Task", "harness": {"name": "Codex", "requested_model": "selected-model", "client_sha256": "private-hash"}, "cycles": [{
        "id": "attempt-number", "traces": [source.name], "produced_code": ["Model.lean"],
        "events": [{"type": "external_response", "timestamp": "private-time", "content": {"id": "private-id", "source_sha256": "private-hash", "response": "Human TUI feedback: derive Cs from the supplied synthetic data."}}],
        "after_events": [{"type": "submission", "content": {"binding": "private-binding"}}, {"type": "checker_result", "content": {"source_sha256": "private-hash"}}],
        "user_feedback": {"decision": "reject", "reason": "Human TUI feedback: prove Cs >= 0 from the model.", "review_authority": "irrelevant role", "binding": "private-binding"},
    }]}
    run = export_run(spec, tmp_path, Sanitizer())
    assert set(run) == {"task", "harness", "messages"}
    assert run["harness"] == {"name": "Codex", "model": "selected-model"}
    cycle = run["messages"][0]
    assert set(cycle) == {"messages", "produced_code", "user_feedback"}
    assert set(cycle["produced_code"][0]) == {"name", "content"}
    assert cycle["user_feedback"] == "prove Cs >= 0 from the model."
    assert cycle["messages"][0] == {"type": "message", "role": "user", "content": "derive Cs from the supplied synthetic data."}
    assert cycle["messages"][2]["output"] == native_output
    assert cycle["messages"][3]["content"] == "Human TUI feedback: this native message stays exact."
    assert cycle["messages"][1]["call_id"] == cycle["messages"][2]["call_id"] == "opaque-tool-id"
    assert all("source" not in m and "source_line" not in m and "timestamp" not in m for m in cycle["messages"])
    rendered = render_run(run, "test-run", "Task")
    assert "opaque-tool-id" not in rendered
    assert "Harness and model" not in rendered
    assert "private-hash" not in rendered
    assert "shell input" in rendered and "shell output · exit 1" in rendered


def test_plain_feedback_removes_role_boilerplate_preserving_science_and_quotes():
    text = ('Operator scientific review under the user instruction to finish the remaining cycles.\n\n'
            'Human TUI feedback: derive the parameters from the supplied SYNTHETIC observations.\n\n'
            'Human instruction, verbatim:\n"Do not assume Cs is positive."\n\n'
            "No other agent's model, numerical results or proof are supplied. No scientific acceptance is given.")
    result = plain_feedback(text)
    assert result == 'derive the parameters from the supplied SYNTHETIC observations.\n\n"Do not assume Cs is positive."'
    assert plain_feedback(result) == result
    quote = '"Human TUI feedback: preserve this actual quotation."'
    assert plain_feedback(quote) == quote
    assert plain_feedback('Human instruction, verbatim: "Calculate Phi inside Lean. Is claude fish done?"') == '"Calculate Phi inside Lean."'
    assert plain_feedback('"Connect the case to reality. Btw, what claude do we use? Sonnet?"') == '"Connect the case to reality."'
    assert plain_feedback('"Can you derive the parameter?"') == '"Can you derive the parameter?"'


def test_private_audit_is_optional_and_never_written_into_public_output(tmp_path):
    (tmp_path / "Model.lean").write_text("theorem answer : True := by trivial\n")
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"runs": [{"id": "run", "task": "Task", "harness": "Claude", "cycles": [{"produced_code": ["Model.lean"]}]}]}))
    audit = tmp_path / "private/audit.json"
    export(mapping, tmp_path / "out", audit)
    assert audit.exists()
    assert not (tmp_path / "out/manifest.json").exists()
    assert "original_sha256" in audit.read_text()
    assert "original_sha256" not in (tmp_path / "out/run.json").read_text()
