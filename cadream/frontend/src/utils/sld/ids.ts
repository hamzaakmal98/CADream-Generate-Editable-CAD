const ID_REGEX = /^(?<prefix>[a-z-]+)-(?<counter>\d+)$/i;

export function makeDeterministicId(prefix: string, counter: number): string {
  return `${prefix}-${counter}`;
}

export function parseDeterministicCounter(id: string, prefix: string): number | null {
  const match = id.match(ID_REGEX);
  if (!match?.groups) return null;
  if (match.groups.prefix !== prefix) return null;
  const counter = Number(match.groups.counter);
  return Number.isFinite(counter) ? counter : null;
}

export function computeNextCounter(ids: string[], prefix: string, fallback = 1): number {
  const counters = ids
    .map((id) => parseDeterministicCounter(id, prefix))
    .filter((value): value is number => value !== null);
  if (counters.length === 0) return fallback;
  return Math.max(...counters) + 1;
}
