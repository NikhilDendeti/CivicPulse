import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import Timeline from "../components/Timeline";
import { ApiError, get, postJson, type Meta, type Report } from "../lib/api";

const ACTIVE = new Set(["submitted", "analysing"]);

export default function StatusPage() {
  const { ref = "" } = useParams();
  const { t } = useTranslation();
  const [report, setReport] = useState<Report | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [err, setErr] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const r = await get<Report>(`/api/reports/${ref}/`);
      setReport(r);
      setNotFound(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setNotFound(true);
    }
  }, [ref]);

  useEffect(() => {
    void load();
    get<Meta>("/api/meta/").then(setMeta).catch(() => undefined);
  }, [load]);

  // Poll while the pipeline is working or the report is mid-flight.
  useEffect(() => {
    window.clearInterval(timer.current);
    const interval = report && ACTIVE.has(report.status) ? 1500 : report && ["routed", "sent", "acknowledged", "in_progress", "analysed"].includes(report.status) ? 8000 : 0;
    if (interval) timer.current = window.setInterval(load, interval);
    return () => window.clearInterval(timer.current);
  }, [report?.status, load]);

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true);
    setErr("");
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  if (notFound) return <p>{t("status.notFound")}</p>;
  if (!report) return <p>{t("status.loading")}</p>;

  const r = report;
  const owner = r.is_owner;
  const needsChoice = r.status === "needs_info" && !r.category;

  return (
    <div className="stack">
      <h1>{t("status.title", { ref: r.ref_no })}</h1>
      <div className="row wrap">
        <span className="pill">{t(`status.${r.status}`, r.status)}</span>
        {r.severity_level && <span className={`pill sev-${r.severity_level}`}>{t(`severity.${r.severity_level}`)}</span>}
        {r.category_label && <span className="pill">{r.category_label}</span>}
        {r.ward && <span className="pill">{r.ward}</span>}
        {r.affected_count > 1 && <span className="pill">{t("dashboard.affected", { n: r.affected_count })}</span>}
      </div>

      {r.image_url && <img className="preview" src={r.image_url} alt="Reported issue" />}
      {ACTIVE.has(r.status) && <div className="notice">{t("result.analysing")}</div>}

      {r.status === "merged" && r.canonical_ref && (
        <div className="notice">
          {t("result.merged", { ref: r.canonical_ref, n: r.affected_count })} <Link to={`/r/${r.canonical_ref}`}>{r.canonical_ref}</Link>
        </div>
      )}

      {(r.description || r.rationale) && (
        <section className="card stack">
          <b>{t("result.heading")}</b>
          {r.description && <div>{r.description}</div>}
          {r.rationale && (
            <div>
              <small className="muted">{t("result.why")}: </small>
              {r.rationale}
            </div>
          )}
          {r.confidence != null && (
            <small className="muted">
              {t("result.confidence")}: {Math.round(r.confidence * 100)}%{r.severity_score != null && ` · ${t("result.severity")}: ${r.severity_score}/100`}
            </small>
          )}
          {r.factors.length > 0 && (
            <details>
              <summary>{t("result.howSeverity")}</summary>
              <ul>{r.factors.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </details>
          )}
        </section>
      )}

      {owner && r.status === "needs_review" && <div className="notice">{r.ai_error ? t("result.aiUnavailable") : t("result.review")}</div>}

      {owner && r.status === "needs_info" && (
        <section className="card stack">
          <b>{t("result.question")}</b>
          {r.clarifying_question && <div>{r.clarifying_question}</div>}
          {needsChoice ? null : (
            <>
              <textarea rows={2} value={answer} placeholder={t("result.answer")} onChange={(e) => setAnswer(e.target.value)} />
              <button className="btn primary" disabled={busy || !answer.trim()} onClick={() => act(() => postJson(`/api/reports/${ref}/answer/`, { answer }))}>
                {t("result.sendAnswer")}
              </button>
            </>
          )}
        </section>
      )}

      {owner && (r.status === "analysed" || r.status === "needs_info") && meta && (
        <section className="card stack">
          <details open={r.status === "needs_info" && needsChoice}>
            <summary>{t("result.edit")}</summary>
            <label className="stack">
              <span>{t("result.category")}</span>
              <select value={category || r.category} onChange={(e) => setCategory(e.target.value)}>
                {!r.category && <option value="">{t("result.chooseCategory")}</option>}
                {meta.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
            </label>
            <label className="stack">
              <span>{t("result.severity")}</span>
              <select value={severity || r.severity_level} onChange={(e) => setSeverity(e.target.value)}>
                {!r.severity_level && <option value="">-</option>}
                {["low", "medium", "high", "critical"].map((s) => <option key={s} value={s}>{t(`severity.${s}`)}</option>)}
              </select>
            </label>
          </details>
          <button
            className="btn primary big"
            disabled={busy || (!r.category && !category)}
            onClick={() => act(() => postJson(`/api/reports/${ref}/confirm/`, { category: category || undefined, severity_level: severity || undefined }))}
          >
            {t("result.confirm")}
          </button>
        </section>
      )}

      {r.authority && (
        <section className="card stack">
          <b>{t("routing.heading")}: {r.authority}</b>
          {r.routing_reason && <small className="muted">{t("routing.reason")}: {r.routing_reason}</small>}
          {r.delivery.some((d) => d.mode === "sandbox") && <small className="notice">{t("routing.sandbox")}</small>}
        </section>
      )}

      {owner && r.status === "resolved" && (
        <section className="card stack">
          <b>{t("resolution.heading")}</b>
          <textarea rows={2} value={note} placeholder={t("resolution.note")} onChange={(e) => setNote(e.target.value)} />
          <div className="row">
            <button className="btn primary" disabled={busy} onClick={() => act(() => postJson(`/api/reports/${ref}/resolution/`, { action: "confirm" }))}>
              {t("resolution.confirm")}
            </button>
            <button className="btn danger" disabled={busy} onClick={() => act(() => postJson(`/api/reports/${ref}/resolution/`, { action: "dispute", note }))}>
              {t("resolution.dispute")}
            </button>
          </div>
        </section>
      )}

      {err && <div className="err" role="alert">{err}</div>}

      <section className="card">
        <b>{t("timeline.heading")}</b>
        <Timeline events={r.timeline} />
      </section>
    </div>
  );
}
