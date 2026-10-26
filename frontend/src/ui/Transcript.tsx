import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { fps, timecode, type Clip } from "../model";
import { useEditor } from "../store";
import {
  assemblyFrame,
  assemblyRange,
  sourceFrame,
  type Word,
} from "../transcript";
import { useAnalysis } from "./useAnalysis";

export function Transcript({ clip }: { clip: Clip }) {
  const { project, document, set } = useEditor();
  const rate = project ? fps(project.settings) : 30;
  const analysis = useAnalysis(clip.assetId);
  const [open, setOpen] = useState<number | null>(null);
  const [anchor, setAnchor] = useState<Word | null>(null);
  useEffect(() => {
    setOpen(null);
    setAnchor(null);
  }, [clip.id]);

  // Transcript selections drive the timeline range; times outside the clip are ignored.
  function select(startUs: number, endUs: number) {
    const range = assemblyRange(document, clip.id, startUs, endUs, rate);
    if (range) set({ range, rangeHandle: null, playing: false });
  }
  function pickWord(word: Word, extend: boolean) {
    if (extend && anchor) {
      select(
        Math.min(anchor.startUs, word.startUs),
        Math.max(anchor.endUs, word.endUs),
      );
    } else {
      setAnchor(word);
      select(word.startUs, word.endUs);
    }
  }

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
  const topics = analysis.topics ?? [],
    words = analysis.words ?? [];
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
                      if (expanded) set({ range: null, rangeHandle: null });
                      else select(topic.startUs, topic.endUs);
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
                      {topic.sentences.map((line, i) => {
                        const spoken = words.filter(
                          (w) =>
                            w.startUs >= line.startUs && w.endUs <= line.endUs,
                        );
                        return (
                          <li key={i}>
                            <Time us={line.startUs} />
                            <span>
                              {spoken.length
                                ? spoken.map((w, j) => (
                                    <span
                                      key={j}
                                      className={`word ${anchor === w ? "anchor" : ""}`}
                                      title="Click: set the range to this word. Shift+click: extend it."
                                      onClick={(e) => pickWord(w, e.shiftKey)}
                                    >
                                      {w.text}{" "}
                                    </span>
                                  ))
                                : line.text}
                            </span>
                          </li>
                        );
                      })}
                    </ol>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="muted transcript-hint">
            Click a word to set the timeline range, Shift+click to extend it,
            then use Trim clip to range in the Clip tab.
          </p>
        </div>
      )}
    </div>
  );
}
