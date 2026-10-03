/**
 * Layer panel — left rail listing render layers grouped by domain,
 * with per-layer visibility toggles and mode-color swatches.
 */

import type { AppApi, LayerDef, LayerId } from '../app/api';

const GROUP_ORDER: LayerDef['group'][] = [
  'WORLD',
  'TRANSPORT',
  'INFRASTRUCTURE',
  'ECONOMY',
  'INTELLIGENCE',
];

const MODE_SWATCH: Partial<Record<LayerId, string>> = {
  'transport.road': 'var(--mode-road)',
  'transport.rail': 'var(--mode-rail)',
  'transport.maritime': 'var(--mode-maritime)',
  'transport.air': 'var(--mode-air)',
};

export function createLayerPanel(api: AppApi): { el: HTMLElement } {
  const el = document.createElement('div');
  el.className = 'pe-layerpanel';

  let panelCollapsed = false;
  const closedGroups = new Set<string>();

  // ---------------------------------------------------------------- header
  const head = document.createElement('div');
  head.className = 'pe-lp-head';
  const title = document.createElement('span');
  title.className = 'pe-lp-title';
  title.textContent = 'LAYERS';
  const chevron = document.createElement('button');
  chevron.className = 'pe-lp-chevron';
  chevron.type = 'button';
  chevron.textContent = '‹';
  chevron.title = 'Collapse panel';
  head.append(title, chevron);

  const body = document.createElement('div');
  body.className = 'pe-lp-body';

  // slim vertical tab shown while collapsed
  const tab = document.createElement('div');
  tab.className = 'pe-lp-tab';
  tab.textContent = 'LAYERS';

  el.append(head, body, tab);

  const setCollapsed = (collapsed: boolean): void => {
    panelCollapsed = collapsed;
    el.classList.toggle('collapsed', collapsed);
  };

  chevron.addEventListener('click', (e) => {
    e.stopPropagation();
    setCollapsed(true);
  });
  el.addEventListener('click', () => {
    if (panelCollapsed) setCollapsed(false);
  });

  // ---------------------------------------------------------------- rows
  const render = (layers: LayerDef[]): void => {
    body.replaceChildren();
    for (const group of GROUP_ORDER) {
      const inGroup = layers.filter((l) => l.group === group);
      if (!inGroup.length) continue;

      const section = document.createElement('div');
      section.className = 'pe-lp-group';
      if (closedGroups.has(group)) section.classList.add('closed');

      const groupHead = document.createElement('button');
      groupHead.className = 'pe-lp-group-head';
      groupHead.type = 'button';
      const groupLabel = document.createElement('span');
      groupLabel.textContent = group;
      const groupChevron = document.createElement('span');
      groupChevron.textContent = closedGroups.has(group) ? '+' : '−';
      groupHead.append(groupLabel, groupChevron);
      groupHead.addEventListener('click', () => {
        if (closedGroups.has(group)) closedGroups.delete(group);
        else closedGroups.add(group);
        section.classList.toggle('closed', closedGroups.has(group));
        groupChevron.textContent = closedGroups.has(group) ? '+' : '−';
      });

      const rows = document.createElement('div');
      rows.className = 'pe-lp-rows';

      for (const layer of inGroup) {
        const rowEl = document.createElement('button');
        rowEl.className = 'pe-lp-row';
        rowEl.type = 'button';
        if (layer.visible) rowEl.classList.add('on');

        const check = document.createElement('span');
        check.className = 'pe-lp-check';
        rowEl.appendChild(check);

        const swatchColor = MODE_SWATCH[layer.id];
        if (swatchColor) {
          const swatch = document.createElement('span');
          swatch.className = 'pe-lp-swatch';
          swatch.style.background = swatchColor;
          rowEl.appendChild(swatch);
        }

        const label = document.createElement('span');
        label.className = 'pe-lp-label';
        label.textContent = layer.label;
        rowEl.appendChild(label);

        rowEl.addEventListener('click', () => {
          api.setLayerVisible(layer.id, !rowEl.classList.contains('on'));
        });

        rows.appendChild(rowEl);
      }

      section.append(groupHead, rows);
      body.appendChild(section);
    }
  };

  render(api.getLayers());
  api.events.on('layersChange', ({ layers }) => render(layers));

  return { el };
}
