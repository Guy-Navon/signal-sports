import React, { Suspense } from "react";
import ErrorState from "@/components/shared/ErrorState";
import { useEngineTraceVisible } from "@/context/AppContext";

function reloadPage() {
  window.location.reload();
}

// Readers get plain Hebrew; ops keeps the raw detail, the same split as
// connectionErrorStrip. Everyone's error still reaches the console below.
function ScreenError({ error }) {
  const showDetail = useEngineTraceVisible();
  return (
    <ErrorState
      variant="page"
      title="לא הצלחנו להציג את המסך"
      message={showDetail ? error.message || String(error) : null}
      onRetry={reloadPage}
      retryLabel="טען מחדש"
    />
  );
}

// Without this, a chunk that cannot load (a deploy replaced the hashed file while
// the tab stayed open, or the network dropped) would blank the whole app. It also
// catches render errors from the screen inside, so the copy names no single cause.
class ScreenErrorBoundary extends React.Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    console.error("lazy screen failed", error);
  }

  render() {
    const { error } = this.state;
    return error ? <ScreenError error={error} /> : this.props.children;
  }
}

// The boundary around anything loaded with React.lazy (#199).
export default function LazyBoundary({ children }) {
  return (
    <ScreenErrorBoundary>
      <Suspense
        fallback={
          <p role="status" className="py-16 text-center text-sm text-text-dim">
            טוען…
          </p>
        }
      >
        {children}
      </Suspense>
    </ScreenErrorBoundary>
  );
}
