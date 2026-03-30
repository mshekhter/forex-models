## Osler-only outline. 

### Scope and integration boundary

This stays inside the existing notebook scaffold.

- We do not create a new signal universe.
- We keep the current entry-time rows.
- We compute one Osler state record per entry row.
- We use only information available at bar \(t\).
- No confirmation window.
- No post-entry features.
- No alternate methodology folded in.

The primary bar-only path here is barrier interaction with round-number proximity and rejection versus breach geometry, computed at entry time.

### Source hierarchy to govern the outline

The method is organized by the PDF, but the mechanism is governed by Osler’s published findings:

- support and resistance can predict intraday trend interruptions
- round numbers matter disproportionately, especially levels ending in 0 or 5
- take-profit and stop-loss clustering around round numbers creates two different behaviors:
  - reversal near levels
  - acceleration after crossing them
- stop-loss buys cluster just above major round numbers
- stop-loss sells cluster just below major round numbers
- take-profits cluster more directly at the round numbers themselves

### Row universe and causal computation boundary

For every existing entry row:

- build a dense Osler feature vector
- compute all features from bars up to and including \(t\) only
- attach event-state flags, but do not discard the row
- allow many rows to be neutral or weak-state rows

This means feature construction is dense, while named Osler events are sparse. Coverage is preserved at the row level. The feature engine and event logic are framed this way, not as a mandatory conjunction gate.

### Base bar-state section

This is the shared primitive block used by all Osler families.

Per entry bar \(t\):

- chosen close proxy used consistently with the notebook
- high, low, open, close
- log return
- log range
- CLV
- body size
- upper wick size
- lower wick size
- full range
- optional deterministic OHLC proxies only if needed for stability

Role:

- CLV is central for same-bar rejection versus acceptance
- wick and body geometry matter for failed break versus accepted break
- range and return feed normalization and scale control

Explicitly include CLV, log range, and OHLC-derived volatility primitives in the barrier engine.

### Objective barrier lattice

This is the first structural family.

For each lookback \(k\):

- resistance \(R_t(k)\) from prior bars only
- support \(S_t(k)\) from prior bars only
- barrier width from \(S\) to \(R\)
- barrier midpoint
- distance from current close to resistance
- distance from current close to support

Rules:

- barriers are defined from bars strictly before \(t\)
- current bar tests interaction with already-existing barriers
- use multiple \(k\) values, not one level

Align with rolling support/resistance setup and its multi-scale barrier recommendation.

### Round-number lattice as a separate first-class family

This is not just a modifier on barriers. It is its own family.

For each round-number step \(s\):

- nearest round-number distance
- signed distance to nearest round number
- nearest upper round number
- nearest lower round number
- distance to upper number
- distance to lower number
- within-band flag around nearest number

Hierarchy:

- major levels first
- minor levels second

For EUR/USD, freeze the hierarchy conceptually as:

- 00 and 50 endings as major
- 0 and 5 endings as broad technical endings
- smaller step grids only as later sensitivity variants

Reason for this change: Osler’s support/resistance paper found disproportionate concentration at levels ending in 0 or 5, and the stop-loss work sharpens this into directional asymmetry around major round numbers.

### Round-number asymmetry block

This is the first augmentation that materially changes the earlier outline.

We must separate three locations around a round number:

- exact-at-number state
- just-above-number state
- just-below-number state

This is side-aware, because the order clustering is asymmetric:

- stop-loss buys cluster above major numbers
- stop-loss sells cluster below major numbers
- take-profits cluster more directly at the numbers themselves

So the feature layout needs separate fields for:

- exact number proximity
- above-number proximity
- below-number proximity
- cross-above-number event
- cross-below-number event
- hold-above-number geometry
- hold-below-number geometry
- fail-at-number reversal geometry

This comes directly from Osler’s order-clustering results and is the main reason the round-number family cannot stay generic.

### Barrier proximity family

This family measures where price sits relative to objective barriers before event classification.

Per scale \(k\):

- raw distance to resistance
- raw distance to support
- signed distance to resistance
- signed distance to support
- nearest-side barrier
- inside touch band flags
- distance-to-barrier rank within current local range
- ratio of resistance distance to support distance

Normalized versions:

- volatility-normalized distance to resistance
- volatility-normalized distance to support
- range-normalized distance to resistance
- range-normalized distance to support

Explicitly treat normalized barrier distance as part of the core barrier interaction engine.

### Barrier interaction state family

This is the first event-state block on objective barriers.

Per scale \(k\) and tolerance delta:

- touch resistance
- touch support
- breach up through resistance
- breach down through support
- touch without breach at resistance
- touch without breach at support
- outside close above resistance
- outside close below support
- inside close after resistance touch
- inside close after support touch

This is the exact interaction vocabulary already implied in the PDF pseudocode and feature table.

### Exact round-number event family

This is the new parallel event family, separate from objective barriers.

Per round-number step \(s\):

- exact-number touch
- exact-number stall
- exact-number rejection
- exact-number cross
- exact-number close-through
- exact-number return-inside
- exact-number hold-above
- exact-number hold-below

Directional interpretation:

- exact-number rejection is the take-profit or level-defense side
- exact-number cross-and-hold is the setup for possible cascade continuation

This family exists because Osler’s mechanism is not only rolling barriers. It is also explicit order clustering around round numbers themselves.

### Rejection geometry family

This is the primary reversal family.

#### 11.1 Resistance rejection geometry

- touched resistance but no valid breach
- close back inside below resistance
- CLV negative
- upper wick size
- upper wick fraction of range
- rejection depth from touched high back to close
- rejection depth normalized by range
- rejection depth normalized by local volatility
- body direction against the attempted break
- close distance back below resistance
- failure-to-hold-above flag

#### 11.2 Support rejection geometry

- touched support but no valid breach
- close back inside above support
- CLV positive
- lower wick size
- lower wick fraction of range
- rebound depth from touched low back to close
- rebound depth normalized by range
- rebound depth normalized by local volatility
- body direction against the attempted break
- close distance back above support
- failure-to-hold-below flag

Directly use rejection at resistance with negative CLV and the mirrored support version as canonical treatment examples.

### Breach and cascade geometry family

This is the primary continuation family.

#### 12.1 Upward breach / cascade geometry

- breach up flag
- close excess above resistance
- excess above resistance normalized by volatility
- excess above resistance normalized by range
- body portion above resistance
- fraction of full range above resistance
- CLV near bar high
- distance from close to next round number above
- breach near major round number
- breach through major round number
- hold-above-number geometry

#### 12.2 Downward breach / cascade geometry

- mirrored support version
- close excess below support
- normalized overshoot
- body portion below support
- CLV near bar low
- distance to next round number below
- breach near major round number
- breach through major round number
- hold-below-number geometry

This is the coding form of Osler’s cascade mechanism: trends accelerate after levels are crossed, especially where stop-loss-dominated order flow is activated.

### Acceptance versus failed-break family

This stays same-bar and fully mechanical.

For any apparent upside break:

- outside-close strength
- close-to-barrier hold distance
- adverse wick fraction
- body agreement with break
- outside fraction of range
- minimal overshoot versus meaningful overshoot
- accepted-break score

For any apparent downside break:

- mirrored version
- accepted-break score

For failed breaks:

- touched and marginally crossed but closed weak
- crossed with CLV contradiction
- crossed with large opposing wick
- crossed but with tiny normalized overshoot
- re-entry risk score

This refines breach events into likely continuation versus likely failed break without using future bars. It is consistent with the researched breach, strong close, and rejection-versus-acceptance framing.

### Persistence and continuity family

This is the second material augmentation.

Earlier freshness was too narrow. The family should include both freshness and persistence.

Per side and scale:

- bars since last touch
- bars since last breach
- first-touch flag
- touch count in recent window
- breach count in recent window
- consecutive bars barrier remained unchanged
- consecutive bars barrier stayed active near price
- barrier age since first establishment
- barrier drift since first establishment
- repeated-attack count
- recently-defended count

Interpretation:

- fresh untouched levels may reject differently from stale recycled ones
- repeatedly attacked levels may be more vulnerable to break
- persistent unchanged levels may carry more structural meaning than drifting ones

This is aligned with the barrier freshness concept, and with Osler’s evidence that published levels were stable and predictive enough to matter beyond a single instant.

### Barrier and round-number confluence family

Confluence stays, but it becomes more structured.

Per row:

- objective barrier plus major round number confluence
- resistance plus exact-number confluence
- support plus exact-number confluence
- resistance rejection plus exact-number confluence
- support rejection plus exact-number confluence
- upside breach plus above-number confluence
- downside breach plus below-number confluence
- multi-scale resistance confluence count
- multi-scale support confluence count
- major-round-number plus strong-close confluence
- persistent-level plus round-number confluence

This family is important, but it cannot be the only source of tradeability. It is a strengthening block, not a mandatory all-or-nothing gate. The PDF itself warns that multi-scale simultaneous states can become sparse.

### Local excursion and approach family

Keep this only as Osler support, not as a separate methodology.

Per scale \(k\) near each active barrier:

- window max
- window min
- current close position in recent window
- directional excursion ratio
- excursion versus net displacement
- directedness of approach into barrier
- compressed approach versus expansive approach
- barrier-side excursion asymmetry

Use:

- distinguish clean drive into a level from noisy drift
- distinguish absorbed rejection from accepted continuation
- refine same-bar interpretation of touch and breach

Explicitly tie excursion and continuation geometry to barrier mechanics and rejection versus continuation states.

### Conditioning block

This remains secondary, not a separate method.

Conditioners only:

- local volatility proxy
- realized range
- semivariance positive
- semivariance negative
- semivariance imbalance
- current bar range percentile relative to recent history

Role:

- normalize distances and overshoots
- stabilize thresholds
- identify fragile high-volatility states
- optionally support later abstention logic

Explicitly address that semivariance should be treated primarily as a state conditioner rather than a standalone directional signal, and range-based estimators are there to stabilize the barrier engine.

### Mechanical-only strength policy

This needs to be explicit in the outline.

We do not use discretionary barrier strength labels. Strength can only mean measurable geometry or persistence, such as:

- normalized overshoot
- CLV
- wick/body structure
- persistence length
- touch history
- confluence count
- accepted-break geometry

That correction is important because Osler’s support/resistance work did not make discretionary textual strength labels a reliable foundation. The model should stay mechanical.

### Event taxonomy to freeze before specs

Core event classes:

- `resistance_rejection`
- `support_rejection`
- `upside_barrier_breach_acceptance`
- `downside_barrier_breach_acceptance`
- `upside_barrier_failed_break`
- `downside_barrier_failed_break`
- `exact_round_rejection_upside_attempt`
- `exact_round_rejection_downside_attempt`
- `cross_above_major_round_hold`
- `cross_below_major_round_hold`
- `cross_above_major_round_fail`
- `cross_below_major_round_fail`
- `neutral_barrier_touch_resistance`
- `neutral_barrier_touch_support`
- `neutral_round_touch`
- `no_named_osler_event`

Important:

- every row still gets features
- event labels are just structured summaries of the current-bar state
- a row may have multiple event flags across scales, but the row is still one row

### Notebook block layout

Freeze the outline into these notebook sections:

- A. `osler_base_bar_state`
- B. `osler_objective_barrier_lattice`
- C. `osler_round_number_lattice`
- D. `osler_round_number_asymmetry`
- E. `osler_barrier_proximity`
- F. `osler_barrier_interaction_states`
- G. `osler_exact_round_events`
- H. `osler_rejection_geometry`
- I. `osler_breach_and_cascade_geometry`
- J. `osler_acceptance_vs_failed_break`
- K. `osler_persistence_and_continuity`
- L. `osler_barrier_round_confluence`
- M. `osler_local_excursion_and_approach`
- N. `osler_conditioners`
- O. `osler_current_bar_event_taxonomy`

### What this outline deliberately does not do yet

Not in this outline:

- final feature names
- final formulas for every field
- parameter grids
- model choice
- label choice
- abstention logic
- validation spec

This is just the structural outline the later specs will hang from. then code. This is as far as I think I can go in public repo.
This should be enough for anyone to take, tailor and build their own approach and code.