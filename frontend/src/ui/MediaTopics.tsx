import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAnalysis } from "./useAnalysis";
export function MediaTopics({ assetId }: { assetId: string }) {
  const marker = useRef<HTMLSpanElement>(null);
  const [position, setPosition] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const analysis = useAnalysis(position ? assetId : null);
  useEffect(() => {
    const card = marker.current?.parentElement;
    if (!card) return;
    let timer: ReturnType<typeof setTimeout>;
    const leave = () => {
      clearTimeout(timer);
      setPosition(null);
    };
    const enter = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const r = card.getBoundingClientRect();
        setPosition({
          left: Math.min(window.innerWidth - 310, r.right + 8),
          top: Math.max(8, Math.min(window.innerHeight - 240, r.top)),
        });
      }, 2000);
    };
    card.addEventListener("mouseenter", enter);
    card.addEventListener("mouseleave", leave);
    card.addEventListener("dragstart", leave);
    window.addEventListener("scroll", leave, true);
    return () => {
      leave();
      card.removeEventListener("mouseenter", enter);
      card.removeEventListener("mouseleave", leave);
      card.removeEventListener("dragstart", leave);
      window.removeEventListener("scroll", leave, true);
    };
  }, [assetId]);
  return (
    <>
      <span ref={marker} />
      {position && analysis?.words?.length && analysis.topics?.length
        ? createPortal(
            <div
              role="tooltip"
              style={{
                position: "fixed",
                ...position,
                zIndex: 10000,
                width: 290,
                maxHeight: 230,
                overflow: "auto",
                pointerEvents: "none",
                background: "var(--paper, white)",
                color: "var(--ink, #243e31)",
                padding: 14,
                border: "1px solid #ccd8cb",
                borderRadius: 8,
                boxShadow: "0 8px 24px #0002",
              }}
            >
              <strong>Transcribed topics</strong>
              <ul>
                {analysis.topics.map((topic, i) => (
                  <li key={i}>{topic.title}</li>
                ))}
              </ul>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
