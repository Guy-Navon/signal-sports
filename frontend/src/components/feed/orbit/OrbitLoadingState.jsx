import React from "react";

// The Orbit skeleton while the feed loads (the app feed and the public demo).
export default function OrbitLoadingState() {
  return (
    <div className="orbit-loading" aria-busy="true" aria-label="טוען את המסלול האישי">
      <div className="orbit-loading__heading">
        <i />
        <i />
      </div>
      <div className="orbit-loading__filters" />
      <div className="orbit-loading__layout">
        <div className="orbit-loading__field">
          <span className="orbit-loading__ring" />
          <div className="orbit-loading__core">
            <i />
            <i />
            <i />
            <i />
          </div>
        </div>
        <div className="orbit-loading__queue">
          {[0, 1, 2, 3].map((index) => (
            <div key={index}>
              <i />
              <i />
              <i />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
