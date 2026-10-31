import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { get, myRefs, type Report } from "../lib/api";

export default function MinePage() {
  const { t } = useTranslation();
  const [reports, setReports] = useState<Report[]>([]);

  useEffect(() => {
    Promise.all(myRefs().map((r) => get<Report>(`/api/reports/${r}/`).catch(() => null))).then((rs) =>
      setReports(rs.filter((r): r is Report => r !== null)),
    );
  }, []);

  return (
    <div className="stack">
      <h1>{t("mine.title")}</h1>
      {reports.length === 0 && <p className="muted">{t("mine.empty")}</p>}
      {reports.map((r) => (
        <Link key={r.ref_no} to={`/r/${r.ref_no}`} className="card link">
          <b>{r.ref_no}</b> <span className="pill">{t(`status.${r.status}`, r.status)}</span>
          <div className="muted">{r.category_label || r.description || new Date(r.created_at).toLocaleString()}</div>
        </Link>
      ))}
    </div>
  );
}
