# Candidate papers from the Oahu electricity project

Assessment written 2026-09-10 in the report repository session, before the A.11 identification work of 2026-09-10 to 2026-09-12. Item 1 is superseded by docs/FINDINGS_2026-09-12_der_identification.md: the battery estimate it praises did not survive, see that file. Items 2 to 7 are untouched and are the next line of work.

---

I've read through the report structure, the methods appendices, the analysis directory, and the private regulatory memos. Here's my read.

## The main observation

Your appendices contain at least three standalone papers that are currently invisible to the literature. A.11, A.14, and A.15 are each a methods contribution wearing an appendix costume. A referee will never see them, and nobody will cite an appendix of a policy report. That's the biggest publication asset here and the easiest thing to lose.

Below, ranked by what I'd actually do first.

---

## 1. Weather-identified rooftop PV and storage effects on grid load

**The strongest standalone paper in the repository.** (A.11, `analysis/01–18_*.py`)

The identification is the selling point: installed PV, storage, and EV adoption all trend together after 2020 and can't be separated on trend. You use day-to-day radiation variation interacted with installed stocks instead. The battery estimate is the cleverest part — midday radiation predicting *post-sunset* load, where PV output is zero and storage is the only channel from midday sun to evening load. That's a genuine exclusion restriction, not a hand-wave.

What makes it publishable rather than merely competent:

- **A falsification test with teeth.** 0.45 MWh/MWh/day into the evening passes the physical bound of 0.62; the trend-based estimator fails it by 5×. Referees love a bound that kills the naive estimator.
- **The tariff-regime bracket.** 0.79 MW/MW pre-battery (net metering, 2013–19) vs 0.61 in the battery era — the same object measured under two tariff regimes.
- **The behind-the-meter wedge.** 24% of rooftop generation never crosses the meter, stable across 2018–2024, growing 180→290 GWh/yr. This is a measurement result with implications for every DER valuation study and for official generation statistics.
- **The low-sun asymmetry.** Grid load runs ~11 MW *above* linear netting on very low-radiation days in 2021–24, with the opposite sign in 2013–16. Households that self-supply most of the time lean on the grid when the sun fails, and it scales with the fleet. This is a distinct, quotable finding about reliability under high DER penetration.
- **A data-forensics public good.** The FERC 714 clock misalignment — detected on battery-inert pre-dawn hours, validated against astronomical solar noon. Anyone using FERC 714/PUDL hourly data has this bug and doesn't know it.

**Weaknesses to get ahead of:** N=1 territory, no cross-island placebo (FERC 714 covers only Oʻahu), AC correlates with radiation despite the temperature quadratic, and the storage capacity series scales every per-MWh result. The honest framing is that this is a *measurement* paper with credible within-territory identification, not a causal-effects-across-markets paper.

**Outlets:** JAERE is the natural home and the realistic target. JEEM as the alternative. AEJ: Applied if you lead with the identification design and the wedge; AEJ: Policy if you lead with "what is rooftop solar worth to the grid, and what do official statistics miss." I'd send it to JAERE. Energy Journal or Energy Economics if you want speed over placement.

If you want the wedge and the low-sun result read by engineers and system planners rather than economists, that's a separate short piece for *Nature Energy* or *Joule* — but don't split the identification out of the main paper to do it.

---

## 2. The procurement premium and nominal contract rigidity

**The most general-interest economics in the project, and the one with the clearest path to a bigger paper.** (§2.3, §2.8, plus `private/PUC_*`, `private/PBR_INCENTIVE_ASYMMETRY.md`)

You have a mechanism, not just a gap. The gap: matched-configuration Hawai'i PPAs go 7.7¢ (2018–20) → 19.5¢ (Mahi reprice, *same project*), while mainland goes 3.1 → 6.5¢. The common global shock is ~2.5–3.5¢ on the mainland against ~12¢ for repricing an identical Hawai'i project. The excess is procurement-channel-specific.

The mechanism is the paper: **PPAs fix price in nominal dollars at award; award-to-interconnection runs four to seven years; the 2022 inflation spike erodes the real value of every award in the queue.** Developers respond by bidding a risk premium, renegotiating, or walking. Kupehau, Mehana, and Barbers Point cancelled; Mahi survived by tripling its price. That's an incomplete-contracts story with an inflation-risk channel and observable outcomes.

**This generalizes, and that's where the real paper is.** Mainland interconnection queues are now 4–7 years too. With LBNL's national PPA and queue data you could test whether repricing and cancellation hazard rises with (award-to-COD lag × realized unexpected inflation), and whether contracts with indexation survive at higher rates. That's a national paper with a clean prediction, and Hawai'i becomes the extreme case that motivates it rather than the whole sample. **I'd push hard in this direction** — the single-jurisdiction version is an Energy Policy paper; the national version is an AEJ: Policy or JAERE paper.

The institutional layer is genuinely striking and belongs somewhere: the utility designs the RFP, evaluates bids, selects winners, negotiates, and may self-bid, with an Independent Observer that has "no decision-making authority." Created by Commission order, not statute — so reversible by order. Your `PUC_DISTANCE_RATIONALE` memo's finding that the framework texts state *no rationale* for the assignment is the kind of documented absence that makes a regulatory-economics point land.

**Outlets:** National version → AEJ: Policy, JAERE, or RAND (if you sharpen the contracting/IO framing). Hawai'i-only version → Energy Journal or Energy Policy.

---

## 3. PBR's exceptional-project door

**A short, sharp regulatory-economics paper.** (`private/PBR_INCENTIVE_ASYMMETRY.md`)

The three-sentence version in your memo is the abstract: the revenue cap kills Averch–Johnson at the within-cap margin, and the Exceptional Project Recovery Mechanism restores full cost-of-service treatment case by case for anything large enough to qualify — where one approved project outearns the entire performance-incentive portfolio in a good year. That's a clean statement about how PBR regimes leak, and it applies well beyond Hawai'i: most PBR frameworks have an equivalent door.

This wants an empirical leg to be a journal paper rather than a comment — EPRM/MPIR filings and approvals over the PBR period, sized against realized PIM earnings. Your memo flags the numbers as order-of-magnitude pending rate-case verification; that verification *is* the paper's empirical section.

**Outlets:** Utilities Policy or The Electricity Journal reach the regulators who can act on it. Review of Industrial Organization or Energy Journal if you want economics placement. Given that the audience you care about is PUCs, I'd take the regulatory outlet and the speed.

The PURPA argument in `PURPA_AND_PROCESS_LEVERS.md` — no RTO, no organized wholesale market, so the EPAct-2005 market-access exemption arguably shouldn't apply, meaning Hawai'i solar has the strongest untested §210 claim in the country — is a litigation theory, not a paper. It belongs in testimony or a law review with a co-author who litigates, not in an economics journal.

---

## 4. Pricing published plans

**The most novel method here, and the one with the widest downstream use.** (A.15, §4.5)

Taking a published utility IGP or state energy plan, extracting its resource mix, imposing it as a quota band in the same model holding every cost assumption identical, and reporting the difference against the model's own least-cost build — this converts "our plan vs. their plan" from a contest of assumptions into a like-for-like price tag. I don't know of a systematic treatment of it.

The design details are the methodological content, not throat-clearing: the firm-energy floor with no ceiling (so the tag prices the plan *as published*, not the cheaper build a model would pick if allowed to substitute), the fossil bands that relax where the clean-energy requirement binds instead, the Kalaeloa must-run carve-out, and the two validation tests — elastic feasibility pre-check before any cell solves, and a post-hoc fidelity audit. That's a replicable protocol.

**The multi-jurisdiction version is a substantially bigger paper.** Price five or ten states' IRPs on a common method and you can say something about whether published plans systematically depart from least-cost and in which direction. That's a finding with national regulatory consequence.

**Caution:** don't submit until the plan cells land at 0.1%. Two of them are currently time-limited at 0.65% and 0.50%, and A.15 already concedes emissions figures are more tolerance-sensitive than costs. A referee who opens `PLAN_CELLS.csv` will find that.

**Outlets:** Single-jurisdiction → Energy Policy or Utilities Policy. Multi-jurisdiction → Joule, Nature Energy, or AEJ: Policy depending on framing.

---

## 5. Market-implied fuel-price uncertainty in capacity expansion

**A clean methods paper that connects to your own prior work.** (A.14)

Replace the agency reference case with a market-implied distribution: futures strip as central, option-implied volatility for the 10th/90th, TIPS breakevens for the real conversion, held flat beyond the last liquid contract on random-walk grounds. Then solve the full scenario matrix across that band rather than around a point forecast.

Three things make it more than a technique note:

- **The documented case against the reference path.** EIA's own retrospective: 45.6% average absolute error on real imported crude across AEO1994–2022, against ~9% for consumption and electricity prices. Plus the AEO2015–19 over-projection in 18 of 25 comparisons, and Bernard et al. on failure to beat no-change at the 2–8 year horizon where these decisions sit.
- **The theoretical grounding, which is yours.** Hotelling predicts a rising real path; Livernois finds the evidence weak; Berck and Roberts finds difference-stationarity. You're in a position to say the escalator in every agency reference case is a modeling convention rather than an empirical regularity, and to be believed.
- **A non-obvious analytical result.** Because LSFO and LNG pass through Brent at nearly identical rates in energy terms (~0.118 $/MMBtu per $/bbl), the fuel *spread* is nearly invariant to the oil price — $6.56/MMBtu at the 10th percentile against $6.61 at the 90th. So the per-unit conversion saving barely depends on oil; what moves total savings across oil worlds is burn volume and the clean investment cheap gas defers. That inverts the intuition every IRP runs on.

You're already appropriately careful about the risk-neutral caveat (Baumeister and Kilian finding no significant premium, and correcting for one worsening real-time forecasts) and about the linear pass-through breaking down at the low end. Keep that candor; it's what will get it past referees.

**Outlets:** The Energy Journal is the natural home. Energy Economics as the alternative. Resource and Energy Economics if you lead with the Hotelling/random-walk framing.

---

## 6. Solar siting and agricultural land

**A natural fit with your existing identity, and a nationally contested question.** (§2.5, §2.6, plus the `solar-wind-landuse` companion)

The findings travel: every pathway builds nearly the same solar on nearly the same acres; ground rent is a few tenths of a cent per kWh, so land carries no scarcity rent and isn't the binding cost; ≥80% of built solar capacity sits off D/E-rated soils; the 1980 plantation footprint context (50,000 ac, 74% still ag, 78% of LSB-rated acres A–B).

The sharpest generalizable point is the critique in §4.5 and `NREL_SCREEN_COMPARISON.md`: **planning studies inherit a land cap from an undocumented screen choice, never test its sensitivity, and the cap drives the headline.** HSEO's ceiling comes from NREL's PV-Alt-1 — one of twelve screens, criteria published only in NREL's tables — and the neighboring screen that admits military land roughly doubles it. That's a methodological failure mode you can document and that other analysts can check for in their own jurisdictions.

**Outlets:** Land Economics or AJAE, given the farmland-competition framing and your standing there. Energy Policy or ERL for reach. I'd favor AJAE — "does utility-scale solar threaten prime agricultural land" is a live national fight and an ag-econ audience will engage with the soil-rating evidence properly.

---

## 7. The umbrella paper

The whole system study: 500+ scenarios on an isolated grid, finding that procurement cost dominates fuel choice by a multiple, that no new fuel plant pays for itself at any oil price tested, that rooftop lowers cost on every pathway, and that the feared constraints mostly don't bind.

The framing that makes this generalizable rather than parochial: **isolated island grids are where the high-renewable transition happens first and where every constraint binds hardest.** No interconnection, no neighboring balancing area, expensive fuel — so they reach the frontier decades ahead of continental systems. The message that carries is "soft costs and procurement institutions dominate fuel and technology choices," which is a claim about energy transitions generally.

**Outlets:** Joule or Nature Energy for visibility; Applied Energy or Energy Policy as the reliable placement. One caution: a widely-circulated public report with press coverage can complicate Nature-family embargo handling. Worth checking before you pitch, not after.

---

## Weaker candidates, honestly assessed

- **EGS (§3).** The economics is a one-liner — an option with bounded downside and asymmetric payoff, all-or-nothing at the resource cap, dispatch invariant to capital cost. That's a section, not a paper, unless you develop the cultural and social-license dimension in §3.1 into its own piece for *Energy Research & Social Science*. The Puna history makes that a real contribution rather than a courtesy paragraph.
- **Methane / lifecycle boundary (A.10, §4.9).** The leakage break-even literature is crowded. Your differentiator is embedding it in capacity expansion, so the answer depends on what clean investment cheap gas defers — not just on the leakage rate. That's enough for ERL or ES&T, not for more.
- **Reliability and maintenance timing.** This is v2 material, but flag one piece now: maintenance calendars are tuned to the *gross*-load valley while solar has moved the binding hours to low-sun November days, and the Hawai'i Island 2022–24 tight evenings repeatedly caught units on annual maintenance. "How much adequacy does a smarter maintenance calendar buy at zero capital cost?" is a tight, answerable, genuinely underexplored question. Applied Energy or IEEE TPWRS when v2 can support it.
- **Reproducibility infrastructure.** There's a real contribution in encoding must-hold economic relations as automated pre-publication gates — a dominance violation means a bad solve, not a finding. I haven't seen that formalized. But it's a short piece for *Environmental Modelling & Software* or *Energy Strategy Reviews*, and it competes for time with better papers. The corrected FERC 714 + NSRDB + DER install panel would make a decent *Scientific Data* descriptor that gives the identification paper something to cite.

---

## Sequencing

1. **A.11 as a paper, now.** It's the most defensible, it's finished analytically, and the others cite it. Nothing about it waits on the solve queue.
2. **Get the national PPA data and test the nominal-rigidity hypothesis.** This is the highest-upside move in the whole set, and Hawai'i's extreme case is the hook rather than the sample.
3. **A.14 as a methods paper** — low marginal effort, the writing exists, and it's independently citable by anyone running an IRP.
4. **Plan pricing after the plan cells refine**, and decide early whether you're doing the one-jurisdiction version or building the multi-state version. They're different projects.
5. **Umbrella paper** whenever v1 locks.
6. **Land paper** on its own clock with the companion repo.

Two cross-cutting notes. First, the public pre-release with a comment period helps you with economics referees (it reads as adversarial pre-review) but check embargo policy before pitching anything to the Nature family. Second, several of these depend on numbers still in flight — the 14 over-target retries and the plan refinements — so anything citing specific system costs should wait for the lock rather than chase a moving basis.

Want me to draft an abstract and an outline for the A.11 paper? That one is close enough to written that the main work is reframing an appendix as a contribution.