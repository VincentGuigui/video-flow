import { useEffect, useState } from "react";
import { api } from "../store";
import { duration, type Clip } from "../model";
interface Peaks {
  pps: number;
  rms: number[];
}
const cache = new Map<string, Promise<Peaks>>();
export function Waveform({ clip, rate }: { clip: Clip; rate: number }) {
  const [peaks, setPeaks] = useState<Peaks | null>(null);
  useEffect(() => {
    if (!clip.assetId) return;
    let mounted = true;
    const id = clip.assetId;
    let request = cache.get(id);
    if (!request) {
      request = api<Peaks>("/waveform/" + id);
      cache.set(id, request);
    }
    request
      .then((result) => {
        if (mounted) setPeaks(result);
      })
      .catch(() => {
        cache.delete(id);
      });
    return () => {
      mounted = false;
    };
  }, [clip.assetId]);
  const values = Array.from({ length: 80 }, (_, i) => {
    if (!peaks) return 0;
    const index = Math.floor(
      ((clip.sourceIn + (duration(clip) * i) / 80) / rate) * peaks.pps,
    );
    return Math.min(1, Math.sqrt(peaks.rms[index] ?? 0));
  });
  return (
    <svg
      className="audio-wave"
      viewBox="0 0 400 20"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {values.map((v, i) => (
        <line
          key={i}
          x1={i * 5}
          x2={i * 5}
          y1={10 - Math.max(0.3, v * 10)}
          y2={10 + Math.max(0.3, v * 10)}
          stroke="currentColor"
          strokeWidth="2"
        />
      ))}
    </svg>
  );
}
