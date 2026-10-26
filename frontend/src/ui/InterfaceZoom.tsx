import { useEffect, useState } from "react";
import { ZoomIn, ZoomOut } from "lucide-react";

export function InterfaceZoom() {
  const [zoom, setZoom] = useState(1);
  useEffect(() => {
    const apply = () => {
      if (window.videoFlowDesktop) window.videoFlowDesktop.setZoom(zoom);
      else if (!window.__videoflowDesktop)
        document.documentElement.style.zoom = String(zoom);
    };
    apply();
    window.addEventListener("videoflow-ready", apply);
    return () => window.removeEventListener("videoflow-ready", apply);
  }, [zoom]);
  useEffect(() => {
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey || event.defaultPrevented) return;
      event.preventDefault();
      setZoom((old) =>
        Math.max(
          0.5,
          Math.min(
            2,
            Math.round((old + (event.deltaY < 0 ? 0.1 : -0.1)) * 100) / 100,
          ),
        ),
      );
    };
    window.addEventListener("wheel", wheel, { passive: false });
    return () => window.removeEventListener("wheel", wheel);
  }, []);
  return (
    <div className="interface-zoom">
      <button
        aria-label="Zoom out interface"
        disabled={zoom <= 0.5}
        onClick={() => setZoom(Math.max(0.5, zoom - 0.1))}
      >
        <ZoomOut size={15} />
      </button>
      <button
        aria-label="Reset interface zoom"
        title="Reset to 100%"
        onClick={() => setZoom(1)}
      >
        {Math.round(zoom * 100)}%
      </button>
      <button
        aria-label="Zoom in interface"
        disabled={zoom >= 2}
        onClick={() => setZoom(Math.min(2, zoom + 0.1))}
      >
        <ZoomIn size={15} />
      </button>
    </div>
  );
}
