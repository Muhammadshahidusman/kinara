// Minimal hash router: #/alerts/K-2026-0001?x=1 -> { parts: ["alerts", "K-2026-0001"], query }.
import { useEffect, useState } from "react";

export interface Route { parts: string[]; query: URLSearchParams }

function parse(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  const [path, qs] = h.split("?");
  return { parts: path.split("/").filter(Boolean).map(decodeURIComponent), query: new URLSearchParams(qs ?? "") };
}

export function useRoute(): Route {
  const [r, setR] = useState(parse);
  useEffect(() => {
    const on = () => { setR(parse()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return r;
}

export const go = (path: string) => { window.location.hash = path.startsWith("#") ? path : `#/${path.replace(/^\//, "")}`; };
export const href = (path: string) => `#/${path.replace(/^\//, "")}`;
