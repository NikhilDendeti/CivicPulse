import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";
import te from "../locales/te.json";

let saved = "en";
try {
  saved = localStorage.getItem("cp_lang") ?? (navigator.language.startsWith("te") ? "te" : "en");
} catch {
  /* storage unavailable */
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, te: { translation: te } },
  lng: saved,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export function setLang(lng: "en" | "te") {
  void i18n.changeLanguage(lng);
  try {
    localStorage.setItem("cp_lang", lng);
  } catch {
    /* ignore */
  }
}
export default i18n;
