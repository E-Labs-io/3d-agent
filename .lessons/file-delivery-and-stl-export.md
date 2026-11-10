# Sending files to the user: one per call. And check where exports actually land.

## Multi-file sends drop everything after the first
`SendUserFile` with an array of paths reports "N files delivered" but only the
first actually arrives. Hit twice in the MIF4 cradle session — sent body+plate,
user got body only, twice, and had to ask for the plate three times.

**Do:** one file per call. Send the thing they asked for first.

## The in-app Browser pane cannot download
Browser-triggered downloads (`a.download` / `saveBlob`) silently do nothing in
the Claude Code Browser pane — `~/Downloads` stays empty. Not a Chrome
multi-download prompt; nothing arrives at all.

**Do:** for anything the user needs on disk, write it server-side
(`POST /api/export`) so it lands in a known folder. Treat the browser download
as a bonus, never the delivery mechanism. If they want working downloads, tell
them to open `http://localhost:3030` in their own browser.

## Check the destination before diagnosing
I blamed Chrome's multi-download prompt and shipped a staggered-download fix
*before* looking in `~/Downloads`. It was empty — no download had ever worked,
so the whole theory was wrong and the user asked twice more.

**Do:** `ls` the destination first. One command settles it.
