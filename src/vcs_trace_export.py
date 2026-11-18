"""Export native scientist records as portable JSON and offline HTML.

The source map is private input: only selected scientific messages, tool activity,
produced files and review records are published. No inference is run by this tool.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any

import click


class ExportError(ValueError):
    """An input cannot be exported faithfully or safely."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk-proj-|sk-ant-|sk-or-v1-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b\d{7,12}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"(?i)\b(?:access_token|refresh_token|api_key|apiKey|authorization)\s*[\"']?\s*[:=]\s*[\"'](?:Bearer\s+)?[A-Za-z0-9_./+~-]{20,}"),
]


class Sanitizer:
    """Redact configured identifiers, then reject remaining credential values."""

    def __init__(self, replacements=None, redactions=None):
        self.replacements = sorted((replacements or {}).items(), key=lambda x: -len(x[0]))
        self.redactions = [(re.compile(x["pattern"]), x.get("replacement", "[redacted]"))
                           for x in redactions or []]
        self.counts: Counter[str] = Counter()

    def text(self, value: str) -> str:
        for before, after in self.replacements:
            if not before:
                raise ExportError("Empty literal redaction")
            self.counts["configured_literal"] += value.count(before)
            value = value.replace(before, after)
        for pattern, replacement in self.redactions:
            value, count = pattern.subn(replacement, value)
            self.counts["configured_pattern"] += count
        # Home-directory identities are transport metadata, not scientific input.
        value, count = re.subn(r"(?<![A-Za-z0-9.:/])/home/[^/\s\"'<>]+", "/home/[user]", value)
        self.counts["home_identity"] += count
        value, count = re.subn(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b",
                              "[email]", value)
        self.counts["email"] += count
        for pattern in SECRET_PATTERNS:
            if pattern.search(value):
                # Never echo the value or its containing line into an exception.
                raise ExportError("Possible credential found in selected export content")
        return value

    def clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.clean(x) for x in value]
        if isinstance(value, dict):
            return {self.text(str(k)): self.clean(v) for k, v in value.items()}
        return value


def _content(value: Any) -> Any:
    """Strip private reasoning blocks even when nested in tool-result content."""
    if isinstance(value, list):
        return [_content(x) for x in value if not isinstance(x, dict)
                or x.get("type") not in {"thinking", "redacted_thinking", "reasoning"}]
    if isinstance(value, dict):
        if value.get("type") in {"thinking", "redacted_thinking", "reasoning"}:
            return {"type": "private_reasoning_omitted"}
        if value.get("type") in {"image", "image_url", "document", "input_image"}:
            return {"type": "attachment_omitted", "reason": "Binary attachment omitted from the text export"}
        return {k: _content(v) for k, v in value.items()}
    return value


def parse_trace(path: Path, label: str | None = None, format: str | None = None) -> list[dict]:
    """Normalize recorded messages without duplicating streaming snapshots.

    Calls are emitted at their first recorded occurrence and filled with final
    arguments when a completed snapshot arrives. Results remain at completion.
    """
    label = label or path.name
    out: list[dict] = []
    calls: dict[str, dict] = {}
    messages: dict[str, dict] = {}
    results: dict[str, dict] = {}
    uuid_seen: set[str] = set()

    def event(line, kind, **fields):
        item = {"type": kind, "source": label, "source_line": line, **fields}
        out.append(item)
        return item

    def call(line, native_id, name, args, timestamp=None):
        ident = f"{label}:{native_id}"
        if ident not in calls:
            calls[ident] = event(line, "tool_call", role="assistant", call_id=ident,
                                native_id=native_id, name=name, input=_content(args),
                                **({"timestamp": timestamp} if timestamp else {}))
        else:
            calls[ident]["input"] = _content(args)
        return ident

    def result(line, native_id, content, timestamp=None, **fields):
        ident = f"{label}:{native_id}"
        fields = {k: v for k, v in fields.items() if v is not None}
        if ident not in results:
            results[ident] = event(line, "tool_result", role="tool", call_id=ident,
                                   content=_content(content), **fields,
                                   **({"timestamp": timestamp} if timestamp else {}))
        else:
            results[ident].update(content=_content(content), **fields)

    for line_no, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            event(line_no, "trace_diagnostic", role="system", content=raw)
            continue
        if not isinstance(row, dict):
            raise ExportError(f"Trace row is not an object: {label}:{line_no}")
        uid = row.get("uuid")
        if uid and uid in uuid_seen:
            continue
        if uid:
            uuid_seen.add(uid)
        typ, timestamp = row.get("type"), row.get("timestamp")
        if typ == "response_item":
            payload = row.get("payload", {})
            ptype = payload.get("type")
            if ptype == "function_call":
                arguments = payload.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        pass
                call(line_no, payload["call_id"], payload.get("name", "tool"), arguments, timestamp)
            elif ptype == "function_call_output":
                result(line_no, payload["call_id"], payload.get("output", ""), timestamp)
            elif ptype == "message" and payload.get("channel") != "analysis":
                for block in payload.get("content", []):
                    if block.get("type") in {"input_text", "output_text", "text"}:
                        event(line_no, "message", role=payload.get("role", "assistant"),
                              content=block.get("text", ""),
                              **({"timestamp": timestamp} if timestamp else {}))
        elif typ in {"item.started", "item.updated", "item.completed"}:
            item = row.get("item", {})
            itype = item.get("type")
            ident = item.get("id", f"line-{line_no}")
            if itype == "reasoning":
                continue
            if itype == "agent_message":
                if typ != "item.completed":
                    continue
                key = f"{label}:{ident}"
                if key not in messages:
                    messages[key] = event(line_no, "message", role="assistant", native_id=ident,
                                           content=item.get("text", ""))
                else:
                    messages[key]["content"] = item.get("text", "")
            elif itype == "command_execution":
                call(line_no, ident, "shell", {"command": item.get("command", "")}, timestamp)
                if typ == "item.completed":
                    result(line_no, ident, item.get("aggregated_output", ""), timestamp,
                           exit_code=item.get("exit_code"), status=item.get("status"))
            elif itype in {"mcp_tool_call", "web_search", "file_change"}:
                inputs = {k: v for k, v in item.items()
                          if k not in {"id", "type", "result", "results", "error", "status"}}
                call(line_no, ident, itype, inputs, timestamp)
                if typ == "item.completed":
                    payload = {k: item[k] for k in ["result", "results", "error", "status"] if k in item}
                    result(line_no, ident, payload, timestamp)
            elif typ == "item.completed":
                event(line_no, "activity", role="assistant", content=_content(item))
        elif typ in {"assistant", "user"}:
            message = row.get("message", {})
            content = message.get("content", [])
            if isinstance(content, str):
                event(line_no, "message", role=typ, content=content,
                      **({"timestamp": timestamp} if timestamp else {}))
                continue
            for index, block in enumerate(content):
                btype = block.get("type")
                if btype in {"thinking", "redacted_thinking", "reasoning"}:
                    continue
                if btype == "text":
                    key = f"{label}:{message.get('id', uid or line_no)}:{index}"
                    if key not in messages:
                        messages[key] = event(line_no, "message", role=typ, content=block.get("text", ""),
                                               **({"timestamp": timestamp} if timestamp else {}))
                    else:
                        messages[key]["content"] = block.get("text", "")
                elif btype == "tool_use":
                    call(line_no, block["id"], block.get("name", "tool"), block.get("input", {}), timestamp)
                elif btype == "tool_result":
                    result(line_no, block["tool_use_id"], block.get("content", ""), timestamp,
                           is_error=block.get("is_error", False))
                else:
                    event(line_no, "message_content", role=typ, content=_content(block))
        elif typ == "result":
            if row.get("result"):
                final = row["result"]
                if not any(x.get("type") == "message" and x.get("role") == "assistant"
                           and x.get("content") == final for x in out[-8:]):
                    event(line_no, "message", role="assistant", content=final)
            event(line_no, "client_outcome", role="system", status=row.get("subtype"),
                  is_error=row.get("is_error", False),
                  **({"errors": _content(row["errors"])} if row.get("errors") else {}))
        elif typ in {"error", "turn.failed"}:
            event(line_no, "client_error", role="system", content=_content(row.get("error", row.get("message", row))))
        # Startup/account/usage/system telemetry is not conversational content.
    return out


def _path(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _file(base: Path, spec: str | dict, *, kind="code") -> dict:
    if isinstance(spec, str):
        spec = {"path": spec}
    path = _path(base, spec["path"])
    if path.suffix.lower() == ".pdf":
        raise ExportError("PDF files cannot be included in the text export")
    raw = path.read_bytes()
    return {"name": spec.get("name", path.name), "kind": spec.get("kind", kind),
            "content": raw.decode("utf-8"), "source_sha256": digest(raw), "original_sha256": digest(raw)}


def _feedback(base: Path, value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(_path(base, value).read_text())
    return value if value is not None else []


def _text_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _text_parts(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _text_parts(item)]
    return []


def export_run(spec: dict, base: Path, sanitizer: Sanitizer) -> dict:
    ident = spec["id"]
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", ident):
        raise ExportError("Run id must be a portable filename")
    cycles = []
    input_messages = []
    task = spec["task"]
    for key, label in [("instructions_file", "Study instructions"), ("task_file", "Task"),
                       ("initial_feedback_file", "Initial clarification")]:
        if spec.get(key):
            f = _file(base, spec[key], kind="input")
            if key == "task_file":
                task = f["content"]
            input_messages.append({"type": "message", "role": "user", "label": label,
                                   "content": f["content"], "source_sha256": f["source_sha256"]})
    sources = []
    for number, cycle in enumerate(spec.get("cycles", []), 1):
        messages = list(input_messages) if number == 1 else []
        if cycle.get("prompt_file"):
            f = _file(base, cycle["prompt_file"], kind="prompt")
            messages.append({"type": "message", "role": "user", "label": "Complete cycle prompt",
                             "content": f["content"], "source_sha256": f["source_sha256"]})
        messages.extend(cycle.get("events", []))
        for trace in cycle.get("traces", []):
            if isinstance(trace, str):
                trace = {"path": trace}
            path = _path(base, trace["path"])
            label = trace.get("label", path.name)
            sources.append({"name": label, "sha256": digest(path.read_bytes())})
            messages.extend(parse_trace(path, label, trace.get("format")))
        messages.extend(cycle.get("after_events", []))
        omissions = cycle.get("publication_omissions", {})
        applied = set()
        for message in messages:
            if message.get("type") != "tool_result" or message.get("call_id") not in omissions:
                continue
            key = message["call_id"]
            omission = omissions[key]
            doi = omission.get("doi")
            if doi and not re.fullmatch(r"https://doi\.org/10\.[^\s]+", doi):
                raise ExportError("Publication omission DOI must be an https://doi.org/ URL")
            retained = omission.get("retained_output")
            if retained is not None:
                spans = retained if isinstance(retained, list) else [retained]
                original_text = "\n".join(_text_parts(message.get("content")))
                if any(not isinstance(span, str) or span not in original_text for span in spans):
                    raise ExportError(f"Retained publication output is not an exact source span: {key}")
            message["content"] = {"type": "publication_omission",
                                  "reason": omission.get("reason", "Full article content omitted from publication"),
                                  **({k: omission[k] for k in ["doi", "source_url", "references", "retained_output"]
                                      if omission.get(k) is not None})}
            applied.add(key)
        if set(omissions) - applied:
            raise ExportError(f"Publication omission does not match a tool result in {ident}/{cycle.get('id', number)}")
        block = {"id": cycle.get("id", f"cycle-{number:03d}"), "messages": messages,
                 "produced_code": [_file(base, f) for f in cycle.get("produced_code", [])],
                 "user_feedback": _feedback(base, cycle.get("user_feedback"))}
        if cycle.get("status"):
            block["status"] = cycle["status"]
        cycles.append(block)
    if not cycles:
        raise ExportError(f"Run {ident} has no cycles")
    result = sanitizer.clean({"id": ident, "task": task, "task_title": spec.get("task_title", spec["task"]),
                              "harness": spec["harness"],
                              "messages": cycles, "sources": sources})
    serialized = json.dumps(result)
    if re.search(r"JVBERi0[A-Za-z0-9+/=]{20,}|%PDF-\d", serialized):
        raise ExportError("PDF content cannot be included in the text export")
    # Exported-content hashes describe the actual text the reader receives.
    for cycle in result["messages"]:
        for code in cycle["produced_code"]:
            code["sha256"] = digest(code["content"].encode())
            code["exported_sha256"] = code["sha256"]
    return result


STYLE = """
:root{color-scheme:light dark}*{box-sizing:border-box}body{max-width:1160px;margin:32px auto;padding:0 20px;font:16px/1.55 system-ui,sans-serif;color:#1f2937;background:#fff}h1{font-size:1.9rem;line-height:1.2}h2{margin-top:2rem}a{color:#175cd3}nav,.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:16px 0}input,button{font:inherit;padding:8px 12px;border:1px solid #aab5c3;border-radius:5px}input{flex:1;min-width:180px}details{border:1px solid #d0d7de;border-radius:6px;margin:10px 0;overflow:hidden}summary{cursor:pointer;padding:12px;background:#f5f7fa;font-weight:600;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;padding:14px;font:13px/1.5 ui-monospace,SFMono-Regular,monospace}.message{border-left:3px solid #b8c9df;padding:0 14px;margin:14px 0}.label{font-size:.85rem;color:#526174}.feedback{border-color:#b1cdbb}.feedback summary{background:#f0f8f2}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{text-align:left;border-bottom:1px solid #d8dee6;padding:12px;vertical-align:top;overflow-wrap:anywhere}.chips{display:flex;gap:8px;flex-wrap:wrap}.chip{padding:2px 8px;border-radius:12px;background:#eef2f8;font-size:.85rem}.hidden,[hidden]{display:none!important}@media(prefers-color-scheme:dark){body{background:#111827;color:#e5e7eb}summary{background:#1f2937}details,th,td{border-color:#455268}a{color:#91baff}.label{color:#bdc9d9}.feedback summary{background:#18372a}.chip{background:#27354a}}
"""


SCRIPT = """
const search=document.querySelector('#search');
if(search)search.addEventListener('input',()=>{const q=search.value.toLowerCase();document.querySelectorAll('[data-searchable]').forEach(el=>{el.hidden=!el.textContent.toLowerCase().includes(q);el.querySelectorAll('details').forEach(d=>{if(q){if(!('searchWasOpen'in d.dataset))d.dataset.searchWasOpen=String(d.open);d.open=!el.hidden}else if('searchWasOpen'in d.dataset){d.open=d.dataset.searchWasOpen==='true';delete d.dataset.searchWasOpen}})});});
document.querySelectorAll('[data-expand]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('details').forEach(d=>d.open=b.dataset.expand==='yes')}));
"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def pretty(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def linked_text(value: Any) -> str:
    """Escape trace content and make DOI URLs directly usable by readers."""
    value = pretty(value)
    pattern = re.compile(r'https://doi\.org/10\.\d{4,9}/[^\s<>"\]}]+')
    parts, offset = [], 0
    for match in pattern.finditer(value):
        url = match.group().rstrip(".,;")
        parts.append(esc(value[offset:match.start()]))
        parts.append(f'<a href="{esc(url)}" rel="noreferrer">{esc(url)}</a>')
        offset = match.start() + len(url)
    parts.append(esc(value[offset:]))
    return "".join(parts)


def details(title, content, class_name="", opened=False):
    return (f'<details class="{esc(class_name)}"' + (" open" if opened else "") + ">"
            f"<summary>{esc(title)}</summary><pre>{linked_text(content)}</pre></details>")


def page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{STYLE}</style></head><body>{body}'
            f'<script>{SCRIPT}</script></body></html>')


def render_run(run: dict) -> str:
    ident, task = run["id"], run.get("task_title", run["task"])
    harness = run["harness"]
    harness_label = harness.get("name", ident) if isinstance(harness, dict) else harness
    body = (f'<nav><a href="index.html">All runs</a><a href="{esc(ident)}.json" download>Download JSON</a></nav>'
            f'<h1>{esc(task)}</h1><p>{esc(harness_label)}</p>'
            '<div class="controls"><input id="search" type="search" aria-label="Search this run" placeholder="Search messages, code and feedback">'
            '<button data-expand="yes">Expand all</button><button data-expand="no">Collapse all</button></div>')
    if isinstance(harness, dict):
        body += details("Harness and model", harness)
    body += '<nav aria-label="Cycles">' + " ".join(
        f'<a href="#{esc(c["id"])}">{esc(c["id"])}</a>' for c in run["messages"]) + '</nav>'
    for cycle in run["messages"]:
        body += f'<section id="{esc(cycle["id"])}"><h2>{esc(cycle["id"])}</h2>'
        if cycle.get("status"):
            body += f'<p class="chip">{esc(cycle["status"])}</p>'
        body += (f'<nav aria-label="{esc(cycle["id"])} sections">'
                 f'<a href="#{esc(cycle["id"])}-messages">Messages</a>')
        if cycle["produced_code"]:
            body += f'<a href="#{esc(cycle["id"])}-code">Code</a>'
        if cycle["user_feedback"]:
            body += f'<a href="#{esc(cycle["id"])}-review">Review</a>'
        body += f'</nav><h3 id="{esc(cycle["id"])}-messages">Messages</h3>'
        for message in cycle["messages"]:
            typ = message.get("type", "message")
            if typ == "message":
                message_label = message.get("label", message.get("role", "Message"))
                if message_label in {"Study instructions", "Initial clarification"}:
                    body += '<div data-searchable>' + details(message_label, message.get("content", "")) + '</div>'
                else:
                    body += (f'<article class="message" data-searchable><div class="label">{esc(message_label)}</div>'
                             f'<pre>{linked_text(message.get("content", ""))}</pre></article>')
            else:
                title = (message.get("name") or typ.replace("_", " "))
                if message.get("call_id"):
                    title += " · " + message["call_id"]
                body += '<div data-searchable>' + details(title, message) + '</div>'
        if cycle["produced_code"]:
            body += f'<h3 id="{esc(cycle["id"])}-code">Produced code</h3>'
            for code in cycle["produced_code"]:
                body += '<div data-searchable>' + details(code["name"], code["content"]) + '</div>'
        if cycle["user_feedback"]:
            body += (f'<div id="{esc(cycle["id"])}-review" data-searchable>'
                     + details("Review feedback", cycle["user_feedback"], "feedback", True) + '</div>')
        body += '</section>'
    return page(f"{task} — {harness_label}", body)


def render_index(runs: list[dict], references: list[dict] | None = None) -> str:
    body = ('<h1>Agent traces</h1><div class="controls"><input id="search" type="search" '
            'aria-label="Find a task or harness" placeholder="Find a task or harness"></div>'
            '<table><thead><tr><th>Task</th><th>Harness</th><th>Agent cycles</th><th>Files</th></tr></thead><tbody>')
    for run in runs:
        harness = run["harness"]
        label = harness.get("name", run["id"]) if isinstance(harness, dict) else harness
        model = harness.get("model", harness.get("requested_model", "")) if isinstance(harness, dict) else ""
        body += (f'<tr data-searchable><td><a href="{esc(run["id"])}.html">{esc(run.get("task_title", run["task"]))}</a></td>'
                 f'<td>{esc(label)}<br><span class="label">{esc(model)}</span></td>'
                 f'<td>{len(run["messages"])}</td><td><a href="{esc(run["id"])}.html">HTML</a> · '
                 f'<a href="{esc(run["id"])}.json" download>JSON</a></td></tr>')
    body += '</tbody></table>'
    if references:
        body += '<h2>References</h2><ul>'
        for reference in references:
            body += f'<li><a href="{esc(reference["doi"])}" rel="noreferrer">{esc(reference["title"])}</a></li>'
        body += '</ul>'
    return page("Agent traces", body)


def read_references(path: Path, sanitizer: Sanitizer) -> list[dict]:
    source = json.loads(path.read_text())
    records = source.values() if isinstance(source, dict) else source
    references = []
    for row in records:
        doi = row["doi"]
        if not doi.startswith("https://doi.org/"):
            doi = "https://doi.org/" + doi
        if not re.fullmatch(r"https://doi\.org/10\.\d{4,9}/[^\s]+", doi):
            raise ExportError("Bibliography contains an invalid DOI URL")
        title = row["title"]
        if isinstance(title, list):
            title = " ".join(title)
        title = re.sub(r"</?(?:scp|sub|sup|i|b)>", "", title)
        title = " ".join(html.unescape(title).split())
        references.append({"title": title, "doi": doi})
    return sanitizer.clean(references)


def export(source_map: Path, output: Path) -> dict:
    mapping = json.loads(source_map.read_text())
    sanitizer = Sanitizer(mapping.get("replacements"), mapping.get("redactions"))
    runs = [export_run(spec, source_map.parent, sanitizer) for spec in mapping["runs"]]
    if len({r["id"] for r in runs}) != len(runs):
        raise ExportError("Duplicate run id")
    references = read_references(_path(source_map.parent, mapping["bibliography_file"]), sanitizer) if mapping.get("bibliography_file") else []
    # Validate all selected content before creating any publishable output.
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "runs": [], "redactions": dict(sanitizer.counts)}
    for run in runs:
        data = json_text(run)
        (output / (run["id"] + ".json")).write_text(data)
        (output / (run["id"] + ".html")).write_text(render_run(run))
        manifest["runs"].append({"id": run["id"], "task": run["task"], "harness": run["harness"],
                                 "json": run["id"] + ".json", "html": run["id"] + ".html",
                                 "sha256": digest(data.encode()), "cycles": len(run["messages"]),
                                 "messages": sum(len(x["messages"]) for x in run["messages"])})
    (output / "index.html").write_text(render_index(runs, references))
    if references:
        (output / "references.json").write_text(json_text(references))
        manifest["references"] = "references.json"
    (output / "manifest.json").write_text(json_text(manifest))
    return manifest


@click.command()
@click.option("--source-map", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True,
              help="Private JSON selecting the native trace, code and review sources.")
@click.option("--output", type=click.Path(file_okay=False, path_type=Path), required=True)
def main(source_map: Path, output: Path):
    """Build portable scientist JSON and self-contained HTML from saved records."""
    try:
        manifest = export(source_map, output)
    except (ExportError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps({"runs": len(manifest["runs"]), "output": str(output),
                           "messages": sum(x["messages"] for x in manifest["runs"])}))


if __name__ == "__main__":
    main()
