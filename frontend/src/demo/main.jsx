import React from "react";
import ReactDOM from "react-dom/client";
import DemoApp from "./DemoApp";
import "@/index.css";

// Entry of the public read-only demo (#458), built by `npm run build:demo`
// into dist-demo/. It must stay free of the router, auth, the app provider and
// every page other than the feed.
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <DemoApp />
  </React.StrictMode>
);
