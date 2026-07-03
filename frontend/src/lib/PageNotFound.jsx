import { useLocation, useNavigate } from "react-router-dom";
import { Home } from "lucide-react";

export default function PageNotFound() {
  const location = useLocation();
  const navigate = useNavigate();
  const pageName = location.pathname.substring(1);

  return (
    <div className="min-h-screen flex items-center justify-center p-6" dir="rtl">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="space-y-2">
          <h1 className="font-display text-7xl font-light text-text-dim">404</h1>
          <div className="h-0.5 w-16 bg-border mx-auto" />
        </div>
        <div className="space-y-2">
          <h2 className="text-2xl font-medium text-foreground">הדף לא נמצא</h2>
          <p className="text-text-secondary leading-relaxed">
            הדף <span className="font-medium text-foreground" dir="ltr">"{pageName}"</span> לא קיים.
          </p>
        </div>
        <button
          onClick={() => navigate("/")}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-foreground bg-surface-2 border border-border rounded-lg hover:bg-surface-3 hover:border-text-dim transition-colors"
        >
          <Home size={15} />
          חזרה לפיד
        </button>
      </div>
    </div>
  );
}
