import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Reveal from "../components/Reveal";

const STEP_ICONS = ["📸", "🧠", "📨", "🔎"];
const PROBLEM_ICONS = ["🧩", "⚖️", "👁️"];

export default function LandingPage() {
  const { t } = useTranslation();
  return (
    <div className="landing">
      <section className="hero-wrap">
        <div className="blob b1" /><div className="blob b2" /><div className="blob b3" />
        <div className="hero-inner">
          <div className="hero-copy">
            <span className="chip">Hyderabad · Civic Pulse</span>
            <h1 className="hero-title">{t("landing.headline")}</h1>
            <p className="lead">{t("landing.problem")}</p>
            <div className="cta-row">
              <Link to="/report" className="btn primary big cta">{t("landing.cta")} <span aria-hidden>→</span></Link>
              <Link to="/dashboard" className="link-arrow">{t("landing.dashboardLink")}</Link>
            </div>
          </div>
          <div className="hero-art" aria-hidden>
            <div className="ring r1" /><div className="ring r2" /><div className="ring r3" />
            <svg className="big-pin" viewBox="0 0 64 80" width="120" height="150">
              <defs><linearGradient id="pg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3b8cf0"/><stop offset="1" stop-color="#0f3f94"/></linearGradient></defs>
              <path d="M32 4C17 4 5 15.500 5 30c0 18 27 46 27 46s27-28 27-46C59 15.500 47 4 32 4z" fill="url(#pg)"/>
              <circle cx="32" cy="30" r="17" fill="#fff"/>
              <path className="beat" d="M19 31h8l3-8 5 16 3-8h7" fill="none" stroke="#1f5fbf" stroke-width="3.500" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <div className="float-card f1">🕳️ Pothole · High</div>
            <div className="float-card f2">✅ Acknowledged</div>
          </div>
        </div>
      </section>

      <section className="problem-grid">
        {[1, 2, 3].map((n, i) => (
          <Reveal key={n} delay={i * 120}>
            <div className="card pcard">
              <div className="icon-badge">{PROBLEM_ICONS[i]}</div>
              <h3>{t(`landing.p${n}t`)}</h3>
              <p className="muted">{t(`landing.p${n}d`)}</p>
            </div>
          </Reveal>
        ))}
      </section>

      <section>
        <Reveal><h2 className="section-title">{t("landing.howTitle")}</h2></Reveal>
        <div className="steps-grid">
          {[1, 2, 3, 4].map((n, i) => (
            <Reveal key={n} delay={i * 120}>
              <div className="card scard">
                <span className="step-num">{n}</span>
                <div className="step-icon">{STEP_ICONS[i]}</div>
                <p>{t(`landing.s${n}`)}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <Reveal>
        <section className="final-cta">
          <h2>{t("landing.finalTitle")}</h2>
          <Link to="/report" className="btn big cta-white">{t("landing.cta")} <span aria-hidden>→</span></Link>
        </section>
      </Reveal>
    </div>
  );
}
