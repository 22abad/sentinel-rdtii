import { Route, Routes } from "react-router-dom";
import { Component, lazy, Suspense, useEffect, useState, type ErrorInfo, type ReactNode } from "react";
import { Navbar } from "./components/Navbar/Navbar";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LanguageToggle } from "./components/LanguageToggle";
import { getLocale, LOCALE_CHANGE_EVENT } from "./lib/i18n";

const LoginPage = lazy(() => import("./pages/auth/login/Login").then(({ default: LoginPage }) => ({ default: LoginPage })));
const RegisterPage = lazy(() => import("./pages/auth/register/Register").then(({ RegisterPage }) => ({ default: RegisterPage })));
const AboutPage = lazy(() => import("./pages/menu/About").then(({ AboutPage }) => ({ default: AboutPage })));
const TechMemoPage = lazy(() => import("./pages/menu/TechMemo").then(({ TechMemoPage }) => ({ default: TechMemoPage })));
const MapSearchPage = lazy(() => import("./pages/mapsearch/MapSearch").then(({ MapSearchPage }) => ({ default: MapSearchPage })));
const LandingPage = lazy(() => import("./pages/menu/Landing").then(({ LandingPage }) => ({ default: LandingPage })));
const WorkbenchPage = lazy(() => import("./pages/workbench/WorkbenchPage").then(({ WorkbenchPage }) => ({ default: WorkbenchPage })));

export function App() {
  const [, setLocaleVersion] = useState(getLocale);

  useEffect(() => {
    const onLocaleChange = () => setLocaleVersion(getLocale());
    window.addEventListener(LOCALE_CHANGE_EVENT, onLocaleChange);
    return () => window.removeEventListener(LOCALE_CHANGE_EVENT, onLocaleChange);
  }, []);

  return (
    <>
      <Navbar />
      <RouteErrorBoundary>
        <Suspense fallback={null}>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/workbench" element={<ProtectedRoute><WorkbenchPage /></ProtectedRoute>} />
            <Route path="/tech_memo" element={<TechMemoPage />} />
            <Route path="/mapsearch" element={<MapSearchPage />} />
          </Routes>
        </Suspense>
      </RouteErrorBoundary>
      <LanguageToggle />
    </>
  );
}

type RouteErrorBoundaryProps = {
  children: ReactNode;
};

type RouteErrorBoundaryState = {
  hasError: boolean;
};

class RouteErrorBoundary extends Component<RouteErrorBoundaryProps, RouteErrorBoundaryState> {
  state: RouteErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): RouteErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Route chunk failed to render.", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main style={{ minHeight: "60vh", display: "grid", placeItems: "center", padding: 24 }}>
          <div role="alert" style={{ maxWidth: 420, textAlign: "center" }}>
            <h1 style={{ marginBottom: 12, fontSize: "1.25rem" }}>Unable to load this page</h1>
            <p style={{ marginBottom: 20, color: "#64748b" }}>
              Refresh the app to get the latest frontend files.
            </p>
            <button className="primary" onClick={() => window.location.reload()}>
              Refresh
            </button>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}
