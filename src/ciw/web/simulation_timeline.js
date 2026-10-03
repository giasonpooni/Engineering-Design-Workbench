'use strict';
(() => {
  const data = JSON.parse(document.getElementById('timeline-data').textContent);
  const t = data.timeline;
  const byId = new Map(t.entries.map(e => [e.execution_id, e]));
  const el = id => document.getElementById(id);
  const text = (id, value) => { el(id).textContent = String(value); };
  const short = value => value ? value.slice(0, 19) + '…' : 'Not recorded';
  const clock = value => value ? `${value.time_s} s · ${value.id}` : 'Not observed by this operation';
  const fmt = value => value === null ? 'Missing' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const observerId = e => e.observer ? e.observer.observer_id : '';
  let shown = t.entries;
  let selected = (t.entries.find(e => e.image && e.image.bytes_checked && e.image.availability === 'present') || t.entries.find(e => e.kind === 'observation') || t.entries[0] || {}).execution_id;
  function options(id, values) {
    [...new Set(values.filter(Boolean))].sort().forEach(value => {
      const option = document.createElement('option'); option.value = value;
      option.textContent = id === 'instance' ? short(value) : value; el(id).append(option);
    });
  }
  text('executions', t.summary.unique_executions); text('instances', t.summary.instance_count);
  text('images', t.summary.checked_images); text('refusals', t.summary.kinds.refusal || 0);
  text('dedup', `${t.sources.length} selected workspace snapshots · ${t.summary.deduplicated_execution_copies} shared execution copies deduplicated · ${t.summary.unique_results} unique retained results. No new execution was created by inspection.`);
  text('source-ref', `Index content reference: ${t.record_digest}`);
  if (t.history_gaps.length || t.summary.legacy_results_not_indexed || t.summary.wall_clock_reversed_links) {
    el('gaps').hidden = false;
    text('gaps', `${t.history_gaps.length} missing history links; ${t.summary.legacy_results_not_indexed} legacy results outside this operation index; ${t.summary.wall_clock_reversed_links} links run opposite host timestamp order. Unknown links are not repaired or inferred.`);
  }
  options('kind', t.entries.map(e => e.kind)); options('instance', t.entries.map(e => e.instance_id || e.requested_instance_id)); options('observer', t.entries.map(observerId));
  function fact(label, value) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = label; dd.textContent = value; el('facts').append(dt, dd);
  }
  function select(id, resetFilters = false) {
    if (!byId.has(id)) return;
    if (resetFilters) ['kind','instance','observer','search'].forEach(k => { el(k).value = ''; });
    selected = id; update();
  }
  function detail() {
    const e = byId.get(selected);
    ['facts','relations','samples'].forEach(id => el(id).replaceChildren());
    el('image-panel').hidden = true; el('capture-image').removeAttribute('src'); el('sample-panel').hidden = true;
    text('observation-note','');
    if (!e) { text('selected-kind','No selection'); text('selected-title','No occurrence selected'); text('selected-execution',''); text('record-json',''); el('previous').disabled = el('next').disabled = true; return; }
    text('selected-kind', e.kind); text('selected-title', e.action); text('selected-execution', e.execution_id);
    fact('Status', e.status); fact('Host timestamp', e.created_at + ' (record creation, not simulation time)');
    fact('Instance', e.instance_id || (e.requested_instance_id ? e.requested_instance_id + ' (attempted only)' : 'Not assigned'));
    if (e.revision !== null) fact('Control / state revision', `${e.revision} / ${e.state_revision}`);
    if (e.owner_id) fact('State owner', e.owner_id);
    if (e.world_after) { fact('World before', clock(e.world_before)); fact('World after', clock(e.world_after)); }
    if (e.observer) fact('Observer', `${e.observer.observer_id} · ${e.observer.kind}`);
    if (e.available_at) fact('Available at', clock(e.available_at));
    if (e.result_id) fact('Result identity', e.result_id);
    if (e.checkpoint_ref) fact('Checkpoint reference', e.checkpoint_ref);
    if (e.refusal) { fact('Refusal reason', `${e.refusal.code}: ${e.refusal.message}`); text('observation-note','This is an attempted operation. No successful result or post-failure world state was retained.'); }
    t.links.filter(link => link.target === selected || link.source === selected).forEach(link => {
      const incoming = link.target === selected, id = incoming ? link.source : link.target;
      const button = document.createElement('button'); button.type = 'button';
      const labels = {instance_predecessor: incoming ? "Previous in instance" : "Next in instance", restored_from: incoming ? "Source checkpoint" : "Restored branch", captured_from: incoming ? "Source observation" : "Derived capture"};
      button.textContent = `${labels[link.relation]} · ${byId.get(id).action}`;
      button.dataset.executionId = id; button.addEventListener('click', () => select(id, true)); el('relations').append(button);
    });
    t.history_gaps.filter(g => g.execution_id === selected).forEach(g => { const p = document.createElement('p'); p.className = 'unavailable'; p.textContent = `Missing link: ${g.reason}. No predecessor is invented.`; el('relations').append(p); });
    if (e.kind === 'observation') {
      text('observation-note', e.samples.length ? `${e.samples.length} observer-conditioned samples. Their acquisition timestamps and original units/provenance are preserved.` : 'No samples were available to this observer. Absence is not a zero measurement.');
      if (e.samples.length) {
        el('sample-panel').hidden = false;
        for (const s of e.samples) {
          const row = document.createElement('tr');
          [s.clock.time_s, s.identity.entity_id, s.quantity, fmt(s.value), s.unit].forEach(value => { const cell = document.createElement('td'); cell.textContent = String(value); row.append(cell); });
          el('samples').append(row);
        }
      }
    }
    if (e.image) {
      fact('Image sample time', e.image.sample_time_s === null ? 'No available sample' : `${e.image.sample_time_s} s`);
      fact('Image availability', e.image.availability); fact('Camera', e.image.camera);
      fact('Image bytes', e.image.bytes_checked ? 'Checked against artifact and source' : 'Not supplied; metadata only');
      if (e.image.bytes_checked) {
        el('image-panel').hidden = false; el('capture-image').src = data.images[e.image.sha256];
        text('image-caption', `${e.image.camera} · ${e.image.availability} · sample ${e.image.sample_time_s === null ? 'unavailable' : e.image.sample_time_s + ' s'} · delivered ${e.available_at.time_s} s. Derived visualization, not live camera evidence.`);
      } else text('observation-note', 'PNG bytes were not included. A valid capture record is not a checked image file.');
    }
    text('record-json', JSON.stringify(e, null, 2));
    const index = shown.findIndex(x => x.execution_id === selected);
    el('previous').disabled = index <= 0; el('next').disabled = index < 0 || index >= shown.length - 1;
  }
  function update() {
    const q = el('search').value.toLowerCase();
    shown = t.entries.filter(e => (!el('kind').value || el('kind').value === e.kind) && (!el('instance').value || el('instance').value === (e.instance_id || e.requested_instance_id)) && (!el('observer').value || el('observer').value === observerId(e)) && (!q || JSON.stringify(e).toLowerCase().includes(q)));
    if (!shown.some(e => e.execution_id === selected)) selected = shown.length ? shown[0].execution_id : null;
    el('event-list').replaceChildren(); text('visible-count', `${shown.length} / ${t.entries.length}`); el('empty').hidden = shown.length !== 0;
    shown.forEach(e => {
      const item = document.createElement('div'); item.setAttribute('role','listitem');
      const button = document.createElement('button'); button.type = 'button'; button.className = 'event ' + e.kind;
      button.dataset.executionId = e.execution_id; button.setAttribute('aria-pressed', String(e.execution_id === selected));
      const line = document.createElement('strong'), title = document.createElement('span'), tag = document.createElement('span');
      title.textContent = e.action; tag.textContent = e.kind; tag.className = 'tag'; line.append(title, tag);
      const sub = document.createElement('small');
      sub.textContent = e.world_after ? `World ${e.world_after.time_s} s · control revision ${e.revision}` : e.image ? `Sample ${e.image.sample_time_s === null ? 'unavailable' : e.image.sample_time_s + ' s'} · ${e.image.camera}` : 'No observed world time';
      const identity = document.createElement('small'); identity.textContent = short(e.instance_id || e.requested_instance_id) + (e.observer ? ` · ${observerId(e)}` : '');
      button.append(line, sub, identity); button.addEventListener('click', () => select(e.execution_id)); item.append(button); el('event-list').append(item);
    });
    detail();
    const list = el("event-list"), active = list.querySelector('[aria-pressed="true"]');
    if (active) list.scrollTop += active.getBoundingClientRect().top - list.getBoundingClientRect().top - list.clientHeight / 2 + active.offsetHeight / 2;
  }
  ['kind','instance','observer'].forEach(id => el(id).addEventListener('change', update)); el('search').addEventListener('input', update);
  el('reset').addEventListener('click', () => { ['kind','instance','observer','search'].forEach(id => { el(id).value = ''; }); update(); });
  for (const [name, offset] of [['previous',-1],['next',1]]) el(name).addEventListener('click', () => { const index = shown.findIndex(e => e.execution_id === selected); const next = shown[index + offset]; if (next) select(next.execution_id); });
  if (!t.analyses.length) { const p = document.createElement('p'); p.className = 'note'; p.textContent = 'No campaign or replay report was selected. No verdict is inferred from the event history.'; el('analysis-list').append(p); }
  for (const a of t.analyses) {
    const card = document.createElement('article'); card.className = 'analysis';
    const title = document.createElement('strong'); title.textContent = `${a.kind.toUpperCase()} · ${a.summary.status}`;
    const ref = document.createElement('p'); ref.className = 'mono'; ref.textContent = a.record_ref;
    const body = document.createElement('p'); body.textContent = a.kind === 'replay' ? `${a.summary.checked_commands} commands checked; ${a.summary.mismatch_indices.length} mismatches. ${a.claim_scope}` : a.outcomes.map(o => `${o.variant_id}: ${o.outcome.status}`).join(' · ');
    const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Open source checkpoint'; button.addEventListener('click', () => select(a.execution_ids[0], true));
    card.append(title, ref, body, button); el('analysis-list').append(card);
  }
  update();
})();
