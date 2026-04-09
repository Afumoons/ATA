export function formatCurrency(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(
  value: number | null | undefined,
  options?: Intl.NumberFormatOptions,
) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", options).format(value);
}

export function formatPercent(value: number | null | undefined, maximumFractionDigits = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${formatNumber(value, { maximumFractionDigits })}%`;
}

export function formatDateTime(value: unknown) {
  if (!value || typeof value !== "string") return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function formatRelativeAge(value: unknown) {
  if (!value || typeof value !== "string") return "Unknown age";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown age";

  const diffMs = Date.now() - parsed.getTime();
  const absMs = Math.abs(diffMs);
  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  let formatted = "just now";
  if (absMs >= day) {
    formatted = `${Math.round(absMs / day)}d`;
  } else if (absMs >= hour) {
    formatted = `${Math.round(absMs / hour)}h`;
  } else if (absMs >= minute) {
    formatted = `${Math.round(absMs / minute)}m`;
  }

  return diffMs >= 0 ? `${formatted} ago` : `in ${formatted}`;
}

export function prettifyKey(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function truncateMiddle(value: string, maxLength = 56) {
  if (value.length <= maxLength) return value;
  const slice = Math.floor((maxLength - 3) / 2);
  return `${value.slice(0, slice)}...${value.slice(-slice)}`;
}

export function compactValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value || "—";
  if (Array.isArray(value)) {
    if (!value.length) return "[]";
    return value.length <= 4 ? JSON.stringify(value) : `${value.length} items`;
  }
  try {
    const encoded = JSON.stringify(value);
    return encoded.length > 120 ? `${encoded.slice(0, 117)}...` : encoded;
  } catch {
    return String(value);
  }
}
