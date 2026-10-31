import imageCompression from "browser-image-compression";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import MapPicker, { HYDERABAD } from "../components/MapPicker";
import VoiceRecorder, { type Voice } from "../components/VoiceRecorder";
import { ApiError, deviceToken, get, NetworkError, postForm, rememberRef, type Meta, type Report } from "../lib/api";
import { buildForm, enqueue, pendingCount } from "../lib/offlineQueue";

export default function ReportPage({ pending, onQueued }: { pending: number; onQueued: () => void }) {
  const { t, i18n } = useTranslation();
  const nav = useNavigate();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [voice, setVoice] = useState<Voice | null>(null);
  const [text, setText] = useState("");
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [pos, setPos] = useState<[number, number]>(HYDERABAD);
  const [located, setLocated] = useState<"pending" | "ok" | "denied">("pending");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [queuedMsg, setQueuedMsg] = useState(false);

  useEffect(() => {
    get<Meta>("/api/meta/").then(setMeta).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!navigator.geolocation) return setLocated("denied");
    const id = navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos([p.coords.latitude, p.coords.longitude]);
        setAccuracy(Math.round(p.coords.accuracy));
        setLocated("ok");
      },
      () => setLocated("denied"),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 },
    );
    return () => void id;
  }, []);

  useEffect(() => {
    if (!photo) return setPreview("");
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  const onMove = useCallback((p: [number, number]) => {
    setPos(p);
    setAccuracy(null);
    setLocated("ok");
  }, []);

  async function submit() {
    setError("");
    if (!photo && !voice && !text.trim()) return setError(t("report.needEvidence"));
    if (!consent) return setError(t("report.needConsent"));
    setBusy(true);
    try {
      const files: { name: string; field: string; blob: Blob }[] = [];
      if (photo) {
        // Compress on the device so uploads work on 3G (FR-4).
        const small = await imageCompression(photo, { maxSizeMB: 0.8, maxWidthOrHeight: 1600, useWebWorker: true }).catch(() => photo);
        files.push({ field: "image", name: "photo.jpg", blob: small });
      }
      if (voice) files.push({ field: "audio", name: voice.name, blob: voice.blob });
      const fields: Record<string, string> = {
        lat: String(pos[0]),
        lng: String(pos[1]),
        text,
        consent: "true",
        lang: i18n.language,
        device_token: deviceToken(),
        email,
      };
      if (accuracy) fields.accuracy = String(accuracy);

      try {
        const report = await postForm<Report>("/api/reports/", buildForm({ fields, files }));
        rememberRef(report.ref_no);
        nav(`/r/${report.ref_no}`);
      } catch (e) {
        if (e instanceof NetworkError) {
          await enqueue({ fields, files });
          await pendingCount();
          onQueued();
          setQueuedMsg(true);
        } else {
          throw e;
        }
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <h1>{t("report.title")}</h1>
      <p className="muted">{t("app.tagline")}</p>
      {pending > 0 && <div className="notice">{t("report.pending", { n: pending })}</div>}

      <section className="card stack">
        <label className="btn secondary file">
          📷 {photo ? t("report.photoChange") : t("report.photo")}
          <input type="file" accept="image/*" capture="environment" hidden onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
        </label>
        {preview && <img className="preview" src={preview} alt="Selected evidence" />}
        <VoiceRecorder maxSeconds={meta?.max_audio_seconds ?? 30} value={voice} onChange={setVoice} />
        <label className="stack">
          <span>{t("report.text")}</span>
          <textarea rows={3} value={text} maxLength={1500} placeholder={t("report.textPlaceholder")} onChange={(e) => setText(e.target.value)} />
        </label>
      </section>

      <section className="card stack">
        <b>{t("report.location")}</b>
        {located === "pending" && <small className="muted">{t("report.locating")}</small>}
        {located === "denied" && <small className="err">{t("report.locDenied")}</small>}
        {located === "ok" && accuracy && <small className="muted">{t("report.locAccuracy", { m: accuracy })}</small>}
        <MapPicker value={pos} onChange={onMove} />
      </section>

      <section className="card stack">
        <label className="stack">
          <span>{t("report.email")}</span>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label className="check">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>{t("report.consent")}</span>
        </label>
        {error && <div className="err" role="alert">{error}</div>}
        {queuedMsg && <div className="notice">{t("report.queued")}</div>}
        <button className="btn primary big" disabled={busy} onClick={submit}>
          {busy ? t("report.submitting") : t("report.submit")}
        </button>
      </section>
    </div>
  );
}
