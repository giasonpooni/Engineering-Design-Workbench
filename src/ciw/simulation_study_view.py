"""Read-only, observer-scoped study display. No engine, provider, or network access."""
from __future__ import annotations
from html import escape
import base64
from hashlib import sha256
from pathlib import Path

from .simulation_study import _inspect_details
from .control_contracts import save_new


def html(directory: Path, observer_id: str) -> str:
    _, plan, report, _ = _inspect_details(directory)
    matches = [p for p in plan['observers'] if p['observer_id'] == observer_id]
    if not matches:
        raise ValueError('Select a declared observer')
    observer = matches[0]
    sections = []
    # Do not include privileged comparisons or the source checkpoint in this view.
    for branch in report['branches']:
        view = next(v for v in branch['observers'] if v['observer']['observer_id'] == observer_id)
        plots=[]
        for quantity, stream in view['streams'].items():
            title=escape(quantity)
            if not stream:
                plots.append(f'<h3>{title}</h3><p>Unavailable at this tick: no delivered observations.</p>')
                continue
            times=[o['clock']['time_s'] for o in stream]
            values=[o['value'] for o in stream]
            low,high=min(values),max(values)
            span=max(high-low,1e-12);duration=max(max(times)-min(times),1e-12)
            points=''.join(f'<circle cx="{45+700*(t-min(times))/duration:.3f}" cy="{195-155*(v-low)/span:.3f}" r="3"><title>{t:.9g} s: {v:.12g} {escape(stream[0]["unit"])}</title></circle>' for t,v in zip(times,values))
            plots.append(f'<h3>{title} ({escape(stream[0]["unit"])})</h3><svg viewBox="0 0 800 235" role="img" aria-label="{title}: discrete delivered samples">{points}<text x="10" y="25">{high:.9g}</text><text x="10" y="210">{low:.9g}</text><text x="45" y="230">{min(times):.6g} s</text><text x="700" y="230">{max(times):.6g} s</text></svg>')
        headers=''.join('<th>'+escape(q)+'</th>' for q in observer['quantities'])
        rows=[]
        for i,tick in enumerate(view['sample_ticks']):
            values=''.join(f'<td>{view["streams"][q][i]["value"]:.12g}</td>' for q in observer['quantities'])
            rows.append(f'<tr><td>{tick}</td><td>{view["available_ticks"][i]}</td>{values}</tr>')
        sections.append(f'<section><h2>{escape(branch["name"])}</h2><p>As of tick {view["as_of_tick"]}; {len(view["sample_ticks"])} delivered samples. Independent owner: <code>{escape(branch["owner_id"])}</code></p>'+''.join(plots)+f'<details><summary>Retained values and delivery ticks</summary><div class="scroll"><table><thead><tr><th>Sample tick</th><th>Available tick</th>{headers}</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></details></section>')
    css='body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5;background:#f6f8fa;color:#18283a}section{background:white;padding:1.2rem;margin:1.5rem 0;border:1px solid #cbd3db;border-radius:8px}svg{width:100%;height:auto;max-height:300px;border-bottom:1px solid #cbd3db}circle{fill:#1c6576}text{font:12px system-ui}code{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%}th,td{padding:.5rem;text-align:left;border-bottom:1px solid #ddd}.scroll{overflow:auto}'
    h=base64.b64encode(sha256(css.encode()).digest()).decode()
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'sha256-{h}'; base-uri 'none'; form-action 'none'"><title>NET stateful study</title><style>{css}</style><h1>Stateful simulation study</h1><p>Observer: <strong>{escape(observer_id)}</strong> · Every {observer['every_ticks']} ticks · Delivery delay {observer['delay_ticks']} ticks</p><p><code>{escape(report['study_id'])}</code></p><p>Discrete synthetic observations; no interpolation, uncertainty estimate or physical validation. Vertical ranges are independent per plot; use the retained values for comparison. A branch difference is not a failed execution.</p>'''+''.join(sections)+'</html>'


def write(directory: Path, observer_id: str, output: Path) -> dict:
    raw=html(directory,observer_id).encode('utf-8')
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Create-only, no output mutation of the source study.
    with output.open('xb') as stream:
        stream.write(raw)
    return {'status':'retained_observer_view_written','observer_id':observer_id,
            'sha256':'sha256:'+sha256(raw).hexdigest(),'provider_execution':'not_performed'}
