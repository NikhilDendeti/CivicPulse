import { useTranslation } from "react-i18next";
import type { TimelineEvent } from "../lib/api";

export default function Timeline({ events }: { events: TimelineEvent[] }) {
  const { t } = useTranslation();
  return (
    <ol className="timeline">
      {events.map((e, i) => (
        <li key={i}>
          <div className="tl-head">
            <b>{t(`status.${e.status}`, e.status)}</b>
            <small className="muted"> {new Date(e.at).toLocaleString()} · {e.actor}</small>
          </div>
          {e.note && <div className="tl-note">{e.note}</div>}
          {e.proof_url && <img className="proof" src={e.proof_url} alt="Proof of resolution" />}
        </li>
      ))}
    </ol>
  );
}
