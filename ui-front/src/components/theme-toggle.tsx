"use client";

import { useTheme } from "./theme-provider";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      <span>{theme === "dark" ? "Dark" : "Light"}</span>
      <span className="theme-toggle-track">
        <span className="theme-toggle-thumb" />
      </span>
    </button>
  );
}
