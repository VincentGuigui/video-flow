import { expect, it } from "vitest";
import { defaultTransform } from "./model";
import { snapHandle } from "./snap";

const original = {
  ...defaultTransform(),
  x: 100,
  y: 100,
  width: 100,
  height: 50,
};
it("snaps scale handles on all four viewport edges without stretching", () => {
  const right = snapHandle(
    original,
    { ...original, width: 198, height: 99 },
    "e",
    "scale",
    300,
    200,
    8,
    false,
    false,
  );
  expect(right.transform.x + right.transform.width).toBe(300);
  expect(right.transform.width / right.transform.height).toBe(2);
  expect(right.x).toContain(300);
  const left = snapHandle(
    original,
    { ...original, x: 3, width: 197, height: 98.5 },
    "w",
    "scale",
    300,
    200,
    8,
    false,
    false,
  );
  expect(left.transform.x).toBe(0);
  expect(left.transform.x + left.transform.width).toBe(200);
  const top = snapHandle(
    original,
    { ...original, y: 3, height: 147, width: 294 },
    "n",
    "scale",
    300,
    200,
    8,
    false,
    false,
  );
  expect(top.transform.y).toBe(0);
  expect(top.transform.y + top.transform.height).toBe(150);
  const bottom = snapHandle(
    original,
    { ...original, height: 98, width: 196 },
    "s",
    "scale",
    300,
    200,
    8,
    false,
    false,
  );
  expect(bottom.transform.y + bottom.transform.height).toBe(200);
});
it("honors centered and stretch modifiers while snapping", () => {
  const centered = snapHandle(
    original,
    { ...original, x: 2, width: 296, height: 148 },
    "e",
    "scale",
    300,
    200,
    8,
    false,
    true,
  );
  expect(centered.transform.x + centered.transform.width / 2).toBe(150);
  expect(centered.x).toEqual([0, 300]);
  const stretch = snapHandle(
    original,
    { ...original, width: 198, height: 70 },
    "e",
    "scale",
    300,
    200,
    8,
    true,
    false,
  );
  expect(stretch.transform.width).toBe(200);
  expect(stretch.transform.height).toBe(70);
});
it("snaps crop handles to the viewport and leaves the opposite crop symmetric", () => {
  const source = {
    ...original,
    x: -100,
    y: 0,
    width: 500,
    height: 200,
    cropLeft: 0.2,
    cropRight: 0.2,
  };
  const snap = snapHandle(
    source,
    { ...source, cropRight: 0.204 },
    "e",
    "crop",
    300,
    200,
    8,
    false,
    true,
  );
  expect(snap.transform.cropLeft).toBeCloseTo(0.2);
  expect(snap.transform.cropRight).toBeCloseTo(0.2);
  expect(snap.x).toEqual([0, 300]);
});
