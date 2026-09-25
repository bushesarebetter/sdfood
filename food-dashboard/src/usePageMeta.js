import { useEffect } from "react";
import { SITE } from "./site";

const TITLE = SITE.siteTitle;

function tag(selector, create) {
  let el = document.querySelector(selector);
  if (!el) {
    el = create();
    document.head.appendChild(el);
  }
  return el;
}

const metaTag = (attr, key) => tag(`meta[${attr}="${key}"]`, () => {
  const m = document.createElement("meta");
  m.setAttribute(attr, key);
  return m;
});

/**
 * One title and one description per view, and the canonical link, so a
 * shared link previews as the view it names. `noindex` asks search engines
 * not to index the view: every place page sets it, because a page about one
 * business should be found through the County's record, not through this site.
 */
export default function usePageMeta({ title, description, noindex = false }) {
  useEffect(() => {
    document.title = title ? `${title} | ${TITLE}` : TITLE;
    if (description) {
      metaTag("name", "description").setAttribute("content", description);
      metaTag("property", "og:description").setAttribute("content", description);
    }
    metaTag("property", "og:title").setAttribute("content", document.title);

    const robots = document.querySelector('meta[name="robots"]');
    if (noindex) metaTag("name", "robots").setAttribute("content", "noindex");
    else if (robots) robots.remove();

    const link = tag('link[rel="canonical"]', () => {
      const l = document.createElement("link");
      l.setAttribute("rel", "canonical");
      return l;
    });
    const { origin, pathname, search } = window.location;
    link.setAttribute("href", origin + pathname + search);
  }, [title, description, noindex]);
}
