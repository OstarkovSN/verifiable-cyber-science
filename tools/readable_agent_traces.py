"""Export recorded Claude/Codex agent activity to self-contained HTML reports."""
from pathlib import Path
import hashlib, html, json, zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/readable-agent-traces'; OUT.mkdir(exist_ok=True,parents=True)
def esc(x): return html.escape(str(x))
def block(title,body,opened=False):
 return '<details'+(' open' if opened else '')+'><summary>'+esc(title)+'</summary><pre>'+esc(body)+'</pre></details>'
def page(title,body):
 return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+esc(title)+'</title><style>body{max-width:1050px;margin:30px auto;padding:0 20px;font:17px/1.5 system-ui;color:#17232e}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.45 monospace;background:#f3f5f7;padding:15px}summary{cursor:pointer;font-weight:600;padding:10px}details{border:1px solid #d4dce3;margin:12px 0}a{color:#164ea0}table{border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}</style><body><h1>'+esc(title)+'</h1>'+body+'</body></html>'
rows=[]; manifest=[]
for src in sorted((ROOT/'artifacts/vas-agent-runs').glob('*/*/transcript.jsonl')):
 task,run=src.parent.parent.name,src.parent.name; meta=json.loads((src.parent/'manifest.json').read_text()); items=[];n=0
 for raw in src.read_text().splitlines():
  event=json.loads(raw)
  if event.get('type')=='item.completed':
   it=event['item']; typ=it.get('type')
   if typ=='agent_message': items.append(block('Agent message',it.get('text',''),True));n+=1
   elif typ=='command_execution':items.append(block('Command · exit '+str(it.get('exit_code')),it.get('command','')+'\n\nOUTPUT\n'+it.get('aggregated_output','')));n+=1
   elif typ in ('file_change','mcp_tool_call','web_search'):items.append(block(typ,json.dumps(it,ensure_ascii=False,indent=2)));n+=1
  elif event.get('type') in ('assistant','user'):
   content=event.get('message',{}).get('content',[])
   if isinstance(content,str):items.append(block(event['type'],content));n+=1;continue
   for b in content:
    typ=b.get('type')
    if typ=='text':items.append(block('Agent message' if event['type']=='assistant' else 'Input',b['text'],True));n+=1
    elif typ=='tool_use':items.append(block('Tool call: '+b.get('name',''),json.dumps(b.get('input',{}),ensure_ascii=False,indent=2)));n+=1
    elif typ=='tool_result':items.append(block('Tool result'+(' · error' if b.get('is_error') else ''),b.get('content','')));n+=1
 title=task+' / '+run; name=task+'--'+run+'.html'; outcome=meta.get('outcome',{})
 body='<p><a href="index.html">All runs</a></p><p>Verbatim recorded messages and tool activity; system metadata and private reasoning blocks are omitted.</p>'
 body+=block('Run metadata',json.dumps(meta,indent=2,ensure_ascii=False))
 for f,label in [('prompt.md','Prompt'),('final.md','Final report')]:
  p=src.parent/f
  if p.exists():body+=block(label,p.read_text(),f=='final.md')
 body+='<h2>Activity in recorded order</h2>'+''.join(items)
 (OUT/name).write_text(page(title,body));rows.append((task,run,name,n))
 manifest.append({'source':str(src.relative_to(ROOT)),'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'report':name,'activity_entries':n})
body='<p>Prompts, final reports, and tool activity from '+str(len(rows))+' saved runs. Open a run and expand any command to see its output. Failed attempts remain in the activity.</p><table><tr><th>Problem</th><th>Run</th><th>Activity entries</th></tr>'
for task,run,name,n in rows: body+='<tr><td>'+esc(task)+'</td><td><a href="'+name+'">'+esc(run)+'</a></td><td>'+str(n)+'</td></tr>'
body+='</table><h2>Latest coffee attempt</h2><p>The later coffee demonstration uses synthetic readings. Its conditional target formula passed Lean; it is separate from the earlier recorded CLI runs above.</p>'
for f in ['report.txt','request.json','synthetic.json','synthetic-prediction.json','CoolingNarrow.lean','lean-narrow.log']:
 p=ROOT/'artifacts/ot2068/scientist'/f
 if p.exists():body+=block(('Initial report (before the successful proof check)' if f=='report.txt' else f),p.read_text())
(OUT/'index.html').write_text(page('Research agent traces',body));(OUT/'sources.json').write_text(json.dumps(manifest,indent=2))
combined='<p>Complete readable export of the saved agent runs. Expand a run, then any command or result.</p>'
for task,run,name,n in rows:
 content=(OUT/name).read_text().split('<body>',1)[1].rsplit('</body>',1)[0]
 combined+='<details><summary>'+esc(task+' / '+run)+'</summary>'+content+'</details>'
(OUT/'all-runs.html').write_text(page('All research agent traces',combined))
with zipfile.ZipFile(OUT.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(OUT.glob('*')):z.write(p,'agent-traces/'+p.name)
print(json.dumps({'runs':len(rows),'entries':sum(x[3] for x in rows),'zip':str(OUT.with_suffix('.zip')),'bytes':OUT.with_suffix('.zip').stat().st_size}))
