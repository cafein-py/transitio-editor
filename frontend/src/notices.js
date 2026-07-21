// Pure helpers for presenting a transitio validation report
// ({ notices, row_counts, service_window }).
const SEVERITY_ORDER = { ERROR: 0, WARNING: 1, INFO: 2 };

export function severityCounts(report) {
  const counts = { ERROR: 0, WARNING: 0, INFO: 0 };
  if (report) {
    for (const notice of report.notices) {
      counts[notice.severity] = (counts[notice.severity] || 0) + 1;
    }
  }
  return counts;
}

export function groupNotices(report, { sampleLimit = 20 } = {}) {
  if (!report) return [];
  const groups = new Map();
  for (const notice of report.notices) {
    let group = groups.get(notice.code);
    if (!group) {
      group = { code: notice.code, severity: notice.severity, count: 0, contexts: [] };
      groups.set(notice.code, group);
    }
    group.count += 1;
    if (group.contexts.length < sampleLimit) {
      group.contexts.push(notice.context || {});
    }
  }
  return [...groups.values()].sort(
    (a, b) =>
      (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3) ||
      b.count - a.count,
  );
}

export function describeContext(context) {
  const parts = Object.entries(context).map(([key, value]) => `${key}=${value}`);
  return parts.length ? parts.join(", ") : "(no context)";
}
