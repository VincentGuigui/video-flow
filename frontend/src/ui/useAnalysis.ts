import { useEffect, useState } from "react";
import { api } from "../store";
import type { Analysis } from "../transcript";

const cache = new Map<string, Promise<Analysis | null>>();

// Analysis of one source; undefined while loading, null when there is none.
export function useAnalysis(assetId: string | null) {
  const [analysis, setAnalysis] = useState<Analysis | null | undefined>();
  useEffect(() => {
    setAnalysis(undefined);
    if (!assetId) return setAnalysis(null);
    let live = true;
    if (!cache.has(assetId))
      cache.set(
        assetId,
        // Missing analysis is not cached: a re-import may add it later.
        api<Analysis | null>(`/analysis/${assetId}`)
          .catch(() => null)
          .then((a) => {
            if (!a) cache.delete(assetId);
            return a;
          }),
      );
    void cache.get(assetId)!.then((a) => live && setAnalysis(a));
    return () => {
      live = false;
    };
  }, [assetId]);
  return analysis;
}
