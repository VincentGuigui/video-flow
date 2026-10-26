import { create } from "zustand";
import { useEffect, type RefObject } from "react";
import { zoomAt } from "./model";

export const TIMELINE_ORIGIN = 56;
interface Timeline {
  scale: number;
  scroll: number;
  width: number;
  fitting: boolean;
  set: (values: Partial<Timeline>) => void;
}
export const useTimeline = create<Timeline>((set) => ({
  scale: 2,
  scroll: 0,
  width: 1000,
  fitting: true,
  set,
}));
export function zoomTimeline(next: number, pointer: number) {
  const state = useTimeline.getState();
  next = Math.max(0.001, Math.min(4096, next));
  state.set({
    scale: next,
    scroll: Math.max(
      0,
      zoomAt(state.scale, next, state.scroll, pointer - TIMELINE_ORIGIN),
    ),
    fitting: false,
  });
}
export function useTimelineWheel(ref: RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey) {
        event.preventDefault();
        zoomTimeline(
          useTimeline.getState().scale * Math.exp(-event.deltaY * 0.002),
          event.clientX - node.getBoundingClientRect().left,
        );
      } else if (event.shiftKey) {
        event.preventDefault();
        useTimeline.getState().set({
          scroll: Math.max(0, node.scrollLeft + (event.deltaY || event.deltaX)),
        });
      }
    };
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, [ref]);
}
