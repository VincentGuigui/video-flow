import { useEffect, useState } from "react";
import { FolderOpen, Trash2 } from "lucide-react";
import { api, useEditor } from "../store";

interface CacheProject {
  id: string;
  name: string;
  path: string;
  size: number;
  current: boolean;
}
interface CacheUsage {
  root: string;
  size: number;
  projects: CacheProject[];
}

export const formatSize = (bytes: number) =>
  bytes < 1024 ** 2
    ? `${Math.round(bytes / 1024)} KB`
    : bytes < 1024 ** 3
      ? `${(bytes / 1024 ** 2).toFixed(1)} MB`
      : `${(bytes / 1024 ** 3).toFixed(2)} GB`;

// The application cache: one rebuildable folder per project (proxies, thumbnails, waveforms).
export function CacheSettings() {
  const { set } = useEditor();
  const [usage, setUsage] = useState<CacheUsage | null>(null),
    [busy, setBusy] = useState(false);
  const refresh = () =>
    api<CacheUsage>("/cache")
      .then(setUsage)
      .catch((e) => set({ error: String(e) }));
  useEffect(() => {
    void refresh();
  }, []);
  async function clear() {
    setBusy(true);
    try {
      const { failed } = await api<{ failed: string[] }>("/cache/clear", {
        method: "POST",
      });
      if (failed.length)
        set({
          error: `Some cache files are in use and were kept (${failed.length}).`,
        });
      await refresh();
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="settings-cache">
      <p>
        Cache size: <strong>{usage ? formatSize(usage.size) : "…"}</strong>
        <span className="muted">
          {" "}
          · proxies, thumbnails and waveforms, rebuilt when needed
        </span>
      </p>
      <ul className="cache-projects">
        {usage?.projects.map((p) => (
          <li key={p.id} title={p.path}>
            <span>
              {p.name}
              {p.current && <small> · open</small>}
            </span>
            <span className="muted">{formatSize(p.size)}</span>
          </li>
        ))}
      </ul>
      <div className="cache-actions">
        <button
          className="button"
          onClick={() =>
            void api("/cache/open", { method: "POST" }).catch((e) =>
              set({ error: String(e) }),
            )
          }
        >
          <FolderOpen size={15} />
          Open cache folder
        </button>
        <button
          className="button"
          disabled={busy || !usage?.size}
          onClick={() => void clear()}
        >
          <Trash2 size={15} />
          Clear cache
        </button>
      </div>
    </div>
  );
}
