import { useEffect, useRef, useState } from "react";
import { Check, Pause, Play, Volume2, VolumeX, X } from "lucide-react";
import {
  anchor,
  divergent,
  pickTake,
  stackedTakes,
  takeWords,
} from "../compare";
import { mediaUrl } from "../desktop";
import { duration, fps, timecode } from "../model";
import { useEditor } from "../store";
import { useAnalyses } from "./useAnalysis";

// Seconds of context played before the common word.
const PREROLL = 0.5;

export function Compare({ clipId }: { clipId: string }) {
  const { project, document, save, busy, set } = useEditor();
  const rate = project ? fps(project.settings) : 30;
  const takes = stackedTakes(document, clipId);
  const analyses = useAnalyses(takes.map((t) => t.assetId ?? ""));
  const words = takes.map((t) =>
    takeWords(t, analyses[t.assetId ?? ""]?.words ?? [], rate),
  );
  const reference = Math.max(
    0,
    takes.findIndex((t) => t.enabled),
  );
  const common = anchor(words, reference);
  const different = divergent(words);
  const players = useRef<(HTMLVideoElement | null)[]>([]);
  const [solo, setSolo] = useState(reference);
  const [playing, setPlaying] = useState(false);
  const close = () => set({ compare: null });

  function start(index: number) {
    const take = takes[index];
    return common
      ? Math.max(
          take.sourceIn / rate,
          common.times[index] / 1_000_000 - PREROLL,
        )
      : take.sourceIn / rate;
  }
  function playAll() {
    if (playing) {
      players.current.forEach((p) => p?.pause());
      return setPlaying(false);
    }
    players.current.forEach((p, i) => {
      if (!p) return;
      p.currentTime = start(i);
      void p.play().catch(() => undefined);
    });
    setPlaying(true);
  }
  function pick(index: number) {
    const take = takes[index];
    if (!take || busy) return;
    void save(pickTake(document, takes, take.id));
  }

  useEffect(() => {
    function keys(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.code === "Space") {
        e.preventDefault();
        playAll();
      } else if (/^[1-9]$/.test(e.key)) {
        e.preventDefault();
        pick(Number(e.key) - 1);
      }
    }
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  });
  // Stop each player at the end of its trimmed range.
  function bound(index: number) {
    const p = players.current[index],
      take = takes[index];
    if (p && take && p.currentTime >= take.sourceOut / rate) p.pause();
  }

  return (
    <div className="modal-backdrop compare-backdrop">
      <section
        className="modal compare-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Compare takes"
      >
        <div className="modal-heading">
          <h2>Compare takes · {takes.length}</h2>
          <button aria-label="Close compare" onClick={close}>
            <X size={20} />
          </button>
        </div>
        <div className="compare-bar">
          <button className="button" onClick={playAll}>
            {playing ? <Pause size={14} /> : <Play size={14} />}
            {playing ? "Pause all" : "Play all"}
          </button>
          <span className="muted">
            {common
              ? `Synced on «${common.word}»`
              : "No common word: playing from each take's start"}
            {" · "}Space play/pause · 1–{Math.min(9, takes.length)} pick · Esc
            close
          </span>
        </div>
        <div className="compare-grid">
          {takes.map((take, index) => (
            <article
              key={take.id}
              className={`compare-take ${take.enabled ? "picked" : ""}`}
              data-testid="compare-take"
            >
              <header>
                <strong>
                  {index + 1} · {take.name}
                </strong>
                <span className="muted">{timecode(duration(take), rate)}</span>
              </header>
              <video
                ref={(node) => {
                  players.current[index] = node;
                }}
                src={mediaUrl(take.assetId)}
                muted={solo !== index}
                preload="auto"
                onLoadedMetadata={(e) => {
                  e.currentTarget.currentTime = start(index);
                }}
                onTimeUpdate={() => bound(index)}
                onEnded={() => setPlaying(false)}
              />
              <p className="compare-words">
                {words[index].length ? (
                  words[index].map((w, j) => (
                    <span
                      key={j}
                      className={[
                        different[index][j] ? "diff" : "",
                        common && w.startUs === common.times[index]
                          ? "anchor"
                          : "",
                      ].join(" ")}
                    >
                      {w.text}{" "}
                    </span>
                  ))
                ) : (
                  <span className="muted">No transcript</span>
                )}
              </p>
              <footer>
                <button
                  className="icon-button"
                  aria-label={
                    solo === index ? "Audio solo" : "Listen to this take"
                  }
                  title="Listen to this take"
                  onClick={() => setSolo(index)}
                >
                  {solo === index ? (
                    <Volume2 size={15} />
                  ) : (
                    <VolumeX size={15} />
                  )}
                </button>
                <button
                  className="button pick-action"
                  disabled={busy}
                  onClick={() => pick(index)}
                >
                  {take.enabled ? <Check size={14} /> : null}
                  {take.enabled ? "Picked" : "Pick"} <kbd>{index + 1}</kbd>
                </button>
              </footer>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
