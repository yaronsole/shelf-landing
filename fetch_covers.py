#!/usr/bin/env python3
"""Fetch book covers for the Shelf landing page.

Discovery runs through the Google Books API (set GOOGLE_BOOKS_API_KEY in the
environment to use a key; it also works keyless at tiny volume, though the
shared keyless pool is often rate-limited). For a crisper, canonical image we
also use Open Library covers (the same source the Shelf app uses in
production) — its "-L" covers are ~500px vs Google's ~128px thumbnails.

Two hard rules drive the title list (see SHELF_LANDING_PAGE_CLAUDE_CODE_PLAN.md):
  1. No public-figure faces on any cover.
  2. No celebrity/book-club names in the page copy.
Several "obvious" titles were dropped because their real cover is a face:
  - Born a Crime  -> The Goldfinch          (cover is Trevor Noah's portrait)
  - Daisy Jones   -> Normal People          (face-forward model photo)
  - Hello Beautiful -> A Gentleman in Moscow (face-dominant edition; Eleanor
                       Oliphant was rejected too — its cover carries a Reese
                       Witherspoon blurb + book-club seal, see hard rule 2)
For titles where Google tends to return a movie/TV tie-in (faces) or an
"image not available" placeholder, an ISBN of the canonical book edition is
pinned so Open Library returns the right art deterministically.

EXCEPTION (owner override of hard rule 1): slots 08 Open (Andre Agassi) and
11 A Promised Land (Barack Obama) ARE public-figure face covers, added at the
owner's explicit request after being warned of the Meta ad-rejection /
endorsement / political-content risk. Slot 06 Creativity, Inc. (Ed Catmull)
is a non-face typographic cover, also added by request. These replaced The
Four Winds, The Midnight Library, Tom Lake, and Greenlights over two rounds.

HAND-SOURCED COVERS (this script's auto-fetch would regress them, so the
committed covers/*.jpg are the source of truth — don't blindly overwrite):
06 Creativity, Inc. uses Google's clean "Expanded Edition" art (volume
0bbYEAAAQBAJ) because OL's scan carried a library sticker + was low-res;
08 Open uses Google's English Knopf cover (OL only had the German edition).

No secrets are hardcoded, so this file is safe to commit. Covers are written
to covers/NN-slug.jpg. Always eyeball the result against the two hard rules.

Usage:
  python3 fetch_covers.py              # fetch all
  python3 fetch_covers.py 13-pachinko  # fetch only the given slug(s)
"""
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

# (index, file_slug, title, author, isbn_pin)  -- isbn_pin "" = discover via Google
BOOKS = [
    (1,  "01-crawdads",          "Where the Crawdads Sing",            "Delia Owens",         ""),
    (2,  "02-normal-people",     "Normal People",                      "Sally Rooney",        "9781984822178"),
    (3,  "03-little-fires",      "Little Fires Everywhere",            "Celeste Ng",          ""),
    (4,  "04-nightingale",       "The Nightingale",                    "Kristin Hannah",      ""),
    (5,  "05-such-a-fun-age",    "Such a Fun Age",                     "Kiley Reid",          ""),
    (6,  "06-creativity-inc",    "Creativity, Inc.",                   "Ed Catmull",          "9780812993011"),
    (7,  "07-american-marriage", "An American Marriage",               "Tayari Jones",        ""),
    (8,  "08-open-agassi",       "Open",                               "Andre Agassi",        "9780307268198"),
    (9,  "09-vanishing-half",    "The Vanishing Half",                 "Brit Bennett",        ""),
    (10, "10-seven-husbands",    "The Seven Husbands of Evelyn Hugo",  "Taylor Jenkins Reid", ""),
    (11, "11-promised-land",     "A Promised Land",                    "Barack Obama",        "9781524763169"),
    (12, "12-lessons-chemistry", "Lessons in Chemistry",               "Bonnie Garmus",       ""),
    (13, "13-pachinko",          "Pachinko",                           "Min Jin Lee",         "9781455563937"),
    (14, "14-gentleman-moscow",  "A Gentleman in Moscow",              "Amor Towles",         "9780670026197"),
    (15, "15-educated",          "Educated",                           "Tara Westover",       ""),
    (16, "16-goldfinch",         "The Goldfinch",                      "Donna Tartt",         "9780316055437"),
    (17, "17-crying-h-mart",     "Crying in H Mart",                   "Michelle Zauner",     ""),
    (18, "18-just-mercy",        "Just Mercy",                         "Bryan Stevenson",     ""),
]

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "covers")
KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")
CTX = ssl.create_default_context()
HEADERS = {"User-Agent": "Mozilla/5.0 (shelf-landing cover fetch)"}
MIN_BYTES = 3000  # smaller than this is a blank/placeholder


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return r.read() if binary else r.read().decode("utf-8")


def norm(s):
    return "".join(c.lower() for c in s if c.isalnum())


def ol_isbn_url(isbn):
    return "https://covers.openlibrary.org/b/isbn/%s-L.jpg?default=false" % isbn


def ol_search_cover_urls(title, author):
    url = ("https://openlibrary.org/search.json?title=%s&author=%s"
           "&limit=5&fields=cover_i,edition_count"
           % (urllib.parse.quote(title), urllib.parse.quote(author)))
    try:
        docs = json.loads(fetch(url)).get("docs", [])
    except Exception:
        return []
    return ["https://covers.openlibrary.org/b/id/%s-L.jpg?default=false" % d["cover_i"]
            for d in docs if d.get("cover_i")]


def google_books(title, author):
    q = 'intitle:"%s" inauthor:"%s"' % (title, author)
    url = ("https://www.googleapis.com/books/v1/volumes?q=%s"
           "&maxResults=5&country=US&printType=books" % urllib.parse.quote(q))
    if KEY:
        url += "&key=" + KEY
    return json.loads(fetch(url)).get("items", []) or []


def pick_volume(items, title):
    want = norm(title)
    best, best_score = None, -1
    for it in items:
        vi = it.get("volumeInfo", {})
        if not vi.get("imageLinks"):
            continue
        have = norm(vi.get("title", ""))
        score = 3 if have == want else (1 if (want in have or have in want) else 0)
        score += 1 if vi["imageLinks"].get("thumbnail") else 0
        if score > best_score:
            best, best_score = vi, score
    return best


def isbn_of(vi):
    for want in ("ISBN_13", "ISBN_10"):
        for ident in vi.get("industryIdentifiers", []):
            if ident.get("type") == want:
                return ident.get("identifier")
    return None


def clean_google_img(url):
    url = url.replace("http://", "https://")
    url = re.sub(r"&?edge=curl", "", url)
    url = re.sub(r"zoom=\d", "zoom=2", url)  # nudge past the 128px thumbnail
    return url


def try_download(url):
    try:
        data = fetch(url, binary=True)
    except Exception:
        return None
    return data if data and len(data) >= MIN_BYTES else None


def get_cover(title, author, isbn_pin):
    """Return (source, bytes) for the largest usable cover. Gathers several
    canonical sources — pinned-ISBN Open Library, OL title/author search
    (ranked by editions), Google Books image, and Google's reported ISBN on
    OL — then keeps the biggest file (best resolution). Pinning an ISBN and/or
    OL search keeps us on the original book edition, dodging movie/TV tie-in
    faces and Google's 'image not available' placeholder."""
    candidates = []
    if isbn_pin:
        candidates.append(("openlibrary(pin)", ol_isbn_url(isbn_pin)))
    for url in ol_search_cover_urls(title, author):
        candidates.append(("openlibrary(search)", url))

    vi = pick_volume(google_books(title, author), title)
    if vi:
        il = vi.get("imageLinks", {})
        g = il.get("large") or il.get("medium") or il.get("thumbnail") or il.get("smallThumbnail")
        if g:
            candidates.append(("googlebooks", clean_google_img(g)))
        isbn = isbn_of(vi)
        if isbn:
            candidates.append(("openlibrary", ol_isbn_url(isbn)))

    best_src, best = None, None
    for src, url in candidates:
        data = try_download(url)
        if data and (best is None or len(data) > len(best)):
            best_src, best = src, data
    return (best_src, best) if best else (None, None)


def main():
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    books = [b for b in BOOKS if not only or b[1] in only]
    ok, problems = 0, []
    for idx, slug, title, author, isbn_pin in books:
        try:
            src, data = get_cover(title, author, isbn_pin)
            if not data:
                problems.append((slug, title, "no usable cover downloaded"))
                print("MISS  %-22s %s" % (slug, title))
                continue
            with open(os.path.join(OUT, slug + ".jpg"), "wb") as f:
                f.write(data)
            ok += 1
            print("OK    %-22s %-16s %6d B  %s" % (slug, src, len(data), title))
        except Exception as e:
            problems.append((slug, title, "error: %s" % e))
            print("ERR   %-22s %s  (%s)" % (slug, title, e))

    print("\n%d/%d covers written to %s" % (ok, len(books), OUT))
    print("Eyeball every cover: no public-figure faces, art must match the title.")
    if problems:
        print("\nFlagged:")
        for slug, title, why in problems:
            print("  - %-22s %-35s %s" % (slug, title, why))


if __name__ == "__main__":
    main()
