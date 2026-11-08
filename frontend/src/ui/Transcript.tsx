import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { fps, timecode, type Clip } from "../model";
import { api, useEditor } from "../store";
import {
  assemblyFrame,
  assemblyRange,
  sourceFrame,
  type Word,
} from "../transcript";
import { forgetAnalysis, useAnalysis } from "./useAnalysis";

export function Transcript({ clip }: { clip: Clip }) {
  const { project, document, set } = useEditor();
  const rate = project ? fps(project.settings) : 30;
  const analysis = useAnalysis(clip.assetId);
  const [open, setOpen] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [correction, setCorrection] = useState("");
  const [saving, setSaving] = useState(false);
  const [anchor, setAnchor] = useState<Word | null>(null);
  useEffect(() => {
    setEditing(null);
    setOpen(null);
    setAnchor(null);
  }, [clip.id]);

  // Transcript selections drive the timeline range; times outside the clip are ignored.
  function select(startUs: number, endUs: number) {
    const range = assemblyRange(document, clip.id, startUs, endUs, rate);
    if (range) set({ range, rangeHandle: null, playing: false });
  }
  function selectText(root: HTMLElement) {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    const selected = selection.getRangeAt(0);
    const nodes = [...root.querySelectorAll<HTMLElement>("[data-word-start]")]
      .filter(node => selected.intersectsNode(node));
    if (nodes.length) select(Number(nodes[0].dataset.wordStart), Number(nodes.at(-1)!.dataset.wordEnd));
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

  async function saveWord() {
    if (!analysis?.words || editing === null || !clip.assetId || saving) return;
    setSaving(true);
    try {
      await api(`/analysis/${clip.assetId}/word`, {method:"PUT",body:JSON.stringify({index:editing,text:correction,expected:analysis.words[editing].text})});
      forgetAnalysis(clip.assetId); setEditing(null);
    } catch(e) { set({error:String(e)}); } finally { setSaving(false); }
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
    <div className="inspector-content transcript-panel" style={{userSelect:"text"}}
      onMouseUp={e => { const root=e.currentTarget; setTimeout(() => selectText(root), 0); }}
      onKeyUp={e => selectText(e.currentTarget)}>
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
                                    editing === words.indexOf(w) ? <input key={j} aria-label="Correct transcript word" autoFocus value={correction} disabled={saving}
                                      onChange={e=>setCorrection(e.target.value)} onBlur={()=>void saveWord()}
                                      onKeyDown={e=>{if(e.key==="Enter") void saveWord();if(e.key==="Escape") {e.preventDefault();e.stopPropagation();setEditing(null);}}} /> : <span
                                      key={j}
                                      data-word-start={w.startUs}
                                      data-word-end={w.endUs}
                                      style={{userSelect:"text"}}
                                      className={`word ${anchor === w ? "anchor" : ""}`}
                                      title="Click: set the range to this word. Shift+click: extend it."
                                      onDoubleClick={e=>{e.stopPropagation();setEditing(words.indexOf(w));setCorrection(w.text);}}
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
            then use Trim clip to range, Delete or Ripple below the flow.
          </p>
        </div>
      )}
    </div>
  );
}
