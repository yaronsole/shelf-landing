# Shelf — landing page

A single-screen marketing landing page for the **Shelf** iOS app, used as the
destination for a Meta (Facebook/Instagram) ad campaign. Hosted on GitHub Pages.

**Live:** https://yaronsole.github.io/shelf-landing/

## What it is

One non-scrolling screen, built to feel like a seamless continuation of the
app's splash: a cream canvas with a slowly drifting wall of book covers behind
a cream fade, and the app's signature near-black full-width CTA. Its single job
is to drive the tap on **Get Shelf on the App Store**.

- `index.html` — self-contained (inline CSS + JS, no build step, no framework).
- `covers/` — 18 book covers, committed locally (not hot-linked).
- `fetch_covers.py` — regenerates `covers/` from Google Books + Open Library.

## Measurement (the point of the page)

A Meta Pixel fires `PageView` on load and a **`Lead`** event on the CTA tap
(`content_name: AppStore_tap`), so "cost per App Store tap" shows up in Meta
Ads Manager as a proxy conversion (iOS SKAdNetwork returns little at small
budgets).

> **Before running ads:** replace `YOUR_PIXEL_ID` in `index.html` (two places:
> the `fbq('init', …)` call and the `<noscript>` fallback) with your real Pixel
> ID from Meta Events Manager → Data Sources → your pixel → Settings. The page
> renders fine with the placeholder; it just won't report until it's set.

## Cover rules (legal + brand — do not break)

1. **No public-figure faces** on any cover (no portrait/memoir covers, no
   movie/TV tie-in editions with actors). Several "obvious" titles were swapped
   for this reason — see `fetch_covers.py`.
2. **No celebrity or book-club names** in the page copy.

## Regenerating covers

```bash
# keyless works but is often rate-limited; pass a key to be safe
GOOGLE_BOOKS_API_KEY=... python3 fetch_covers.py            # all 18
GOOGLE_BOOKS_API_KEY=... python3 fetch_covers.py 13-pachinko # one slug
```

Always eyeball the result against the two cover rules before committing.
