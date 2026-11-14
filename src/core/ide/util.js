// Shared utilities for IDE adapters.

// Approximation of sort -V: comparator for version-like directories/strings. Sorts "3.0.9" < "3.0.10" correctly.
export function compareCacheName(a, b) {
  const pa = a.split(".").map((n) => parseInt(n, 10) || 0);
  const pb = b.split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d) return d;
  }
  return a.localeCompare(b);
}

// Status → display tag (" ✓ latest" / " → update available: vX"). Empty string without templateVersion.
export function versionTag(installedVersion, templateVersion) {
  if (!templateVersion || !installedVersion) return "";
  return installedVersion === templateVersion ? " ✓ latest" : ` → update available: v${templateVersion}`;
}
