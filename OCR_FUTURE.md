# OCR future work

Deferred optimizations and follow-ups for the SAOL14 whole-column OCR experiments.

- Candidate-survival event stepping: once the simple row-by-row survival algorithm is correct, avoid reevaluating long unchanged vertical runs. Precompute profile-change events (left-edge x changes, gap starts/ends, new visible front) and advance candidates between those events. This is explicitly an optimization only; correctness should first be established with one physical raster row per step.
