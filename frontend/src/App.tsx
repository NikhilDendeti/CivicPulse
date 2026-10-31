import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Route, Routes } from "react-router-dom";
import { setLang } from "./lib/i18n";
import { pendingCount, startAutoFlush } from "./lib/offlineQueue";
import DashboardPage from "./pages/DashboardPage";
import MinePage from "./pages/MinePage";
import ReportPage from "./pages/ReportPage";
import StatusPage from "./pages/StatusPage";

export default function App() {
  const { t, i18n } = useTranslation();
  const [pending, setPending] = useState(0);
  const [toast, setToast] = useState("");

  const refresh = useCallback(() => void pendingCount().then(setPending), []);

  useEffect(() => {
    refresh();
    return startAutoFlush(() => {
      setToast(t("report.uploaded"));
      refresh();
      setTimeout(() => setToast(""), 5000);
    });
  }, [refresh, t]);

  return (
    <>
      <header className="top">
        <NavLink to="/" className="brand">CivicPulse</NavLink>
        <nav>
          <NavLink to="/">{t("nav.report")}</NavLink>
          <NavLink to="/dashboard">{t("nav.dashboard")}</NavLink>
          <NavLink to="/mine">{t("nav.mine")}</NavLink>
        </nav>
        <select aria-label={t("common.language")} value={i18n.language} onChange={(e) => setLang(e.target.value as "en" | "te")}>
          <option value="en">EN</option>
          <option value="te">తెలుగు</option>
        </select>
      </header>
      {toast && <div className="toast" role="status">{toast}</div>}
      <main>
        <Routes>
          <Route path="/" element={<ReportPage pending={pending} onQueued={refresh} />} />
          <Route path="/r/:ref" element={<StatusPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/mine" element={<MinePage />} />
        </Routes>
      </main>
    </>
  );
}
