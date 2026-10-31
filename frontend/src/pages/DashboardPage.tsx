import "leaflet/dist/leaflet.css";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import { Link } from "react-router-dom";
import { HYDERABAD } from "../components/MapPicker";
import { get, type MapFeature, type Meta, type Metrics } from "../lib/api";

const SEV_COLOR: Record<string, string> = { low: "#2e9e57", medium: "#d4a017", high: "#e07b1a", critical: "#c62828" };
const STATUSES = ["sent", "acknowledged", "in_progress", "resolved", "reopened", "merged", "dispatch_failed"];

export default function DashboardPage() {
  const { t } = useTranslation();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [features, setFeatures] = useState<MapFeature[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [group, setGroup] = useState<"ward" | "department">("ward");
  const [f, setF] = useState({ category: "", severity: "", status: "" });
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    get<Meta>("/api/meta/").then(setMeta).catch(() => undefined);
  }, []);

  useEffect(() => {
    const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
    get<{ features: MapFeature[] }>(`/api/map/?${qs}`)
      .then((d) => {
        setFeatures(d.features);
        setLoaded(true);
      })
      .catch(() => setError(true));
  }, [f]);

  useEffect(() => {
    get<Metrics>(`/api/metrics/?group=${group}`).then(setMetrics).catch(() => setError(true));
  }, [group]);

  const na = t("dashboard.na");
  const num = (v: number | null, suffix = "") => (v == null ? na : `${v}${suffix}`);
  const empty = loaded && metrics?.totals.reports === 0;

  return (
    <div className="stack">
      <h1>{t("dashboard.title")}</h1>
      {error && <div className="err">{t("common.error")}</div>}

      <div className="stats">
        <div className="stat"><b>{metrics?.totals.reports ?? "-"}</b><small>{t("dashboard.reports")}</small></div>
        <div className="stat"><b>{metrics?.totals.open ?? "-"}</b><small>{t("dashboard.open")}</small></div>
        <div className="stat"><b>{metrics?.totals.resolved ?? "-"}</b><small>{t("dashboard.resolved")}</small></div>
      </div>

      {empty && <div className="notice">{t("dashboard.empty")}</div>}

      <section className="card stack">
        <b>{t("dashboard.filters")}</b>
        <div className="row wrap">
          <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} aria-label={t("dashboard.category")}>
            <option value="">{t("dashboard.category")}: {t("dashboard.all")}</option>
            {meta?.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
          <select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })} aria-label={t("dashboard.severity")}>
            <option value="">{t("dashboard.severity")}: {t("dashboard.all")}</option>
            {["low", "medium", "high", "critical"].map((s) => <option key={s} value={s}>{t(`severity.${s}`)}</option>)}
          </select>
          <select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} aria-label={t("dashboard.status")}>
            <option value="">{t("dashboard.status")}: {t("dashboard.all")}</option>
            {STATUSES.map((s) => <option key={s} value={s}>{t(`status.${s}`)}</option>)}
          </select>
        </div>
        <MapContainer center={HYDERABAD} zoom={11} className="map tall" scrollWheelZoom>
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} />
          {features.map((ft) => (
            <CircleMarker
              key={ft.properties.ref_no}
              center={[ft.geometry.coordinates[1], ft.geometry.coordinates[0]]}
              radius={8 + Math.min(ft.properties.affected, 6)}
              pathOptions={{ color: SEV_COLOR[ft.properties.severity] ?? "#555", fillOpacity: 0.7 }}
            >
              <Popup>
                <b>{ft.properties.category_label}</b><br />
                {t(`severity.${ft.properties.severity}`)} · {t(`status.${ft.properties.status}`, ft.properties.status)}<br />
                {ft.properties.ward}<br />
                <Link to={`/r/${ft.properties.ref_no}`}>{ft.properties.ref_no}</Link>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </section>

      <section className="card stack">
        <div className="row wrap">
          <button className={`btn ${group === "ward" ? "primary" : "ghost"}`} onClick={() => setGroup("ward")}>{t("dashboard.byWard")}</button>
          <button className={`btn ${group === "department" ? "primary" : "ghost"}`} onClick={() => setGroup("department")}>{t("dashboard.byDept")}</button>
        </div>
        {metrics && metrics.rows.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th></th><th>{t("dashboard.volume")}</th><th>{t("dashboard.ack")}</th><th>{t("dashboard.res")}</th>
                  <th>{t("dashboard.reopen")}</th><th>{t("dashboard.backlog")}</th>
                </tr>
              </thead>
              <tbody>
                {metrics.rows.map((row) => (
                  <tr key={row.name}>
                    <th scope="row">{row.name}</th>
                    <td>{row.volume}</td>
                    <td>{num(row.median_hours_to_acknowledge, " h")} <small className="muted">({row.acknowledged}/{row.sent})</small></td>
                    <td>{num(row.median_hours_to_resolve, " h")} <small className="muted">({row.resolved}/{row.sent})</small></td>
                    <td>{row.reopen_rate == null ? na : `${Math.round(row.reopen_rate * 100)}%`}</td>
                    <td>{row.aging_backlog}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <details className="card">
        <summary>{t("dashboard.definitions")}</summary>
        <ul>{metrics && Object.entries(metrics.definitions).map(([k, v]) => <li key={k}><b>{k.replace(/_/g, " ")}:</b> {v}</li>)}</ul>
      </details>

      <a className="btn secondary" href="/api/export/reports.csv">{t("dashboard.export")}</a>
    </div>
  );
}
