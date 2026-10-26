import { clone, type Transform } from "./model";

export function snapHandle(
  original: Transform,
  draft: Transform,
  handle: string,
  mode: "scale" | "crop",
  width: number,
  height: number,
  threshold: number,
  stretch: boolean,
  symmetric: boolean,
) {
  const next = clone(draft);
  const sides = [
    {
      active: handle.includes("w"),
      axis: "x",
      side: "w",
      value: next.x + next.width * next.cropLeft,
      target: 0,
    },
    {
      active: handle.includes("e"),
      axis: "x",
      side: "e",
      value: next.x + next.width * (1 - next.cropRight),
      target: width,
    },
    {
      active: handle.includes("n"),
      axis: "y",
      side: "n",
      value: next.y + next.height * next.cropTop,
      target: 0,
    },
    {
      active: handle.includes("s"),
      axis: "y",
      side: "s",
      value: next.y + next.height * (1 - next.cropBottom),
      target: height,
    },
  ]
    .filter((s) => s.active && Math.abs(s.value - s.target) <= threshold)
    .sort(
      (a, b) => Math.abs(a.value - a.target) - Math.abs(b.value - b.target),
    );
  const side = sides[0];
  if (!side) return { transform: next, x: [] as number[], y: [] as number[] };
  if (mode === "crop") {
    const ratio =
      (original.width * (1 - original.cropLeft - original.cropRight)) /
      (original.height * (1 - original.cropTop - original.cropBottom));
    const clamp = (n: number) => Math.max(0, Math.min(0.98, n));
    if (side.axis === "x") {
      if (side.side === "w") {
        next.cropLeft = clamp((side.target - next.x) / next.width);
        if (symmetric) next.cropRight = next.cropLeft;
      } else {
        next.cropRight = clamp(1 - (side.target - next.x) / next.width);
        if (symmetric) next.cropLeft = next.cropRight;
      }
      if (!stretch) {
        const crop =
          1 -
          (next.width * (1 - next.cropLeft - next.cropRight)) /
            ratio /
            next.height;
        next.cropTop = (crop + original.cropTop - original.cropBottom) / 2;
        next.cropBottom = crop - next.cropTop;
      }
    } else {
      if (side.side === "n") {
        next.cropTop = clamp((side.target - next.y) / next.height);
        if (symmetric) next.cropBottom = next.cropTop;
      } else {
        next.cropBottom = clamp(1 - (side.target - next.y) / next.height);
        if (symmetric) next.cropTop = next.cropBottom;
      }
      if (!stretch) {
        const crop =
          1 -
          (next.height * (1 - next.cropTop - next.cropBottom) * ratio) /
            next.width;
        next.cropLeft = (crop + original.cropLeft - original.cropRight) / 2;
        next.cropRight = crop - next.cropLeft;
      }
    }
    if (
      [next.cropLeft, next.cropRight, next.cropTop, next.cropBottom].some(
        (c) => c < 0,
      ) ||
      next.cropLeft + next.cropRight >= 0.98 ||
      next.cropTop + next.cropBottom >= 0.98
    )
      return { transform: draft, x: [], y: [] };
  } else {
    if (side.axis === "x") {
      const anchor = symmetric
        ? original.x + original.width / 2
        : handle.includes("w")
          ? original.x + original.width
          : original.x;
      const coefficient =
        side.side === "w"
          ? symmetric
            ? next.cropLeft - 0.5
            : next.cropLeft - 1
          : symmetric
            ? 0.5 - next.cropRight
            : 1 - next.cropRight;
      if (Math.abs(coefficient) < 1e-6)
        return { transform: draft, x: [], y: [] };
      next.width = (side.target - anchor) / coefficient;
      if (!stretch)
        next.height = (next.width * original.height) / original.width;
    } else {
      const anchor = symmetric
        ? original.y + original.height / 2
        : handle.includes("n")
          ? original.y + original.height
          : original.y;
      const coefficient =
        side.side === "n"
          ? symmetric
            ? next.cropTop - 0.5
            : next.cropTop - 1
          : symmetric
            ? 0.5 - next.cropBottom
            : 1 - next.cropBottom;
      if (Math.abs(coefficient) < 1e-6)
        return { transform: draft, x: [], y: [] };
      next.height = (side.target - anchor) / coefficient;
      if (!stretch)
        next.width = (next.height * original.width) / original.height;
    }
    if (
      !Number.isFinite(next.width) ||
      !Number.isFinite(next.height) ||
      next.width < 32 ||
      next.height < 32
    )
      return { transform: draft, x: [], y: [] };
    next.x = symmetric
      ? original.x + (original.width - next.width) / 2
      : handle.includes("w")
        ? original.x + original.width - next.width
        : original.x;
    next.y = symmetric
      ? original.y + (original.height - next.height) / 2
      : handle.includes("n")
        ? original.y + original.height - next.height
        : original.y;
  }
  return {
    transform: next,
    x: [
      ...(Math.abs(next.x + next.width * next.cropLeft) < 0.01 ? [0] : []),
      ...(Math.abs(next.x + next.width * (1 - next.cropRight) - width) < 0.01
        ? [width]
        : []),
    ],
    y: [
      ...(Math.abs(next.y + next.height * next.cropTop) < 0.01 ? [0] : []),
      ...(Math.abs(next.y + next.height * (1 - next.cropBottom) - height) < 0.01
        ? [height]
        : []),
    ],
  };
}
