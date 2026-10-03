/**
 * Toasts — bottom-right notification stack. Glass cards with a
 * tone-colored left border, auto-dismiss with hover pause.
 */

import type { AppApi } from '../app/api';

const LIFETIME_MS = 6000;
const MAX_STACK = 4;

export function createToasts(api: AppApi): { el: HTMLElement } {
  const el = document.createElement('div');
  el.className = 'pe-toasts';

  api.events.on('toast', ({ title, body, tone }) => {
    const card = document.createElement('div');
    card.className = 'pe-toast';
    if (tone === 'warn' || tone === 'alert') card.classList.add(tone);

    const titleEl = document.createElement('div');
    titleEl.className = 'pe-toast-title';
    titleEl.textContent = title;
    card.appendChild(titleEl);

    if (body) {
      const bodyEl = document.createElement('div');
      bodyEl.className = 'pe-toast-body';
      bodyEl.textContent = body;
      card.appendChild(bodyEl);
    }

    let timer = 0;
    let deadline = 0;
    let remaining = LIFETIME_MS;
    let dismissed = false;

    const dismiss = (): void => {
      if (dismissed) return;
      dismissed = true;
      window.clearTimeout(timer);
      card.classList.add('out');
      window.setTimeout(() => card.remove(), 380);
    };

    const arm = (ms: number): void => {
      deadline = Date.now() + ms;
      timer = window.setTimeout(dismiss, ms);
    };

    card.addEventListener('mouseenter', () => {
      if (dismissed) return;
      window.clearTimeout(timer);
      remaining = Math.max(600, deadline - Date.now());
    });
    card.addEventListener('mouseleave', () => {
      if (dismissed) return;
      arm(remaining);
    });
    card.addEventListener('click', dismiss);

    // cap the stack — drop the oldest
    while (el.children.length >= MAX_STACK) {
      el.firstElementChild?.remove();
    }

    el.appendChild(card);
    arm(LIFETIME_MS);
  });

  return { el };
}
