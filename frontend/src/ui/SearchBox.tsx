// Search of what is said in the edit (docs/features/editing/text-search.md).
import { useEffect, useMemo, useRef } from "react";
import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { fps } from "../model";
import { useEditor } from "../store";
import { TIMELINE_ORIGIN, useTimeline } from "../timeline";
import { nextHit, searchHits, terms, useSearch, type Hit } from "../search";
import { useAnalyses } from "./useAnalysis";

// Put the cursor on an occurrence and scroll the timeline to it.
function goTo(hit: Hit) {
  const s = useEditor.getState();
  s.set({
    frame: hit.frame,
    playing: false,
    focus: s.focus && s.focus !== hit.clipId ? null : s.focus,
  });
  const t = useTimeline.getState(),
    x = hit.frame * t.scale,
    visible = t.width - TIMELINE_ORIGIN;
  if (x < t.scroll || x > t.scroll + visible - 24)
    t.set({ scroll: Math.max(0, x - visible / 3) });
}

export function SearchBox() {
  const project = useEditor((s) => s.project),
    document = useEditor((s) => s.document),
    frame = useEditor((s) => s.frame);
  const { query, hits, set } = useSearch();
  const input = useRef<HTMLInputElement>(null);
  const sources = useMemo(
    () => [
      ...new Set(
        document.clips
          .filter(
            (c) => (c.kind === "video" || c.kind === "audio") && c.assetId,
          )
          .filter(
            (c) =>
              !project?.assets.find((a) => a.id === c.assetId)?.probe.still,
          )
          .map((c) => c.assetId!),
      ),
    ],
    [document, project?.assets],
  );
  const analyses = useAnalyses(sources);
  const rate = project ? fps(project.settings) : 30;
  useEffect(() => {
    set({ hits: searchHits(document, analyses, query, rate) });
  }, [document, analyses, query, rate, set]);
  // Ctrl+F focuses the box (the editor's key handler skips text fields).
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  const move = (back: boolean) => {
    const hit = nextHit(hits, frame, back);
    if (hit) goTo(hit);
  };
  const current = hits.findIndex((h) => h.frame === frame);
  const active = terms(query).length > 0;
  return (
    <div className={`search-box ${active ? "active" : ""}`} role="search">
      <Search size={14} aria-hidden />
      <input
        ref={input}
        aria-label="Search what is said"
        placeholder="Search what is said"
        title="Search the transcripts of the clips (Ctrl+F); Enter goes to the next occurrence"
        value={query}
        onChange={(e) => set({ query: e.target.value })}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            move(e.shiftKey);
          } else if (e.key === "Escape") {
            e.preventDefault();
            if (query) set({ query: "" });
            else input.current?.blur();
          }
        }}
      />
      {active && (
        <>
          <span className="search-count" aria-live="polite">
            {hits.length
              ? `${current >= 0 ? current + 1 : "–"} / ${hits.length}`
              : "No match"}
          </span>
          <button
            className="search-step"
            aria-label="Previous occurrence"
            title="Previous occurrence (Shift+Enter)"
            disabled={!hits.length}
            onClick={() => move(true)}
          >
            <ChevronUp size={14} />
          </button>
          <button
            className="search-step"
            aria-label="Next occurrence"
            title="Next occurrence (Enter)"
            disabled={!hits.length}
            onClick={() => move(false)}
          >
            <ChevronDown size={14} />
          </button>
          <button
            className="search-step"
            aria-label="Clear search"
            title="Clear search (Escape)"
            onClick={() => {
              set({ query: "" });
              input.current?.focus();
            }}
          >
            <X size={14} />
          </button>
        </>
      )}
    </div>
  );
}
