/** Decimal-string formatting without binary floating point. */
function scaled(value: string, dp: number): bigint {
  const negative = value.trim().startsWith('-');
  const [intPart, fracPart = ''] = value.trim().replace(/^[-+]/, '').split('.');
  const frac = (fracPart + '0'.repeat(dp + 1)).slice(0, dp + 1);
  let v = BigInt(intPart || '0') * 10n ** BigInt(dp + 1) + BigInt(frac || '0');
  v = (v + 5n) / 10n; // round half up
  return negative ? -v : v;
}

export function decimal(value: string | null | undefined, dp = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  const v = scaled(value, dp);
  const abs = v < 0n ? -v : v;
  const base = 10n ** BigInt(dp);
  const intStr = (abs / base).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const fracStr = dp ? '.' + (abs % base).toString().padStart(dp, '0') : '';
  return (v < 0n ? '-' : '') + intStr + fracStr;
}

export function money(value: string | null | undefined, dp = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  return value.trim().startsWith('-') ? `-$${decimal(value.trim().slice(1), dp)}` : `$${decimal(value, dp)}`;
}

/** "2.000" -> "2", "0.50" -> "0.5" */
export function qty(value: string | null | undefined): string {
  if (!value) return '—';
  return value.includes('.') ? value.replace(/\.?0+$/, '') : value;
}

/** Display-only percentage change between two decimal strings. */
export function pctChange(previous: string, current: string): number | null {
  const a = Number(previous), b = Number(current);
  if (!isFinite(a) || !isFinite(b) || a === 0) return null;
  return ((b - a) / a) * 100;
}

const TZ = 'America/New_York';
export const shortDate = (iso: string) =>
  new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: TZ });
export const dateTime = (iso: string) =>
  new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: TZ });
export const timeAgo = (iso: string) => {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return shortDate(iso);
};
export const label = (id: string | null | undefined) =>
  id ? id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—';
