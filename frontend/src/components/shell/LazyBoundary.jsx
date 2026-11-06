import React, { Suspense } from "react";
import ErrorState from "@/components/shared/ErrorState";

function reloadPage() {
  window.location.reload();
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
    if (error) {
      return (
        <ErrorState
          variant="page"
          title="לא הצלחנו להציג את המסך"
          message={error.message || String(error)}
          onRetry={reloadPage}
          retryLabel="טען מחדש"
        />
      );
    }
    return this.props.children;
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
