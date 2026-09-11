import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import "./workspace/intelligence-workspace.css";
import "./workspace/liquid-workspace.css";
import App from "./App";
import { initializeWorkspaceAppearance } from "./workspace/workspaceMode";
import { applyTheme, resolveTheme } from "./lib/theme";

// Presentation is a document-level choice, not a post-mount route effect.
initializeWorkspaceAppearance(document.documentElement, window.location.search);
applyTheme(document.documentElement, resolveTheme(window.location.search));

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
