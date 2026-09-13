# TAPTO – whole-column / consumed-profile OCR – 2026-09-08

Branch: `agent/ocr-whole-column-shadow`

Known branch HEAD before this note: `3bc20d8626cc2390192e21eb9fb60bfb10f75f7b`.

## Where we are

We are experimenting with exact SAOL14 OCR from the digital facsimile raster using canonical glyph pixel templates.

The important successful experiment is **consumed-profile matching**:

1. identify a glyph exactly;
2. assign/consume exactly that glyph's black pixels;
3. keep all page coordinates absolute;
4. run the same left-profile logic on the remaining, unassigned pixels;
5. the next glyph may start inside the previous glyph's x bounding box.

This solved the real italic overlap on page 39:

- `t` at x=171..175
- next `r` at x=175..180
- `overlap_x=1`
- it was found by `profile-consumed`, not by the old straight-x cursor rule.

This is strong evidence that glyph traversal should ultimately be based on **remaining pixels**, not on a straight vertical crop after the previous glyph.

Do NOT yet promote the current shadow implementation to production OCR. It is functionally promising but far too slow.

## Baseline / separator semantics that must be preserved

- Without a verified vertical white separator, the baseline stays locked.
- After a verified vertical white separator, profile matching may restart completely and establish a new baseline.
- A vertical white separator is therefore permission for baseline reset, not necessarily the mechanism for moving between glyphs.
- A detached glyph's internal horizontal blank raster band must be empty only inside that glyph's own x-span; ink farther right is allowed.

## Sequential row boundaries

Only the current row's upper boundary needs to be known initially.

After a row is completed:

- collect all pixels assigned to accepted glyphs, including descenders;
- `next_row_top = max(y of assigned pixels) + 1`;
- every assigned pixel from the completed row is then strictly above the next row boundary.

A row is finished when, after baseline is established, there is no remaining row ink to the right in `row_top..baseline`. Pixels below baseline alone do not keep the row alive.

## Current page-39 result

Rows 0 and 1 complete correctly in the shadow run:

- row 0: `ap|flocks.~en~ar`
- row 1: `AP-fonds.~en~er¤allmän`

Row 2 reaches:

- `pensionsfond:tred`

The source text continues `pensionsfond: tredje` (spaces are not represented yet).

At approximately x=199 the matcher sees an ambiguity between `·` and `.`. The facit currently has no `j` glyph, so this is very plausibly the dot over the missing `j`, not an algorithmic punctuation problem. Do not special-case this ambiguity. Later use the glyph editor to add `j` from this occurrence.

## Change of test page

For the next performance/algorithm work, use **page 30**, not page 39. We know the glyphs needed on page 30 are already represented in the facit, so an algorithm stop there should not be confused with an incomplete glyph library.

## Performance problem – important

The current shadow implementation takes many seconds per row. Earlier OCR work processed roughly a whole page in about 5 seconds. Therefore the current implementation is only a correctness experiment, not a viable implementation.

The obvious architectural cost is repeated `run_candidate_survival()` calls. Each call currently rebuilds:

- `black_by_y` from the black-pixel set;
- `_model_rows()` for all ~428 glyph models;
- `_internal_gap_rows()` for all models;
- then scans the requested y range again.

The shadow walker calls this repeatedly after glyphs/restarts. Do not waste time microbenchmarking this known-bad architecture.

Next implementation direction:

1. precompile model rows, gaps, x/y bounds and profile information once when the facit is loaded;
2. build page/column pixel indexes once (`black_by_y`, and probably `black_by_x` / efficient residual-row ownership);
3. keep a mutable/logical consumed-pixel state rather than recreating `set(black) - set(consumed)` repeatedly;
4. after accepting a glyph, update only the affected raster rows;
5. do not rescan to `column_bottom` after every glyph;
6. preserve exact absolute coordinates and the proven consumed-profile semantics;
7. benchmark page 30 after the architectural change; target is again seconds per PAGE, not seconds per row.

Current relevant files:

- `src/swedish_wordlist_tools/ocr_candidate_survival.py`
- `src/swedish_wordlist_tools/ocr_shadow_column_from_top.py`

## Recovery after an unknown/missed glyph

This is not solved yet and should be handled conservatively.

Desired distinction:

- normal exact traversal: accepted glyph -> consume exact pixels -> continue;
- unresolved/ambiguous glyph: do not silently accept a punctuation fragment or guess;
- possible later resynchronization after sufficiently safe whitespace may be useful diagnostically, but text after such recovery should be marked as resynced rather than pretending the whole sequence was exact.

A first white x-column after an unknown glyph is not automatically safe, because it could theoretically be an internal gap of an unresolved glyph. Keep this concern explicit when designing recovery.

## Glyph editor / review loop

After performance is under control, reconnect the existing glyph review/editor so an unresolved residual cluster can be inspected and added to the canonical facit (e.g. the missing `j` on page 39).

Do not solve the missing `j` before the performance architecture; page 30 is the clean next test.

## VERY IMPORTANT DEBUG-VIEW PATTERN

For geometry bugs, make a **pixel-native HTML debug page** like the useful one made earlier: visually it should feel like millimeter paper, with the source raster pixels as the coordinate unit.

The essential design rule is:

- **1 source raster pixel = 1 logical grid unit**.

Do not make a conventional scaled screenshot where CSS/image interpolation obscures coordinates. Render the diagnostic geometry on a grid/pixel canvas where every black source pixel, candidate pixel, bbox edge, baseline, row boundary, separator, consumed/unconsumed state etc. lands on exact integer raster coordinates. Then enlarge the whole thing for human viewing while preserving nearest-neighbour / hard-edged cells.

The debug page should make it possible to visually check exact pixel ownership and off-by-one errors. Useful overlays/annotations include:

- original black pixels;
- consumed/assigned pixels versus residual/unassigned pixels;
- current glyph's exact placed pixel set;
- candidate glyph pixels;
- row top;
- baseline;
- next-row boundary;
- vertical separator x;
- physical x/y coordinate labels or grid ticks;
- candidate bounding boxes only as secondary information (actual pixel sets are authoritative);
- enough surrounding source context to understand the row.

The key memory is the **millimeter-paper idea**: raster pixels themselves are the units, and the visualization is enlarged without changing that coordinate system. This was much easier to reason about than ordinary cropped PNGs and should be recreated whenever geometry becomes unclear.

## Resume command (current shadow tool)

After pulling the branch, page 30 is the intended next experiment:

```bash
cd ~/proj/saol14-fast-forward-test
git pull

PYTHONPATH=src python -m swedish_wordlist_tools.ocr_shadow_column_from_top \
  /home/matsj/proj/saol14-faksimil.jsonl \
  --facit glyphs/saol14-manual-glyph-facit-v2.json \
  --page 30 \
  --column 0 \
  --rows 4
```

But first implement the reusable/precompiled survival indexes; the current command is expected to remain slow until that is done.
