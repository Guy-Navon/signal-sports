import React from "react";
import ReactDOM from "react-dom/client";
import LabApp from "./LabApp";
import "@/index.css";

// Dev-only design lab (#462): a specimen of the new consumer UI's tokens, type
// and marks in all three grounds. Its own entry (lab.html, vite.lab.config.js),
// so nothing here reaches the main or demo bundles. index.css is loaded so the
// specimen sits in the same cascade the real screens will.
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <LabApp />
  </React.StrictMode>
);
