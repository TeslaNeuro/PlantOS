/**
 * PlantOS operations console entry.
 * SPDX-License-Identifier: MIT
 * Copyright (c) 2026 TeslaNeuro
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
