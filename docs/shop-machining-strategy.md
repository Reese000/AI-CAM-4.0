# Shop Machining Strategies — Bar Parts and Edge Breaks (v4)

> **Canonical copy:** `Web DFM/docs/SHOP-MACHINING-STRATEGY.md`. Copies live in AI CAM 3.0, AI CAM 4.0 and cam-lora `docs/`. Edit the canonical copy, then re-copy.


**Source:** the shop owner (Reese CNC), in conversation on 2026-09-12. v4 incorporates the owner's
corrections to v1, v2 and v3. This document is the authority on *how this shop actually machines parts*. Where
it conflicts with generic CNC knowledge or with existing code, this document wins.

**Consumers:** Web DFM (priority) and AI CAM 3.0.

**Machine context:** 3-axis vertical mill. Anything on a side face needs the part manually relocated.

**Units:** inches throughout, unless stated otherwise. CAD files are usually mm, so convert first.

**How to read the markers:**
- **[A-n]** is an *assumption*: a value or rule the owner has not explicitly confirmed. Put every
  [A] value in config, marked `assumed: true`, so the owner can change it without a code change.
- **[Q-n]** is an *open question* still waiting on the owner (listed in Part 3). Do not invent an
  answer. Use the stated default and surface the uncertainty.

---

## Part 1 — Bar Parts (multi-part bar machining)

### 1.1 What it is, in one paragraph

Several identical parts are machined side by side, in a single row, from one bar held in a 6" vise.
**Op 1** faces the bar, contours the parts, and cuts split slots between them. The parts stay joined
through a thin strip of uncut stock at the bottom, called the **hat**. Optionally, the joined strip
is then turned on its side to machine features on the side faces. **Op 2** flips the strip into a
second vise and faces the hat off, which frees the parts, and machines whatever is left on that side.
Because the parts were still joined when they were relocated, they all land in the same relative
positions in every later setup. One probe cycle serves the whole row, and features line up across
every part to well under 0.001".

Even at only **2 parts per bar** this can pay off at high quantity: half the tool changes, half the
cycle starts, and about 1.5x the walk-away time.

### 1.2 Glossary

| Term | Meaning |
|---|---|
| **Bar** | One piece of stock holding N parts in a single row. Roughly 6.2" long. |
| **Bar axis (X)** | The long axis of the bar, running along the vise jaws. |
| **Y faces** | The part faces that point toward the vise jaws. |
| **X faces** | The part faces that point toward the neighbouring parts, across the split slots. |
| **Op 1 face (+Z)** | The part face pointing up in Op 1. Choosing it is the key decision (section 1.6). **It is not necessarily the part's "top" or its most complicated face.** |
| **Op 2 face (-Z)** | The opposite face. It points up after the flip. |
| **Hat** | Stock left below the part in Op 1: at least 0.125" thick, of which 0.100" sits inside the jaw step (full budget in 1.3). |
| **Split slot / split contour** | The cut that separates neighbouring parts. A straight slot for rectangular X faces; a contour around each part for other outlines. |
| **Splitting end mill** | 1/4" flat end mill by default. 3/8" for deep parts (section 1.5). |
| **Op 2 grip band** | The part height clamped by the Op 2 jaws, measured up from the Op 1 face (which rests on the parallels). Op 2 can only machine *above* this band. |
| **Blend** | One continuous surface (e.g. one flat wall) finished partly in one setup and partly in another. Leaves a visible mismatch line. |
| **G54 / G55** | Work offsets for Op 1 and Op 2, one per vise. |

### 1.3 Shop constants

| Constant | Value | Source |
|---|---|---|
| Vise jaw length (Op 1 and Op 2) | 6.000" | owner |
| Op 1 jaws | stepped, serrated hard jaws | owner |
| Jaw step depth (Op 1 grip height) | 0.100" | owner |
| Hat allowance | **Conditional — see 1.5.2.** When Op 1 must cut down to the bottom of the part (continuous vertical walls), the stock needs at least 0.125" more than the part (budget below). That is the absolute minimum and can never be less, and every rule must still **accept** exactly part + 0.125"; 0.250" is fine if the price is no worse. When Op 1's cuts stop well short of the stock bottom, a cleanup pass on each face is enough. | owner |
| Top skim (facing cleanup per face) | 0.010" | owner |
| Wall overcut below part bottom in Op 1 (contour extra depth) | **0.030" optimal**, whenever the stock leaves room above the jaws; 0.010" minimum. Planned overcut = min(0.030, headroom - 0.005), where headroom = stock Z - skim - op1_depth - 0.100. Below 0.010" the stock is too thin. | owner |
| Jaw clearance (deepest Op 1 cut above the jaw top) | 0.005" | owner |
| **Z stock budget, full-depth part** | **0.125" = 0.100 jaw grip + 0.010 top skim + 0.010 contour overcut (minimum) + 0.005 jaw clearance.** Stock sizing uses the 0.010" minimum; the optimal 0.030" overcut is used only when the chosen stock has the room (e.g. +0.250" stock). Stock of exactly part Z + 0.125" must always pass. No rule may add margin on top of this that would reject it. | owner |
| Finish stock on ordinary faces | 0.005" | owner |
| Finish stock per wall in split slots, nominal | 0.010" | owner |
| Part gap, nominal (1/4" tool) | 0.270" | owner |
| Part gap, widened without extra roughing | up to about 0.300" (about 0.025" finish stock per wall) | owner |
| Part gap wider than 0.300" | allowed, but adds a 1/4" end mill roughing pass in the slots (costs time) | owner |
| Part gap with a 3/8" tool | 0.375 + 2 x 0.010 = 0.395" nominal **[A-1]** | derived |
| Target span of all parts along X | a little over 6.0", e.g. 6.10" | owner |
| Stock length | span + about 0.10" (about 0.05" per end) **[A-7]** | owner example |
| End part held in the Op 2 jaws (fraction of its X length) | at least 50% workable, 75% or more optimal | owner |
| Min part Z for Op 2 grip | 0.1875" (3/16") | owner ("probably") |
| Max split depth | 5xD in aluminum and plastics; 4xD in regular steels; 3xD in hard-to-machine materials (e.g. 304 SS) | owner |
| Op 2 jaws | standard hard jaws, part on parallels, fixed X stop | owner |
| Op 2 jaw depth (maximum grip height) | about 1.75" | owner |
| Op 2 clearance: lowest Op 2 cut (edge-break passes included) above the jaw top | 0.030" **[A-17]** | assumed; owner: "as deep as I can get it without worrying about hitting the jaws" |
| Spot oversize on HSS-drilled holes | 0.007" on diameter (being fine-tuned) | owner |

### 1.4 The process, step by step

#### Op 1 — G54, stepped serrated jaws. Origin: top-left-back corner of the STOCK.

Op 1 **must** do three things: **face, split, and contour.** Everything else is optional in Op 1 and
goes wherever it is best done (section 1.6).

1. Put the bar in the jaws, sitting on the 0.100" step. A **removable stop** sets rough X.
2. **Probing (first bar only).** The X, Y and Z probe cycles are **block-delete lines** (`/`). After
   the first bar the operator turns block delete on, and they are skipped. That is safe because Y
   and Z come from the jaws, which never move, and bar-to-bar stock variation is negligible.
3. **Jaw-crash safety check, built into the Y probe.** The Y probe cycle descends, in protected-move
   mode, to a Z a couple of thousandths **below the deepest tool depth** in the program.
   - If the Z origin is wrong (too low), the probe hits the jaw top and the program alarms before any
     tool can cut the jaws.
   - If the probe gets down, that proves every tool in the program clears the jaws.
4. Face.
5. Contour and split. Walls that need to be full depth are finished full depth, overcut below the part
   bottom by **0.030" when the stock allows** (optimal), never less than 0.010", and always leaving at
   least 0.005" above the jaw top. See the planned-overcut formula in 1.5.2.
   - **Split slots** leave 0.010" per wall (up to about 0.025" if the gap was widened), then a
     finishing pass takes the walls to size. The slot stops above the jaw top, so the parts stay
     joined through the hat.
   - **Outermost X faces** (X- end of the first part, X+ end of the last part) are finished **through
     the full stock thickness, hat included**. It is possible because the span (about 6.10") is
     longer than the jaws (6.00"), so these walls sit outside the jaw ends and the tool never meets a
     jaw. **Why this matters:** later setups probe X on one of these end walls. A leftover 0.125" hat
     step would block the probe.
   - **Partial-depth parts.** A contour does **not** have to go full depth if the part has no
     continuous vertical wall running its full height.
     - Example: a pyramid on an extruded square base. Op 1 takes the base side. The finished profile
       only runs the height of the extrusion, so Op 1 contours and partly splits only that deep.
     - The rest of the stock stays solid. It holds the row together and is what the Op 1 jaws grip.
     - In Op 2 that leftover material is roughed away, and whatever still joins the parts is
       separated there, while every part is clamped by its extruded section.
     - No continuous wall crosses from Op 1 into Op 2, so there is no blend. The Op 2 separation is
       usually a wide roughing cut, not a slot.
     - The stock needs only a cleanup pass on each face, not the 0.125" hat (section 1.5.2).
6. Any other features that are best done from this side, then the edge breaks on this side (Part 2).

The overcut in step 5 is why facing the hat off in Op 2 frees each part cleanly. Without it, a thin
skin or lip would be left on the bottom edge.

#### Y-face setups — optional, BEFORE Op 2, parts still joined

Only the **Y faces** can be reached on the joined strip. Each X face sits a split gap away from the
neighbouring part.

1. Stand the strip on its side. The **machined Op 1 face goes against the vise's fixed hard jaw.**
   - **Never put the unmachined hat side against the fixed jaw.** Stock size varies bar to bar, so the
     part's Y location would shift.
2. The part rests on parallels that touch **only the finished Y face**. The hat is still attached and
   sticks out below that face, so on the moving-jaw side a **shorter parallel** acts as a spacer and
   leaves room for the hat. That way the part sits flat on its machined face.
3. Machine the upward Y face. Then flip the strip and do the other Y face, if it has features.

One setup per Y face that has features (0, 1 or 2 setups).

#### Op 2 — G55, second vise, standard hard jaws on parallels. Origin: top-left-back corner of the PART.

1. Put the joined strip in with the Op 1 face on the parallels. A **fixed stop** locates X, and Y and
   Z do not move between cycles. The jaws clamp **any flat, parallel, Y-facing surfaces inside the
   grip band.** These do not have to be the outer contour; a rectangular step or boss works.
   - **Grip height:** as deep as possible without risking the jaws. The jaws are about 1.75" deep.
   - The jaw top must sit **below the lowest Op 2 cut, including the ball edge-break passes**, with
     clearance. The ball dips slightly below any edge it breaks, so the part's top edge can never be
     flush with the jaw top.
   - Formula: `grip = min(1.75, lowest_op2_cut_height - 0.030)`, measured from the Op 1 face
     **[A-17]**. The grip must be at least 0.1875" (3/16").
2. Face the hat off with the face mill. This frees the parts. (For partial-depth parts, rough away the
   leftover material and separate the parts here instead.) They stay put because every part is
   clamped from both sides. (This is why there is only ever **one row**: with two rows, the parts
   next to the air gap between rows would fall out once the hat is gone.)
3. **Set Z by measurement, not by probe:** take a pass, measure the part thickness, adjust, and cut
   again.
4. Probe X (on the end wall finished full depth in Op 1) and Y.
5. Machine the Op 2 features. **Op 2 can machine anything above the top of its jaws**: steps,
   contours, pockets, bores, countersinks. It cannot go below the jaw top, so it cannot reach full
   depth the way Op 1 can.
   - **The one thing to avoid is a blend.** If one continuous wall is finished partly in Op 1 and
     partly in Op 2, it looks bad. Features that don't have to blend exactly are fine; alignment
     error is under 0.001".
6. Edge breaks on the Op 2 side with the 1/4" ball. This depends on the near-perfect alignment; on a
   misaligned part, it would destroy the part.

#### Per-part setups — only if X faces have features

Features on an X face can't be reached until the parts are separated. **The bar method is still
used**, because Op 1 and Op 2 remain much faster. After Op 2, each part is processed one at a time
for its X-face features, at the same speed as the pure one-at-a-time method.

### 1.5 Is the bar strategy viable? (hard gates)

Evaluate these **for each candidate orientation** (section 1.6). If any gate fails, that orientation
is out. If every orientation fails, the part is not a bar part. Report which gate failed, with the
numbers.

| # | Gate | Rule |
|---|---|---|
| G1 | Quantity | order quantity >= 2 x parts_per_bar. Fewer than two bars' worth does not justify the setup. |
| G2 | Parts per bar | parts_per_bar >= 2. Whether 2 or 3 per bar pays off is a cost question, not a gate: compare against one-at-a-time. |
| G3 | Split depth | split depth <= k x D, where k = 5 (aluminum, plastics), 4 (steel), 3 (hard materials such as 304 SS). Try D = 0.250" first, then 0.375" (wider gap, [A-1]). Otherwise the part is too deep for this strategy. |
| G4 | Op 2 holdable | grip = min(1.75, lowest Op 2 cut height - 0.030) is at least 0.1875", **and** inside that grip band there is a pair of flat, parallel, opposing Y-facing surfaces. If not, the orientation needs **custom soft jaws** or another strategy. Flag it; do not silently pass it. |
| G5 | Span window | the span along X extends past the jaws at both ends (at least 6.0" + 2 x min_end_overhang) **and** the end part's held fraction in Op 2 is at least 50%. See 1.5.1. |
| G6 | Stock | a stock size exists per section 1.5.2. |

Blends (section 1.6, step 4) are **not** a gate. They are a heavy penalty, because some features
don't need to blend exactly.

#### 1.5.1 Parts per bar, gap, and span

For a candidate orientation, with part length `L` along X, jaw length `J` = 6.000", and gap `g`:

```
span(N, g)     = N * L + (N - 1) * g
overhang       = (span - J) / 2                   # per end; row centred on the jaws
held_fraction  = (L - overhang) / L               # end part, in Op 2 (after the hat is gone)
stock_X        = span + 2 * 0.050                 # [A-7]
```

Procedure:
1. Start with `g = 0.270`. For each N >= 2, compute the span.
2. Keep an N only if `overhang >= min_end_overhang` (0.050" **[A-8]**) and `held_fraction >= 0.50`.
3. **If the span is just short of the minimum overhang, widen the gap** within 0.270–0.300" to reach
   it (no extra roughing). A gap above 0.300" is allowed but adds slot roughing time.
4. Among valid N, prefer `held_fraction >= 0.75`, then more parts per bar.

**Worked example:** aluminum, 1.500" along X.
- N = 3: span 5.04" is inside the jaws, so it fails.
- N = 4: span 4(1.500) + 3(0.270) = 6.810", overhang 0.405", held fraction (1.500 - 0.405)/1.500 =
  **73%**. That is workable, just under optimal. The owner confirms this case is OK.

**Worked example:** aluminum, 1.000" along X.
- N = 5: span 6.080", overhang 0.040", short of 0.050". Widen the gap to 0.280": span 6.120",
  overhang 0.060", held fraction 94%. Five per bar, no extra roughing.

#### 1.5.2 Stock size

- **Z:** the required minimum depends on how deep Op 1 cuts.

  ```
  skim = 0.010; overcut = 0.010; jaw_clearance = 0.005; jaw_step = 0.100
  op1_depth = depth of Op 1's deepest finished profile below the finished Op 1 face (overcut NOT included)
  stock_Z_min = max( part_Z + 2 * skim,                                        # partial-depth: skim both faces
                     skim + op1_depth + overcut + jaw_clearance + jaw_step )   # Op 1 cuts clear the jaws
  # Full-depth part: op1_depth = part_Z  ->  stock_Z_min = part_Z + 0.125 EXACTLY. Test this.
  # overcut here is the 0.010 MINIMUM. Never size stock with the 0.030 optimum, or +0.125 stock gets rejected.

  # After choosing a standard stock size:
  headroom        = stock_Z - skim - op1_depth - jaw_step      # room between part bottom and jaw top
  planned_overcut = min(0.030, headroom - jaw_clearance)       # 0.030 optimal; >= 0.010 guaranteed by sizing
  ```

  - **Continuous vertical walls** (Op 1 cuts to the part bottom): `op1_depth` = part Z, so the
    second term governs and gives exactly part Z + 0.125". That is the absolute minimum; it can never
    be less, and it must never be pushed higher by extra margins.
  - **Partial-depth parts** (Op 1 stops short): the first term governs, and the stock is just the
    part plus a cleanup pass on each face.
  - Round **up** to a standard size. The owner prefers the smallest standard size that works; a
    larger size is fine if its price is no worse.

  **Worked example (pyramid on a square base, aluminum):** base 2.000" x 2.000" x 0.500", pyramid
  1.000" tall on top, so part Z = 1.500". Op 1 = base side.
  - `op1_depth` = 0.500".
  - `stock_Z_min` = max(1.500 + 0.020, 0.010 + 0.500 + 0.010 + 0.005 + 0.100) = max(1.520, 0.625) = **1.520"**, then
    round up to standard.
  - Always applying the hat would have required 1.625".

  **Worked example (full-depth block):** 1.000" tall part with continuous walls. `op1_depth` = 1.000".
  `stock_Z_min` = max(1.020, 0.010 + 1.000 + 0.010 + 0.005 + 0.100) = **1.125"** exactly, so 1.125" stock is accepted.
  - With 1.125" stock: headroom = 1.125 - 0.010 - 1.000 - 0.100 = 0.015"; planned overcut = min(0.030, 0.010) = 0.010".
  - With 1.250" stock: headroom = 0.140"; planned overcut = 0.030" (optimal).
  - Op 2 grips the base. The lowest Op 2 cut is the edge break where the pyramid meets the base top,
    at 0.500 - 0.007 = 0.493" above the Op 1 face. Grip = min(1.75, 0.493 - 0.030) = 0.463", at least
    0.1875" ✓.
- **Y:** round **up** to a standard size. A 2" part takes 2.125", 2.25" or 2.5" stock, smallest
  preferred. Nominal-size stock equal to the part (2" for a 2" part) is allowed **only** when the
  stock's tolerance is plus-only. Stock sold as +/- is not safe to size to the part.
  - The minimum Y allowance is 0.125" **[A-2]** (from the owner's 2" to 2.125" example).
- Use the stock catalogue (`app/cost/stock_catalog.py`) for standard sizes and tolerance type. If the
  catalogue lacks tolerance data, treat the stock as +/- and say so.
- **X:** span + about 0.10", cut from long bar.

### 1.6 Orientation — choosing the Op 1 face (the key decision)

> **Rule 1: Never use the uploaded orientation.** The CAD file's axes reflect how the part was drawn,
> not how it should be held.
>
> **Rule 2: Do NOT assume Op 1 should do most of the work.** This is a trap that catches experienced
> machinists too. Op 1 only *has* to face, split and contour. Op 2, or the Y-face setups, may be the
> better place for most of the features. A common correct answer is to machine the *simple*,
> rectangular side first, so it becomes the holding surface for Op 2, and put the complicated,
> unholdable side in Op 2.
>
> **Rule 3: Plan backwards from workholding.** First ask "how will this part be held in Op 2 and in
> the Y-face setups?" The answer usually decides the Op 1 face. Sometimes the right orientation looks
> unconventional, such as the part on its side.

#### 1.6.1 Candidates

1. Align the part to its own machining frame: dominant planar faces and principal axes, not the
   file's world axes.
2. Enumerate **12 candidates**: 3 axes x 2 signs for the Op 1 face (6), times 2 choices for which
   remaining axis runs along the bar. Side-lying orientations are included by construction.

#### 1.6.2 Evaluate each candidate

1. **Op 2 workholding (G4).** Put the Op 1 face down. The grip band runs from the Op 1 face up to
   `min(1.75, lowest Op 2 cut height - 0.030)`. Look for flat, parallel, opposing Y-facing surfaces
   inside that band: the outer contour, or a rectangular step or boss. Remember the lowest Op 2 cut
   includes ball edge breaks on Op 2-side edges.
2. **Reach.**
   - Op 1 can reach every surface visible from +Z, down to just above the Op 1 jaw top.
   - Op 2 can reach every surface visible from -Z that lies **above the Op 2 grip band**.
   - Y-face setups can reach surfaces visible from +Y or -Y.
   - Per-part setups can reach X-face features.
   - Assign every feature to the earliest setup that can reach it completely. Anything no setup can
     reach completely means soft jaws, a special fixture, or another strategy. Flag it.
3. **Split depth (G3)** and **span and held fraction (G5)**.
4. **Blends.** Find continuous surfaces (one planar or cylindrical face) whose finishing would be split
   across two setups, for example a wall that is only partly inside Op 1's reach and partly inside
   Op 2's. Each blend is a heavy penalty. It is acceptable only on surfaces that don't need an exact
   match.
5. **Count setups:** Op 1 + (Y faces with features: 0–2) + Op 2 + (per-part setups x quantity, if any X
   face has features).

#### 1.6.3 Rank the surviving candidates

The best ranking is by **estimated total job cost** (setup time + cycle time + per-part handling +
stock cost), using the quote engine for every candidate. If a full cost estimate isn't available,
use this order **[A-14]** (config list, owner to confirm):

1. Fewest per-part setups (no X-face features).
2. No blends on surfaces that must match.
3. Fewest total setups.
4. Op 2 held fraction >= 75%.
5. Most parts per bar, least stock cost, no slot roughing.
6. Shallower split depth (1/4" tool rather than 3/8").

#### 1.6.4 Output (must be explainable)

- The chosen transform from the uploaded frame, the Op 1 face, and the bar-axis direction.
- The setup sequence, with the features assigned to each setup and the Op 2 holding surfaces used.
- N, gap, span, overhang, held fraction, stock X x Y x Z, and splitting tool diameter.
- Flags: blends, soft jaws needed, unreachable features, assumed values that decided the outcome.
- **Every rejected candidate, with the gate or ranking criterion that eliminated it.** The owner has
  to be able to see *why* one orientation won.

### 1.7 Non-rectangular parts

- The split becomes a **contour around each part**, with the part gap as the minimum wall-to-wall
  distance.
- **Always a single row.** Two rows would let parts fall out in Op 2 (section 1.4).
- Shapes that nest better alternated (e.g. triangles) can alternate orientation along the row.
  That requires **custom soft jaws** designed for the alternating layout. Flag it, and include soft
  jaw cost.
- If the part is irregular on every side, with no holdable parallel faces anywhere, it needs custom
  soft jaws or a different strategy, whichever is cheaper.

### 1.8 Pitfalls

1. **Putting most features in Op 1 by default.** Plan from workholding instead (section 1.6, Rule 2).
2. **Capping the span at 6.0".** The span must be *longer* than the jaws.
3. **Using 0.250" as the gap.** The nominal gap is 0.270", widenable to about 0.300".
4. **Taking stock height from the wrong axis.** Stock Z comes from the Op 1 direction *after
   orientation*.
5. **Thinking Op 2 can't do steps or contours.** It can, above its jaw top. What it must avoid is
   blending a surface with Op 1.
6. **Requiring Op 2 to hold the outer contour.** Any flat, parallel Y-facing pair in the grip band
   works.
7. **Putting the hat side against the fixed jaw in a Y-face setup.** Always the machined Op 1 face.
8. **Rejecting the bar method because of X-face features.** Still use it, and add per-part setups.
9. **Sizing stock at nominal size** when the stock tolerance is +/-.
10. **Getting the hat rule wrong in either direction.** Below 0.125" when Op 1 cuts to the part bottom
    is never allowed, and adding margin above the exact 0.125" budget (0.100 + 0.010 + 0.010 + 0.005) wrongly rejects valid +0.125" stock. The mirror mistake: using 0.010" overcut when the stock has room. Use 0.030" whenever it fits. But forcing a 0.125" hat onto a partial-depth part wastes stock; a cleanup pass
    is enough there (section 1.5.2).
11. **Letting the Op 2 part top sit flush with the jaws.** The ball dips below the edges it breaks.
12. **Guessing units** with a "> 10 means mm" heuristic.

### 1.9 Vise layouts — current and planned

**Do not hardcode "one 6-inch vise."** Model the workholding as config: the number of vises, stations
per vise, jaw length and jaw depth, so the layouts below can be added without rewriting the evaluator.

| Layout | Status | What it changes |
|---|---|---|
| Single vise per op (Op 1 vise, Op 2 vise) | **current** | Everything in this document. |
| **Double-station vise** | **planned by the owner** | Parallelized bar: two stations per vise. One planned use is Op 1 in one station and Op 2 in the other, so each cycle loads a fresh bar and unloads a finished row. Roughly doubles throughput per cycle. |
| **Several double-station vises in a row** | idea | e.g. about 3 vises lined up: Op 1 in one set of jaws, Op 2 in the other. Also allows longer bars spanning several vises. **[Q-J]** Rules for a bar spanning the gaps between vises are undefined. |
| **Tabbed plate (2D), then run as bars** | idea, under evaluation | See 1.10. |
| Fixture plate / vacuum | high volume only | Not in scope for DFM now. |

### 1.10 Idea under evaluation — tabbed plate in Op 1, then bars

**Not for implementation yet. Recorded so it is not lost.**

**Concept (owner):** Op 1 machines several rows from a plate, leaving **tabs between the rows**.
The tabs are broken, and each row then runs as an ordinary bar through the Y-face setups and Op 2.

**Analysis so far:**
- **Why it would pay off:** Op 1 load, facing, probing and tool changes happen once per plate
  instead of once per bar. Op 2 is unchanged (still once per row), unless combined with a
  double-station vise.
- **Put the tabs in the hat height only** (below the part bottom). The broken tab stubs then sit on
  the hat, which Op 2 faces off. **A stub on a finished Y face would be a real problem:** Y faces are
  the Op 2 clamping surfaces and the reference against the parallels in Y-face setups.
- **Inner rows are held only by the tabs in Op 1.** The stepped jaws grip just the plate's two outer
  edges, 0.100" deep. That limits plate width, and a wide plate can bow or chatter in the middle.
  Material removal across a wide plate can also release stress and warp it.
- Inner-row Y faces can still be finished to part bottom + overcut, same as outer rows. Below the
  plate's middle is air, so the row-separation cut can go through the full depth except at the tabs.
- After the tabs are broken, each row keeps its own internal alignment, which is all Op 2 needs.
  Alignment between rows is lost, but nothing depends on it.
- **Still open:** maximum plate width for 0.100" stepped-jaw grip; tab size, count and placement;
  whether rows need a sub-plate or spoilboard under the middle.

---

## Part 2 — Edge Breaks

### 2.1 Tools

| Tool | Use |
|---|---|
| **1/4" ball end mill** (1/4" ball tip) | The universal edge-break tool. It can break edges on steep and sloped surfaces as well as flat ones. Also the default for countersinks, large chamfers, and chamfers on holes too big to spot, as a 3D surfacing or contour pass: slower, but it hits size on the first try. |
| **1/8" ball end mill** | Fallback wherever the 1/4" ball can't reach. |
| Chamfer mill | Only when the ball would be too slow: high-quantity large countersinks or large chamfers. |
| **120 degree carbide spot drill, 3/8" or 1/2"** | Centers every HSS-drilled hole. On smaller holes the spot also forms the hole-edge chamfer. |
| Finishing end mill | Cuts the modeled vertical corner radii and chamfers during the normal finishing contour. |

### 2.2 What gets modeled in CAD, and what does not

| Edge | Modeled in the CAD model? | How it's cut |
|---|---|---|
| Vertical outside corners of a contour | **Yes — fillet, 0.020"** (default) | Finishing end mill, normal contour pass |
| Vertical corner where a contour wall continues flush into a wall of a different contour level (section 2.3, D3) | **Yes — chamfer, 0.015"** (default) | Finishing end mill, normal contour pass |
| Horizontal and sloped edges (top edges of contours, pocket rims, edges on steep walls) | **No — do not model them** | 1/4" ball edge-break pass |
| Hole edges | No | Spot drill or ball (D4–D6) |

### 2.3 Rules

**D1 — Ball edge break** (horizontal and sloped edges): run the 1/4" ball along the edge to take off
**0.005–0.007"**.
- **Terminology:** this is *not* a true 45 degree chamfer. A 1/4" ball leaves a tiny concave, cusp-like
  break. At this size the ball's radius is so much larger than the break that the difference can't be
  seen.
- In code and UI call it an **edge break**, not a chamfer, so it isn't confused with a modeled chamfer
  or a chamfer-mill operation.

**D2 — Vertical corner radius:** every vertical outside corner of a contour gets a modeled fillet,
**0.020"** by default. The finishing contour cuts it. No separate operation.

**D3 — Step-transition chamfer (avoids a blend mark):** when one contour sits on top of another and a
wall of the upper contour is flush with (continues) a wall of the lower contour, the vertical corner
where that flush wall turns inward gets a **0.015" chamfer instead of a fillet**. A fillet there
leaves a blend mark on the continuous wall where the two contour passes meet.
- **Reference picture (owner's screenshot, sizes exaggerated):** a large rectangular block with a
  smaller block on its back-left corner, so two of the small block's walls are flush with the large
  block's walls.
  - The two corners where the small block's flush walls turn inward are **chamfered**.
  - The shared outer corner (flush on both sides, continuous full height), the small block's
    freestanding corner, and all the large block's corners are **filleted**.
  - The top horizontal edges are **not modeled**; the ball breaks them.

**D4 — Drilled holes (HSS):** always spot first with the 120 degree spot drill for centering. On holes
small enough, spot deep enough to also form the edge break: **spot diameter = drill diameter +
0.007"**. It depends on the part and drill, and the owner is still fine-tuning it, so keep it in
config.

**D5 — Tapped holes:** spot diameter = **tap major diameter + 0.010"**.

**D6 — Holes as large as the spot drill, or larger:** a plunge can no longer form the chamfer. Do a
**shallow centering spot**, drill, and then break the edge with the **1/4" ball**. The cut-over is
reached when the required spot diameter is at least the spot drill diameter (3/8" or 1/2", whichever
spot drill is in the program).

**D7 — Countersinks and large chamfers:** 1/4" ball 3D surfacing by default. Use a chamfer mill only
when quantity x size makes the ball too slow.

**D8 — Reach:** where the 1/4" ball can't reach (narrow slots, small inside features), step down to the
**1/8" ball**. Where even that can't reach, flag the edge.

### 2.4 Scale

Edge breaks scale with the part and, more importantly, with its features:

| Largest part dimension | D1 ball edge break |
|---|---|
| under 1" | 0.005" |
| 1" and up | 0.007" |

- Defaults: D2 corner fillet 0.020", D3 step chamfer 0.015".
- **Feature-dependent:** long, thin parts and large parts with small features look better with
  **smaller** breaks, radii and chamfers. Scale to the local feature size, not only the part envelope.
  **[A-15]** For features under about 0.25", use about half the default.

### 2.5 Things to watch for

- A 120 degree spot makes a 120 degree included-angle edge, not a 90 degree countersink. A drawing
  callout for a 90 degree countersink cannot be spot-drilled; use the ball (D7).
- Op 2 ball edge breaks depend on the bar method's near-perfect alignment. On a separately fixtured,
  unprobed part, they are a scrap risk.

---

## Part 3 — Open Questions (waiting on the owner)

| ID | Question |
|---|---|
| Q-J | Bars spanning several vises in a row: rules for parts over the gaps between vises (future layout). |
| A-14 | Confirm the fallback ranking order in section 1.6.3 (used only when a full cost estimate isn't available). |

**Resolved in v4:** (Q-R) partial-depth parts still have their two outermost X end faces cut through
the full stock depth in Op 1, so X can be probed in Op 2; Y comes from the fixed jaw. (A-16) replaced
by the owner's Z budget: 0.010" skim, 0.010" overcut, 0.005" jaw clearance, 0.100" grip = 0.125".
(A-3) Overcut is 0.030" optimal when the stock leaves room above the jaws, 0.010" minimum.
(A-17) 0.030" Op 2 clearance accepted as the default.

**Resolved in v3:** partial-depth separation (Op 2 roughs away and separates the rest); spot
oversize is 0.007" on diameter; Op 2 jaw depth is about 1.75", with the grip limited by the lowest
Op 2 cut including edge breaks; the held fraction is the end part's length inside the Op 2 jaws.
