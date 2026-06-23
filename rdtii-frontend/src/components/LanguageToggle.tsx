import { useEffect, useState } from "react";
import { getLocale, LOCALE_CHANGE_EVENT, setLocale, t } from "../lib/i18n";

export function LanguageToggle() {
  const [locale, setCurrentLocale] = useState(getLocale);

  useEffect(() => {
    const onLocaleChange = () => setCurrentLocale(getLocale());
    window.addEventListener(LOCALE_CHANGE_EVENT, onLocaleChange);
    return () => window.removeEventListener(LOCALE_CHANGE_EVENT, onLocaleChange);
  }, []);

  const options = [
    { value: "en", label: "EN" },
    { value: "zh", label: "中" },
  ] as const;

  return (
    <div
      className="fixed bottom-4 right-4 z-[70] flex items-center gap-1 rounded-full border border-white/15 bg-black/55 p-1 shadow-lg backdrop-blur-md"
      role="group"
      aria-label={t("nav.language")}
    >
      {options.map((option) => {
        const active = locale === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => setLocale(option.value)}
            className={`h-8 min-h-0 rounded-full px-3 text-xs font-medium transition ${
              active
                ? "bg-[#10B981] text-white"
                : "bg-transparent text-white/65 hover:bg-white/10 hover:text-white"
            }`}
            aria-pressed={active}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
