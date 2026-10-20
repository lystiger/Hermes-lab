/**
 * One time format for the console: local wall-clock time, 24-hour, with the date when it matters.
 * Invalid or missing input is shown as unknown, never as the current time.
 */
export const UNKNOWN_TIME = '—';

export type TimeInput = string | number | Date | null | undefined;

function toDate(value: TimeInput): Date | null {
  if (value === null || value === undefined || value === '') return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0');

/** HH:MM:SS, local time. */
export function formatTimeOfDay(value: TimeInput): string {
  const d = toDate(value);
  return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` : UNKNOWN_TIME;
}

/** YYYY-MM-DD HH:MM:SS, local time. */
export function formatDateTime(value: TimeInput): string {
  const d = toDate(value);
  return d
    ? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${formatTimeOfDay(d)}`
    : UNKNOWN_TIME;
}

/** HH:MM:SS.mmm, local time, for event rows. */
export function formatMillis(value: TimeInput): string {
  const d = toDate(value);
  return d ? `${formatTimeOfDay(d)}.${pad(d.getMilliseconds(), 3)}` : UNKNOWN_TIME;
}
