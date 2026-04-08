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

export function formatDateTime(value: unknown) {
  if (!value || typeof value !== "string") return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function prettifyKey(key: string) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function compactValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
