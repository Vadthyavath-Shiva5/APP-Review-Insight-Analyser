import { promises as fs } from "fs";
import path from "path";

const ROOT = process.cwd();

function abs(...parts) {
  return path.join(ROOT, ...parts);
}

async function readTextSafe(filePath) {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch {
    return "";
  }
}

async function readJsonSafe(filePath) {
  try {
    const text = await fs.readFile(filePath, "utf8");
    return JSON.parse(text);
  } catch {
    return {};
  }
}

async function countCsvDataRows(filePath) {
  try {
    const text = await fs.readFile(filePath, "utf8");
    const lines = text.split(/\r?\n/).filter((line) => line.trim() !== "");
    return Math.max(lines.length - 1, 0);
  } catch {
    return null;
  }
}

async function resolveRedactedReviewCount() {
  const redactedMeta = await readJsonSafe(abs("data", "processed", "reviews_15w_redacted_meta.json"));
  const rowsOutput = Number(redactedMeta?.stats?.rows_output);
  if (Number.isFinite(rowsOutput) && rowsOutput >= 0) {
    return rowsOutput;
  }

  return countCsvDataRows(abs("data", "processed", "reviews_15w_redacted.csv"));
}

function section(lines, start, end = null) {
  const sidx = lines.indexOf(start);
  if (sidx < 0) return [];
  const eidx = end ? lines.indexOf(end) : -1;
  return lines.slice(sidx + 1, eidx > sidx ? eidx : undefined);
}

function parseThemeOneLiners(noteText) {
  const lines = noteText.split(/\r?\n/);
  const rows = section(lines, "## Theme One-Liners", "## Quick Summary");
  const map = {};

  for (const raw of rows) {
    const line = raw.trim().replace(/^-\s*/, "").replace(/\*\*/g, "");
    if (!line || !line.includes(":")) continue;
    const [name, ...rest] = line.split(":");
    map[name.trim()] = rest.join(":").trim();
  }

  return map;
}

function parseActionableInsights(noteText) {
  const lines = noteText.split(/\r?\n/);
  const rows = section(lines, "## 3 Actionable Insights and Advice", "## Top 5 User Reviews By Theme");
  const actions = [];

  for (const raw of rows) {
    const line = raw.trim();
    const match = line.match(/^\d+\.\s+(.+)$/);
    if (match) actions.push(match[1].trim());
  }

  return actions;
}

async function latestUpdatedAt() {
  const noteMeta = await readJsonSafe(abs("data", "outputs", "weekly_note_meta.json"));
  const pipelineMeta = await readJsonSafe(abs("data", "outputs", "pipeline_run_meta.json"));
  return noteMeta.generated_at_utc || pipelineMeta.ended_at_utc || null;
}

export async function loadDashboardData() {
  const themesPayload = await readJsonSafe(abs("data", "processed", "themes_weekly.json"));
  const noteText = await readTextSafe(abs("data", "outputs", "weekly_note.md"));
  const redactedReviewCount = await resolveRedactedReviewCount();
  const attachments = await resolveLatestAttachmentPaths();

  const oneLiners = parseThemeOneLiners(noteText);
  const insights = parseActionableInsights(noteText);
  const themes = Array.isArray(themesPayload.themes) ? themesPayload.themes : [];

  const transformedThemes = themes.map((theme) => ({
    name: theme.name || "Unnamed Theme",
    oneLiner: oneLiners[theme.name] || theme.summary || `${theme.count || 0} mapped reviews in this theme.`,
    topReviews: (theme.top_reviews || []).slice(0, 5).map((r) => ({
      rating: r.rating ?? "N/A",
      date: r.date || "N/A",
      text: (r.text || "").trim(),
    })),
  }));

  return {
    title: "GROWW Reviews - Analyser",
    latestUpdatedAt: await latestUpdatedAt(),
    processLoadedAt: new Date().toISOString(),
    analysisWindow: {
      from: themesPayload.analysis_window_start || themesPayload.week_start || null,
      to: themesPayload.analysis_window_end || themesPayload.week_end || null,
      sampleSize: redactedReviewCount,
      claudeSampleSize: themesPayload?.sampling?.sample_size_used ?? null,
    },
    themes: transformedThemes,
    actionableInsights: insights,
    attachments: {
      pdfName: attachments.pdfName,
      csvName: attachments.csvName,
      pdfDownloadUrl: attachments.pdfName ? "/api/download?kind=pdf" : null,
      csvDownloadUrl: attachments.csvName ? "/api/download?kind=csv" : null,
    },
  };
}

export async function resolveLatestAttachmentPaths() {
  const outputsDir = abs("data", "outputs");
  let names = [];
  try {
    names = await fs.readdir(outputsDir);
  } catch {
    return {
      pdfPath: null,
      csvPath: null,
      pdfName: null,
      csvName: null,
    };
  }

  const datedPdfs = names.filter((n) => /^groww_weekly_insights_\d{4}-\d{2}-\d{2}\.pdf$/.test(n)).sort();
  const datedCsv = names.filter((n) => /^groww_reviews_redacted_\d{4}-\d{2}-\d{2}\.csv$/.test(n)).sort();

  const pdfName = datedPdfs.length ? datedPdfs[datedPdfs.length - 1] : null;
  const csvName = datedCsv.length ? datedCsv[datedCsv.length - 1] : null;

  return {
    pdfPath: pdfName ? path.join(outputsDir, pdfName) : null,
    csvPath: csvName ? path.join(outputsDir, csvName) : null,
    pdfName,
    csvName,
  };
}

export async function readEmailDraftParts() {
  const draft = await readTextSafe(abs("data", "outputs", "email_draft.txt"));
  if (!draft) {
    return {
      subject: "Weekly Review Insights - GROWW",
      body: "Hello Team,\n\nNo draft found. Please run pipeline first.",
    };
  }

  const lines = draft.split(/\r?\n/);
  const subjectLine = lines.find((l) => l.startsWith("Subject:"));
  const subject = subjectLine ? subjectLine.replace("Subject:", "").trim() : "Weekly Review Insights - GROWW";

  const blankIdx = lines.findIndex((l) => l.trim() === "");
  const body = blankIdx >= 0 ? lines.slice(blankIdx + 1).join("\n").trim() : draft;

  return { subject, body };
}

export async function readPipelineMeta() {
  return readJsonSafe(abs("data", "outputs", "pipeline_run_meta.json"));
}
