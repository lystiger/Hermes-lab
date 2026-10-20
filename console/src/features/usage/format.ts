/** Pure helpers for the Usage page. No React. */

export type StatusTone = 'success' | 'warning' | 'danger' | 'muted';

/** "2h 10m", "45m", "now". Hours are shown with minutes only when the minutes are not zero. */
export function formatResetIn(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 60) return 'now';
  const totalMinutes = Math.floor(seconds / 60);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  if (hours > 0) return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  return `${minutes}m`;
}

/** Maps a limit status (including the page-level `stale` and `not ready`) to a tone. */
export function statusTone(status: string): StatusTone {
  switch (status) {
    case 'ok':
      return 'success';
    case 'warn':
      return 'warning';
    case 'alarm':
      return 'danger';
    default:
      return 'muted';
  }
}
