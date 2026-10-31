/** Offline upload queue (FR-4): reports submitted without a connection are kept in IndexedDB and
 *  uploaded automatically when the network returns. Nothing is lost if the tab is closed. */
import { del, get, keys, set } from "idb-keyval";
import { ApiError, NetworkError, postForm, rememberRef, type Report } from "./api";

const PREFIX = "cp_queue_";

export interface QueuedReport {
  id: string;
  fields: Record<string, string>;
  files: { name: string; field: string; blob: Blob }[];
  queuedAt: number;
}

export function buildForm(q: Pick<QueuedReport, "fields" | "files">): FormData {
  const fd = new FormData();
  Object.entries(q.fields).forEach(([k, v]) => fd.append(k, v));
  q.files.forEach((f) => fd.append(f.field, f.blob, f.name));
  return fd;
}

export async function enqueue(q: Omit<QueuedReport, "id" | "queuedAt">): Promise<string> {
  const id = crypto.randomUUID();
  await set(PREFIX + id, { ...q, id, queuedAt: Date.now() } satisfies QueuedReport);
  return id;
}

export async function pendingCount(): Promise<number> {
  return (await keys()).filter((k) => String(k).startsWith(PREFIX)).length;
}

/** Try to upload every queued report. Returns refs of reports that were created. */
export async function flushQueue(): Promise<Report[]> {
  const done: Report[] = [];
  for (const key of await keys()) {
    if (!String(key).startsWith(PREFIX)) continue;
    const q = (await get(key)) as QueuedReport | undefined;
    if (!q) continue;
    try {
      const report = await postForm<Report>("/api/reports/", buildForm(q));
      rememberRef(report.ref_no);
      await del(key);
      done.push(report);
    } catch (e) {
      if (e instanceof NetworkError) break; // still offline: keep everything, try again later
      if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 429) {
        await del(key); // permanently invalid: do not retry forever
      } else {
        break;
      }
    }
  }
  return done;
}

export function startAutoFlush(onUploaded: (r: Report[]) => void) {
  const run = () => flushQueue().then((r) => r.length && onUploaded(r));
  window.addEventListener("online", run);
  run();
  return () => window.removeEventListener("online", run);
}
