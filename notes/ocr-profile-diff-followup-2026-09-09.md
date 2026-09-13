# Follow-up: profile matching should wait for meaningful dx events

Save this for later; do not implement yet.

## Idea

We may not need to start deciding from the very first visible pixel row of a glyph profile.

A glyph may be uninformative for several raster rows while the left edge does not move. In profile terms, repeated `dx = 0` may best be treated as **no new event / no new information** rather than as a matching step that should cause candidate birth/death work.

Potential rule to investigate:

- wait until there are at least **two meaningful profile differences/events** before trying to decide which glyph is plausible;
- repeated `dx = 0` means "nothing changed yet" and can be skipped/aggregated;
- the upper row boundary itself can count as a profile event/difference when a glyph reaches it.

## Examples

### `-`

A hyphen can have a long constant run and then two large edge changes. Those changes carry the useful identifying information; examining every unchanged raster row before them may be wasted work.

### `[`

A left bracket can reach the known upper row boundary. In that case the **upper row boundary is itself information**: it acts like a terminating/anchoring event even if there is no previous visible profile row above it from which to compute an ordinary dx.

## Question to answer later

Should the profile matcher be event-based rather than raster-row-based for candidate creation/elimination?

One possible representation:

- ignore/aggregate runs where `dx = 0`;
- emit an event when x changes;
- emit a special boundary event when the profile touches a known row boundary;
- do not attempt glyph identification until enough information exists, perhaps two such events/differences.

This could reduce work substantially while preserving exact raster coordinates. It should be evaluated against the directional top-down / baseline-up matcher after the current page-30 benchmark work.
