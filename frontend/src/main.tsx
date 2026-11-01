import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./ui/App";
import "./style.css";
// Only the app's own context menus: the browser menu (reload, copy address…) never opens.
window.addEventListener("contextmenu", (event) => event.preventDefault());
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
