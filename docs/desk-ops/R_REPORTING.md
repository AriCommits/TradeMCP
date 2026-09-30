> **Canon snapshot for TradeMCP** (docs/desk-ops/). Originating path under
> paper-trades: `R_REPORTING.md`. **Paper only** — no live orders; live ops still
> use `/workspace/paper-trades` until wired.

# R-multiple reporting (cross-asset)

## Definition
- **Risk $** at entry = `abs(Entry − Stop) × Qty × multiplier`
  - Options: multiplier **100**
  - Spot / most futures logs: multiplier **1** (if futures size is contracts, use the $ risk you actually defined at entry)
- **R** = `P&L $ ÷ Risk $`

## How we use it
- Compare desks by **avg R** and **sum R**, not raw dollars
- A +2R futures trade equals a +2R options trade in idea quality
- Still show $ P&L for cash reality

## Long options
If no underlying stop, set Stop to a premium invalidation (e.g. 40–50% of entry premium). Then Risk $ ≈ capital at risk on the premium.

## Book check
Weekday Paper book check should include per-desk: open count, $ unreal/realized, and **R on closed trades since last check** when Risk $ is filled.
