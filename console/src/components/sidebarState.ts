/** Sidebar preference storage. Every access is guarded: private windows and blocked storage must not break the UI. */
export const SIDEBAR_STORAGE_KEY = 'lys.sidebar.collapsed';

/** Windows narrower than this collapse the sidebar automatically (M7 item 3). */
export const SIDEBAR_NARROW_QUERY = '(max-width: 1099px)';

export function readSidebarCollapsed(): boolean | null {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (raw === '1') return true;
    if (raw === '0') return false;
    return null;
  } catch {
    return null;
  }
}

export function writeSidebarCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? '1' : '0');
  } catch {
    /* storage unavailable: the choice lasts for this page view only */
  }
}

/** True while the focus is in a field, where "[" is text, not a shortcut. */
export function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  if (el.isContentEditable) return true;
  return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT';
}
