import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { fps, timecode, type Clip } from "../model";
import { api, useEditor } from "../store";
import {
  assemblyFrame,
  assemblyRange,
  sourceFrame,
  type Analysis,
} from "../transcript";

export function Transcript({ clip }: { clip: Clip }) {
  const { project, document, set } = useEditor();
  const rate = project ? fps(project.settings) : 30;
  const [analysis, setAnalysis] = useState<Analysis | null | undefined>();
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => {
    setAnalysis(undefined);
    setOpen(null);
    if (!clip.assetId) return setAnalysis(null);
    let live = true;
    api<Analysis | null>(`/analysis/${clip.assetId}`)
      .then((a) => live && setAnalysis(a))
      .catch(() => live && setAnalysis(null));
    return () => {
      live = false;
    };
  }, [clip.assetId]);
  // The highlight belongs to this panel; leave nothing behind on clip change.
  useEffect(() => () => set({ highlight: null }), [clip.id]);

  function Time({ us }: { us: number }) {
    const frame = assemblyFrame(document, clip.id, us, rate);
    return frame === null ? (
      <span
        className="timecode outside"
        title="Outside the clip's trimmed range"
      >
        {timecode(sourceFrame(us, rate), rate)}
      </span>
    ) : (
      <button
        className="timecode"
        title="Move the cursor here"
        onClick={(e) => {
          e.stopPropagation();
          set({ frame, playing: false });
        }}
      >
        {timecode(frame, rate)}
      </button>
    );
  }

  if (analysis === undefined)
    return <div className="inspector-content muted">Loading transcript…</div>;
  if (!analysis)
    return (
      <div className="inspector-content transcript-panel">
        <p className="muted">
          No analysis for this media. Import it again with analysis to get a
          transcript, summary and topics.
        </p>
      </div>
    );
  const topics = analysis.topics ?? [];
  return (
    <div className="inspector-content transcript-panel">
      <span className="overline">SUMMARY</span>
      <p className="transcript-summary">
        {analysis.summary || "No speech detected."}
      </p>
      {topics.length > 0 && (
        <div className="inspector-section">
          <span className="overline">TOPICS</span>
          <ul className="topics">
            {topics.map((topic, index) => {
              const expanded = open === index;
              return (
                <li key={index} className={expanded ? "expanded" : ""}>
                  <div
                    className="topic-head"
                    role="button"
                    tabIndex={0}
                    aria-expanded={expanded}
                    onClick={() => {
                      setOpen(expanded ? null : index);
                      set({
                        highlight: expanded
                          ? null
                          : assemblyRange(
                              document,
                              clip.id,
                              topic.startUs,
                              topic.endUs,
                              rate,
                            ),
                      });
                    }}
                  >
                    {expanded ? (
                      <ChevronDown size={13} />
                    ) : (
                      <ChevronRight size={13} />
                    )}
                    <span className="topic-times">
                      <Time us={topic.startUs} />
                      <span>–</span>
                      <Time us={topic.endUs} />
                    </span>
                    <strong>{topic.title}</strong>
                  </div>
                  {expanded && (
                    <ol className="topic-lines">
                      {topic.sentences.map((line, i) => (
                        <li key={i}>
                          <Time us={line.startUs} />
                          <span>{line.text}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
