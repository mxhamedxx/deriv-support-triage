"""Simple read-only browser dashboard created from POST-review queue data.
The required correction checkpoint stays in the terminal.
No Flask, server, database or external packages necessary.
"""
from collections import Counter
from html import escape
from pathlib import Path

BASE = Path(__file__).resolve().parent


def build_dashboard(queue, normalized, config):
    source = {t['ticket_id']: t for t in normalized}
    categories = Counter(q['final_category'] for q in queue)
    priorities = Counter(q['final_priority'] for q in queue)
    queues = Counter(q['final_route_to'] for q in queue)
    e = lambda value: escape(str(value), quote=True)

    category_options = ''.join(f'<option value="{e(c)}">{e(c)}</option>' for c in config['allowed_categories'])
    priority_options = ''.join(f'<option value="{e(p)}">{e(p)}</option>' for p in config['allowed_priorities'])
    queue_options = ''.join(f'<option value="{e(q)}">{e(q)}</option>' for q in dict.fromkeys(config['routing_rules'].values()))

    rows = []
    for item in queue:
        ticket = source[item['ticket_id']]
        rows.append(f'''<article class="ticket" data-category="{e(item['final_category'])}" data-priority="{e(item['final_priority'])}" data-route="{e(item['final_route_to'])}">
  <div class="ticket-head"><span class="id">{e(item['ticket_id'])}</span><strong>{e(ticket['subject'])}</strong><span class="pill">{e(item['final_priority'])}</span></div>
  <p class="message">{e(ticket['message'])}</p>
  <div class="meta"><span>Category: <b>{e(item['final_category'])}</b></span><span>Route: <b>{e(item['final_route_to'])}</b></span>{'<span class="corrected">Human corrected</span>' if item['was_overridden'] else ''}</div>
  <div class="reply"><b>Suggested reply</b><p>{e(item['suggested_reply'])}</p></div>
</article>''')

    metrics = ''.join(
        f'<div class="metric"><div class="number">{e(value)}</div><div>{e(label)}</div></div>'
        for label, value in [
            ('Total tickets', len(queue)),
            ('Urgent', priorities.get('urgent', 0)),
            ('Human corrected', sum(q['was_overridden'] for q in queue)),
            ('Destinations', len([v for v in queues.values() if v]))
        ]
    )
    route_breakdown = ''.join(f'<li>{e(k)}: <strong>{v}</strong></li>' for k, v in queues.items())
    category_breakdown = ''.join(f'<li>{e(k)}: <strong>{v}</strong></li>' for k, v in categories.items())

    page = '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Support Triage | Agent Queue</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f6f9;color:#16243a;font-family:system-ui,-apple-system,Segoe UI,Arial,sans-serif;line-height:1.5}
header{background:#101d35;color:white;padding:28px max(20px,calc((100% - 1060px)/2))}header h1{margin:0;font-size:25px}header p{color:#c7d4ea;margin:6px 0 0}
main{max-width:1060px;margin:auto;padding:25px 18px 60px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric,.panel,.ticket{background:white;border:1px solid #e4e9f1;border-radius:12px;padding:16px;box-shadow:0 2px 5px #14233d0b}.number{font-weight:750;font-size:28px;color:#254fa1}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:18px;margin-top:22px}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 16px}select,input{border:1px solid #ced7e4;border-radius:8px;background:white;padding:10px;min-width:145px}input{flex:1;min-width:190px}.ticket{margin-bottom:12px}.ticket-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.id{font-size:12px;font-weight:700;color:#536680}.pill{margin-left:auto;background:#e9effd;color:#284b8c;border-radius:20px;padding:4px 9px;font-size:12px}.message{color:#4d5d71}.meta{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:#5b6b7c}.meta b{color:#273e61}.corrected{color:#9b5b14;font-weight:700}.reply{background:#eef4ff;border-radius:8px;padding:11px 13px;margin-top:13px}.reply p{margin:5px 0 0;font-size:14px}.panel h3{margin:0 0 8px;font-size:15px}.panel ul{padding-left:18px;word-break:break-word}li{font-size:13px;margin:6px 0}.hint{font-size:12px;color:#62718a}.empty{display:none;padding:20px;text-align:center}
@media(max-width:740px){.metrics{grid-template-columns:repeat(2,1fr)}.layout{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Support Triage — Agent Queue</h1><p>Post-review classifications and suggested replies</p></header>
<main><section class="metrics">__METRICS__</section>
<div class="layout"><section><h2>Assigned Tickets</h2><div class="controls">
<input id="search" placeholder="Search ticket, subject or reply" aria-label="Search tickets">
<select id="category" aria-label="Category"><option value="">All categories</option>__CATEGORY_OPTIONS__</select>
<select id="priority" aria-label="Priority"><option value="">All priorities</option>__PRIORITY_OPTIONS__</select>
<select id="route" aria-label="Queue"><option value="">All queues</option>__QUEUE_OPTIONS__</select>
</div><div id="tickets">__TICKETS__</div><p class="empty" id="empty">No tickets match these filters.</p></section>
<aside class="panel"><h3>Queue destinations</h3><ul>__ROUTES__</ul><h3>Final categories</h3><ul>__CATEGORIES__</ul>
<p class="hint">This is a read-only dashboard. Ticket corrections are performed in the mandatory terminal review checkpoint before generating this page.</p></aside></div></main>
<script>
const items=Array.from(document.querySelectorAll('.ticket'));
const inputs=['search','category','priority','route'].map(id=>document.getElementById(id));
function filterTickets(){const [search,category,priority,route]=inputs.map(x=>x.value.toLowerCase());let count=0;
for(const t of items){const show=t.textContent.toLowerCase().includes(search)&&(!category||t.dataset.category===category)&&(!priority||t.dataset.priority===priority)&&(!route||t.dataset.route===route);t.style.display=show?'':'none';if(show)count++}
document.getElementById('empty').style.display=count?'none':'block';}
inputs.forEach(i=>i.addEventListener('input',filterTickets));
</script></body></html>'''
    replacements = {
        '__METRICS__': metrics, '__CATEGORY_OPTIONS__': category_options,
        '__PRIORITY_OPTIONS__': priority_options, '__QUEUE_OPTIONS__': queue_options,
        '__TICKETS__': '\n'.join(rows), '__ROUTES__': route_breakdown,
        '__CATEGORIES__': category_breakdown,
    }
    for token, value in replacements.items():
        page = page.replace(token, value)
    (BASE / 'dashboard.html').write_text(page, encoding='utf-8')
