/**
 * Command bar — top-center chrome: wordmark, omni-search, flow-mode
 * toggle, Follow-the-Load, preset tab strip, demo caption strip.
 */

import type { AppApi, Suggestion, ViewPreset } from '../app/api';

const PRESETS: { id: ViewPreset; label: string }[] = [
  { id: 'world', label: 'WORLD' },
  { id: 'freight', label: 'FREIGHT' },
  { id: 'trade', label: 'TRADE' },
  { id: 'commodities', label: 'COMMODITIES' },
  { id: 'network', label: 'NETWORK' },
  { id: 'exceptions', label: 'EXCEPTIONS' },
];

export function createCommandBar(api: AppApi): { el: HTMLElement } {
  const el = document.createElement('div');
  el.className = 'pe-commandbar';

  // ---------------------------------------------------------------- row
  const row = document.createElement('div');
  row.className = 'pe-cb-row';

  const mark = document.createElement('div');
  mark.className = 'pe-cb-mark';
  const glyph = document.createElement('span');
  glyph.className = 'pe-cb-glyph';
  mark.title = 'Geospatial State Visualization';
  mark.append(glyph, document.createTextNode('GEOSPATIAL'));

  const searchWrap = document.createElement('div');
  searchWrap.className = 'pe-cb-searchwrap';
  const input = document.createElement('input');
  input.className = 'pe-cb-search';
  input.type = 'text';
  input.spellcheck = false;
  input.autocomplete = 'off';
  input.placeholder = 'Search geographic entities…';
  const dropdown = document.createElement('div');
  dropdown.className = 'pe-cb-suggest';
  dropdown.hidden = true;
  searchWrap.append(input, dropdown);

  const flowChip = document.createElement('button');
  flowChip.className = 'pe-chip pe-cb-flow';
  flowChip.type = 'button';
  flowChip.textContent = 'FLOW MODE';

  const followBtn = document.createElement('button');
  followBtn.className = 'pe-cb-follow';
  followBtn.type = 'button';
  followBtn.textContent = 'FOLLOW THE LOAD';

  row.append(mark, searchWrap, flowChip, followBtn);

  // ---------------------------------------------------------------- tabs
  const tabs = document.createElement('div');
  tabs.className = 'pe-cb-tabs';
  const tabButtons = new Map<ViewPreset, HTMLButtonElement>();
  for (const p of PRESETS) {
    const b = document.createElement('button');
    b.className = 'pe-cb-tab';
    b.type = 'button';
    b.textContent = p.label;
    b.addEventListener('click', () => api.setPreset(p.id));
    tabButtons.set(p.id, b);
    tabs.appendChild(b);
  }

  const syncTabs = (active: ViewPreset): void => {
    for (const [id, b] of tabButtons) b.classList.toggle('active', id === active);
  };
  syncTabs(api.getPreset());
  api.events.on('preset', ({ preset }) => syncTabs(preset));

  // ---------------------------------------------------------------- demo strip
  const demoStrip = document.createElement('div');
  demoStrip.className = 'pe-cb-demo';
  const demoTitle = document.createElement('div');
  demoTitle.className = 'pe-cb-demo-title';
  const demoStep = document.createElement('div');
  demoStep.className = 'pe-cb-demo-step';
  demoStrip.append(demoTitle, demoStep);

  // ---------------------------------------------------------------- result line
  const result = document.createElement('div');
  result.className = 'pe-cb-result';
  result.hidden = true;
  let resultTimer = 0;
  const showResult = (message: string, ok: boolean): void => {
    result.textContent = message;
    result.classList.toggle('err', !ok);
    result.hidden = false;
    window.clearTimeout(resultTimer);
    resultTimer = window.setTimeout(() => {
      result.hidden = true;
    }, 3200);
  };

  el.append(row, tabs, demoStrip, result);

  // ---------------------------------------------------------------- search
  let suggestions: Suggestion[] = [];
  let activeIx = -1;

  const closeDropdown = (): void => {
    dropdown.hidden = true;
    dropdown.replaceChildren();
    suggestions = [];
    activeIx = -1;
  };

  const highlight = (ix: number): void => {
    activeIx = ix;
    const rows = dropdown.children;
    for (let i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('active', i === ix);
    }
  };

  const runCommand = (text: string): void => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const res = api.runCommand(trimmed);
    showResult(res.message, res.ok);
  };

  const chooseSuggestion = (s: Suggestion): void => {
    input.value = s.text;
    closeDropdown();
    runCommand(s.text);
  };

  const renderDropdown = (): void => {
    dropdown.replaceChildren();
    if (!suggestions.length) {
      dropdown.hidden = true;
      return;
    }
    suggestions.forEach((s, ix) => {
      const rowEl = document.createElement('div');
      rowEl.className = 'pe-cb-sug-row';
      const label = document.createElement('span');
      label.className = 'pe-cb-sug-label';
      label.textContent = s.label;
      rowEl.appendChild(label);
      if (s.hint) {
        const hint = document.createElement('span');
        hint.className = 'pe-cb-sug-hint';
        hint.textContent = s.hint;
        rowEl.appendChild(hint);
      }
      rowEl.addEventListener('mouseenter', () => highlight(ix));
      rowEl.addEventListener('mousedown', (e) => {
        // mousedown (not click) so we act before the input blurs
        e.preventDefault();
        chooseSuggestion(s);
      });
      dropdown.appendChild(rowEl);
    });
    dropdown.hidden = false;
    highlight(activeIx);
  };

  input.addEventListener('input', () => {
    const v = input.value.trim();
    if (!v) {
      closeDropdown();
      return;
    }
    suggestions = api.suggest(v);
    activeIx = -1;
    renderDropdown();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' && suggestions.length) {
      e.preventDefault();
      highlight((activeIx + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp' && suggestions.length) {
      e.preventDefault();
      highlight(activeIx < 0 ? suggestions.length - 1 : (activeIx - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIx >= 0 && activeIx < suggestions.length) {
        chooseSuggestion(suggestions[activeIx]);
      } else {
        closeDropdown();
        runCommand(input.value);
      }
    } else if (e.key === 'Escape') {
      if (!dropdown.hidden) closeDropdown();
      else input.blur();
    }
  });

  input.addEventListener('blur', () => {
    // let a suggestion mousedown land first
    window.setTimeout(closeDropdown, 120);
  });

  // '/' anywhere (outside editable elements) focuses search
  window.addEventListener('keydown', (e) => {
    if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target as HTMLElement | null;
    if (
      t &&
      (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
    ) {
      return;
    }
    e.preventDefault();
    input.focus();
    input.select();
  });

  // ---------------------------------------------------------------- flow mode
  const syncFlow = (enabled: boolean): void => {
    flowChip.classList.toggle('on', enabled);
  };
  syncFlow(api.getFlowMode());
  flowChip.addEventListener('click', () => api.setFlowMode(!api.getFlowMode()));
  api.events.on('flowMode', ({ enabled }) => syncFlow(enabled));

  // ---------------------------------------------------------------- demo
  let demoActive = api.isDemoActive();

  const syncDemoButton = (): void => {
    followBtn.textContent = demoActive ? 'EXIT DEMO' : 'FOLLOW THE LOAD';
    followBtn.classList.toggle('exit', demoActive);
    el.classList.toggle('demo', demoActive);
  };
  syncDemoButton();

  followBtn.addEventListener('click', () => {
    if (demoActive) api.stopFollowTheLoad();
    else api.startFollowTheLoad();
  });

  api.events.on('demo', (d) => {
    demoActive = d.active;
    syncDemoButton();
    if (d.active) {
      demoTitle.textContent = d.title ?? '';
      demoTitle.hidden = !d.title;
      const step =
        d.step !== undefined && d.totalSteps !== undefined
          ? `STEP ${d.step}/${d.totalSteps}`
          : '';
      const caption = d.caption ?? '';
      demoStep.textContent =
        step && caption ? `${step} · ${caption}` : step || caption;
    } else {
      demoTitle.textContent = '';
      demoStep.textContent = '';
    }
  });

  return { el };
}
