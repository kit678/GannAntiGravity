function splitSymbolResolution(selectedSymbolRes) {
  if (!selectedSymbolRes) {
    return { symbol: '', resolution: '' };
  }

  const [symbol, resolution] = selectedSymbolRes.split('/');
  return { symbol, resolution };
}

export function extractTimestampToken(path) {
  if (!path) {
    return '';
  }

  const parts = path.split('/');
  return parts.find((part) => /^\d{6}(_all)?$/.test(part)) || '';
}

function getRunScopedReports(reports, selectedSymbolRes, selectedRun) {
  if (!selectedSymbolRes || !selectedRun) {
    return [];
  }

  const { symbol, resolution } = splitSymbolResolution(selectedSymbolRes);
  return reports.filter(
    (report) =>
      report.symbol === symbol &&
      report.resolution === resolution &&
      report.run_id === selectedRun
  );
}

function isAnalysisHypothesisReport(report) {
  return String(report?.path || '').includes('/analysis/hypotheses/');
}

function sortNewestFirst(reports) {
  return [...reports].sort((a, b) => Number(b?.modified || 0) - Number(a?.modified || 0));
}

export function getTimestampOptions(reports, selectedSymbolRes, selectedRun) {
  const runReports = getRunScopedReports(reports, selectedSymbolRes, selectedRun);
  if (runReports.some(isAnalysisHypothesisReport)) {
    return [];
  }

  const seen = new Set();

  return runReports.filter((report) => {
    const token = extractTimestampToken(report.path);
    if (!token || seen.has(token)) {
      return false;
    }
    seen.add(token);
    return true;
  });
}

export function getReportOptions(
  reports,
  selectedSymbolRes,
  selectedRun,
  selectedTimestamp
) {
  const runReports = getRunScopedReports(reports, selectedSymbolRes, selectedRun);
  if (!runReports.length) {
    return [];
  }

  const analysisReports = sortNewestFirst(runReports.filter(isAnalysisHypothesisReport));
  if (analysisReports.length) {
    return analysisReports;
  }

  const timestampedReports = runReports.filter((report) => extractTimestampToken(report.path));
  if (!selectedTimestamp) {
    return timestampedReports.length
      ? []
      : runReports.filter((report) => !extractTimestampToken(report.path));
  }

  return runReports.filter(
    (report) => extractTimestampToken(report.path) === selectedTimestamp
  );
}

export function getPreferredReportPath(
  reports,
  selectedSymbolRes,
  selectedRun,
  selectedTimestamp
) {
  const options = getReportOptions(reports, selectedSymbolRes, selectedRun, selectedTimestamp);
  return options[0]?.path || '';
}

export function resolveSelectedReportPath(
  reports,
  selectedSymbolRes,
  selectedRun,
  selectedTimestamp,
  selectedReport
) {
  const options = getReportOptions(reports, selectedSymbolRes, selectedRun, selectedTimestamp);
  if (!options.length) {
    return '';
  }

  if (selectedReport && options.some((option) => option.path === selectedReport)) {
    return selectedReport;
  }

  return options[0]?.path || '';
}
