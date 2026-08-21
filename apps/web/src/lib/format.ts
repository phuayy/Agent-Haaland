export function timeAgo(iso: string): string {
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));

  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;

  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay}d ago`;

  const diffWeek = Math.floor(diffDay / 7);
  if (diffWeek < 4) return `${diffWeek}w ago`;

  const diffMonth = Math.floor(diffDay / 30);
  if (diffMonth < 12) return `${diffMonth}mo ago`;

  const diffYear = Math.floor(diffDay / 365);
  return `${diffYear}y ago`;
}

/** `services.tier` is a smallint on the wire (1 = core, 2 = standard,
 * 3 = internal); the UI has always shown the words. */
export function tierLabel(tier: number): string {
  return `Tier ${tier}`;
}

export function tierDescription(tier: number): string {
  return { 1: "Core", 2: "Standard", 3: "Internal" }[tier] ?? "Standard";
}

/** Strips the scheme so a repo URL reads as `github.com/org/repo` on a card. */
export function repoLabel(repoUrl: string): string {
  return repoUrl.replace(/^https?:\/\//, "");
}
