import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export interface Voice {
  blob: Blob;
  name: string;
  url: string;
}

function pickMime(): { mime: string; ext: string } {
  const options: [string, string][] = [
    ["audio/webm;codecs=opus", "webm"],
    ["audio/webm", "webm"],
    ["audio/ogg;codecs=opus", "ogg"],
    ["audio/mp4", "m4a"],
  ];
  for (const [mime, ext] of options) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mime)) return { mime, ext };
  }
  return { mime: "", ext: "webm" };
}

export default function VoiceRecorder({ maxSeconds, value, onChange }: { maxSeconds: number; value: Voice | null; onChange: (v: Voice | null) => void }) {
  const { t } = useTranslation();
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [denied, setDenied] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(timer.current), []);

  async function start() {
    setDenied(false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const { mime, ext } = pickMime();
      const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        const blob = new Blob(chunks, { type: mr.mimeType || mime || "audio/webm" });
        onChange({ blob, name: `voice.${ext}`, url: URL.createObjectURL(blob) });
        setRecording(false);
        window.clearInterval(timer.current);
      };
      rec.current = mr;
      mr.start();
      setRecording(true);
      setElapsed(0);
      const startedAt = Date.now();
      timer.current = window.setInterval(() => {
        const s = Math.floor((Date.now() - startedAt) / 1000);
        setElapsed(s);
        if (s >= maxSeconds) mr.stop();
      }, 250);
    } catch {
      setDenied(true);
    }
  }

  return (
    <div className="stack">
      {value ? (
        <div className="row">
          <audio controls src={value.url} />
          <button type="button" className="btn ghost" onClick={() => onChange(null)}>
            {t("report.voiceRemove")}
          </button>
        </div>
      ) : (
        <button type="button" className={`btn ${recording ? "danger" : "secondary"}`} onClick={recording ? () => rec.current?.stop() : start}>
          {recording ? `${t("report.voiceStop")} (${elapsed}s)` : `🎤 ${t("report.voice")}`}
        </button>
      )}
      <small className="muted">{t("report.voiceHint", { s: maxSeconds })}</small>
      {denied && <small className="err">{t("report.micDenied")}</small>}
    </div>
  );
}
