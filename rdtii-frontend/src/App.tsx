import { Route, Routes } from "react-router-dom";
import { useEffect, useState } from "react";
import LoginPage from "./pages/auth/login/Login";
import { RegisterPage } from "./pages/auth/register/Register";
import { AboutPage } from "./pages/menu/About";
import { TechMemoPage } from "./pages/menu/TechMemo";
import { MapSearchPage } from "./pages/mapsearch/MapSearch";
import { LandingPage } from "./pages/menu/Landing";
import { WorkbenchPage } from "./pages/workbench/WorkbenchPage";
import { Navbar } from "./components/Navbar/Navbar";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LanguageToggle } from "./components/LanguageToggle";
import { getLocale, LOCALE_CHANGE_EVENT } from "./lib/i18n";

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
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/workbench" element={<ProtectedRoute><WorkbenchPage /></ProtectedRoute>} />
        <Route path="/tech_memo" element={<TechMemoPage />} />
        <Route path="/mapsearch" element={<MapSearchPage />} />
      </Routes>
      <LanguageToggle />
    </>
  );
}
