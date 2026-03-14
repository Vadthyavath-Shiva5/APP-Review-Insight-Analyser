"use client";

import { useEffect, useMemo, useState } from "react";

const MIN_WEEK = 1;
const MAX_WEEK = 15;
const MIN_REPROCESS_WEEKS = 6;

function fmt(value) {
  if (!value) return "N/A";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function parseWeekInput(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  if (!/^\d+$/.test(text)) return null;
  return Number.parseInt(text, 10);
}

function spanWeeks(weeksFrom, weeksTo) {
  return weeksTo - weeksFrom + 1;
}

export default function Page() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openTheme, setOpenTheme] = useState("");

  const [recipientEmail, setRecipientEmail] = useState("");
  const [weeksFromInput, setWeeksFromInput] = useState("1");
  const [weeksToInput, setWeeksToInput] = useState("15");
  const [busySend, setBusySend] = useState(false);
  const [busyReprocess, setBusyReprocess] = useState(false);
  const [message, setMessage] = useState({ type: "", text: "" });

  async function fetchDashboard() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/dashboard", { cache: "no-store" });
      const json = await res.json();
      if (!res.ok || !json.ok) throw new Error(json.error || "Failed to load dashboard");
      setData(json.data);
      if (json.data?.themes?.length && !openTheme) {
        setOpenTheme(json.data.themes[0].name);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchDashboard();
  }, []);

  const latestUpdated = useMemo(() => fmt(data?.latestUpdatedAt), [data]);
  const loadedAt = useMemo(() => fmt(data?.processLoadedAt), [data]);

  const weeksFrom = useMemo(() => parseWeekInput(weeksFromInput), [weeksFromInput]);
  const weeksTo = useMemo(() => parseWeekInput(weeksToInput), [weeksToInput]);

  const selectedWeekSpan = useMemo(() => {
    if (weeksFrom === null || weeksTo === null) return null;
    return spanWeeks(weeksFrom, weeksTo);
  }, [weeksFrom, weeksTo]);

  const invalidWeekRange = useMemo(() => {
    if (weeksFrom === null || weeksTo === null) return true;
    if (weeksFrom < MIN_WEEK || weeksFrom > MAX_WEEK) return true;
    if (weeksTo < MIN_WEEK || weeksTo > MAX_WEEK) return true;
    if (weeksFrom > weeksTo) return true;
    return selectedWeekSpan < MIN_REPROCESS_WEEKS;
  }, [weeksFrom, weeksTo, selectedWeekSpan]);

  async function handleSendCurrent() {
    if (!recipientEmail.trim()) {
      setMessage({ type: "err", text: "Please enter recipient email." });
      return;
    }

    setBusySend(true);
    setMessage({ type: "", text: "" });
    try {
      const res = await fetch("/api/send-email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipientEmail: recipientEmail.trim() }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) throw new Error(json.error || "Failed to send email");
      setMessage({ type: "ok", text: json.message || "Email sent." });
    } catch (err) {
      setMessage({ type: "err", text: err instanceof Error ? err.message : "Failed to send email" });
    } finally {
      setBusySend(false);
    }
  }

  async function handleReprocessSend() {
    if (!recipientEmail.trim()) {
      setMessage({ type: "err", text: "Please enter recipient email." });
      return;
    }
    if (weeksFrom === null || weeksTo === null) {
      setMessage({ type: "err", text: "Please enter valid week numbers." });
      return;
    }
    if (weeksFrom < MIN_WEEK || weeksFrom > MAX_WEEK || weeksTo < MIN_WEEK || weeksTo > MAX_WEEK) {
      setMessage({ type: "err", text: `Weeks must be between ${MIN_WEEK} and ${MAX_WEEK}.` });
      return;
    }
    if (weeksFrom > weeksTo) {
      setMessage({ type: "err", text: "From week must be less than or equal to To week." });
      return;
    }
    if (selectedWeekSpan < MIN_REPROCESS_WEEKS) {
      setMessage({ type: "err", text: `Please select at least ${MIN_REPROCESS_WEEKS} weeks for reprocess.` });
      return;
    }

    setBusyReprocess(true);
    setMessage({ type: "", text: "" });
    try {
      const res = await fetch("/api/reprocess-and-send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipientEmail: recipientEmail.trim(),
          weeksFrom,
          weeksTo,
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.ok) throw new Error(json.error || "Failed to trigger reprocess");
      setMessage({ type: "ok", text: json.message || "Reprocess triggered." });
      await fetchDashboard();
    } catch (err) {
      setMessage({ type: "err", text: err instanceof Error ? err.message : "Failed to trigger reprocess" });
    } finally {
      setBusyReprocess(false);
    }
  }

  return (
    <main className="page">
      <section className="hero">
        <div className="heroCard">
          <h1 className="heroTitle">GROWW Reviews - Analyser</h1>
          <p className="heroSub">
            Weekly pulse dashboard for themes, insights, and evidence-driven review highlights.
          </p>
        </div>
        <aside className="metaCard">
          <div className="metaLabel">Latest Updated</div>
          <div className="metaValue">{latestUpdated}</div>
          <div className="metaLabel">Process Loaded</div>
          <div className="metaValue">{loadedAt}</div>
          <div className="metaLabel">Window</div>
          <div className="metaValue">
            {data?.analysisWindow?.from || "N/A"} to {data?.analysisWindow?.to || "N/A"}
          </div>
          <div className="metaLabel">Total Redacted Reviews</div>
          <div className="metaValue">{data?.analysisWindow?.sampleSize ?? "N/A"}</div>
        </aside>
      </section>

      <section className="mainGrid">
        <div>
          <div className="sectionCard">
            <h2 className="sectionTitle">Themes</h2>
            {loading && <p>Loading dashboard...</p>}
            {error && <p className="message err">{error}</p>}
            {!loading && !error && (
              <div className="themeList">
                {(data?.themes || []).map((theme) => {
                  const isOpen = openTheme === theme.name;
                  return (
                    <article key={theme.name} className="themeCard">
                      <button
                        className="themeHead"
                        onClick={() => setOpenTheme(isOpen ? "" : theme.name)}
                        type="button"
                      >
                        {theme.name}
                      </button>
                      {isOpen && <div className="themeBody">{theme.oneLiner}</div>}
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          <div className="sectionCard">
            <h2 className="sectionTitle">Actionable Insights</h2>
            <ol className="actionList">
              {(data?.actionableInsights || []).map((item, idx) => (
                <li key={`${idx}-${item}`}>{item}</li>
              ))}
            </ol>
          </div>

          <div className="sectionCard">
            <h2 className="sectionTitle">Top 5 Reviews of Each Theme</h2>
            {(data?.themes || []).map((theme) => (
              <div className="reviewTheme" key={`rv-${theme.name}`}>
                <h4>{theme.name}</h4>
                <ol className="reviewList">
                  {(theme.topReviews || []).map((review, idx) => (
                    <li key={`${theme.name}-${idx}`}>
                      <strong>{review.rating}★</strong> ({review.date}) - {review.text}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </div>

        <aside className="panel">
          <h3 className="sideTitle">Send & Reprocess</h3>

          <div className="formRow">
            <label htmlFor="email">Recipient Email</label>
            <input
              id="email"
              type="email"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              placeholder="name@example.com"
            />
          </div>

          <div className="weekGrid">
            <div className="formRow">
              <label htmlFor="wf">From Week (1-15)</label>
              <input
                id="wf"
                type="number"
                min={MIN_WEEK}
                max={MAX_WEEK}
                step={1}
                value={weeksFromInput}
                onChange={(e) => setWeeksFromInput(e.target.value)}
              />
            </div>
            <div className="formRow">
              <label htmlFor="wt">To Week (1-15)</label>
              <input
                id="wt"
                type="number"
                min={MIN_WEEK}
                max={MAX_WEEK}
                step={1}
                value={weeksToInput}
                onChange={(e) => setWeeksToInput(e.target.value)}
              />
            </div>
          </div>

          <p className="hint">Selected range span: {selectedWeekSpan ?? "-"} week(s).</p>
          <p className="hint">Reprocess requires at least {MIN_REPROCESS_WEEKS} weeks.</p>

          <div className="timelineCard">
            <h4 className="timelineTitle">Processing Timelines</h4>
            <ul className="timelineList">
              <li>Request acceptance: 2-10 seconds.</li>
              <li>1-6 selected weeks: 2-4 minutes.</li>
              <li>7-10 selected weeks: 3-6 minutes.</li>
              <li>11-15 selected weeks: 4-8 minutes.</li>
              <li>Peak delays (cold start or API latency): up to 10-12 minutes.</li>
            </ul>
            <p className="hint">Please check your email after the expected timeline.</p>
          </div>

          <button type="button" className="btn" onClick={handleSendCurrent} disabled={busySend || busyReprocess}>
            {busySend ? "Sending..." : "Send Current Generated Email"}
          </button>

          <button
            type="button"
            className="btn secondary"
            onClick={handleReprocessSend}
            disabled={busyReprocess || busySend || invalidWeekRange}
          >
            {busyReprocess ? "Reprocessing..." : "Reprocess Selected Weeks and Send"}
          </button>

          <p className="hint">
            Email is sent via Brevo. Set BREVO_API_KEY and EMAIL_FROM_ADDRESS in Vercel. Reprocess uses backend
            webhook: set PIPELINE_TRIGGER_URL and PIPELINE_TRIGGER_TOKEN in Vercel.
          </p>

          <div className="downloadCard">
            <h4 className="downloadTitle">Latest Attachments</h4>
            {data?.attachments?.pdfDownloadUrl ? (
              <a className="downloadLink" href={data.attachments.pdfDownloadUrl}>
                Download {data.attachments.pdfName}
              </a>
            ) : (
              <p className="hint">PDF is not available yet.</p>
            )}
            {data?.attachments?.csvDownloadUrl ? (
              <a className="downloadLink" href={data.attachments.csvDownloadUrl}>
                Download {data.attachments.csvName}
              </a>
            ) : (
              <p className="hint">CSV is not available yet.</p>
            )}
          </div>

          {message.text && <div className={`message ${message.type === "ok" ? "ok" : "err"}`}>{message.text}</div>}
        </aside>
      </section>
    </main>
  );
}

