import { useEffect, useState } from "react";
import { api } from "../store";
import type { Analysis } from "../transcript";

const cache = new Map<string, Promise<Analysis | null>>();

function load(assetId: string): Promise<Analysis | null> {
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
  return cache.get(assetId)!;
}

// Analysis of one source; undefined while loading, null when there is none.
export function useAnalysis(assetId: string | null) {
  const [analysis, setAnalysis] = useState<Analysis | null | undefined>();
  useEffect(() => {
    setAnalysis(undefined);
    if (!assetId) return setAnalysis(null);
    let live = true;
    void load(assetId).then((a) => live && setAnalysis(a));
    return () => {
      live = false;
    };
  }, [assetId]);
  return analysis;
}

// Analyses for several sources at once, keyed by asset id (missing ids → null).
export function useAnalyses(assetIds: string[]) {
  const key = assetIds.join("|");
  const [result, setResult] = useState<Record<string, Analysis | null>>({});
  useEffect(() => {
    let live = true;
    void Promise.all(assetIds.map((id) => load(id))).then((list) => {
      if (live)
        setResult(Object.fromEntries(assetIds.map((id, i) => [id, list[i]])));
    });
    return () => {
      live = false;
    };
    // The joined key captures the id list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return result;
}
