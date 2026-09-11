# DER program terms and what each predicts for the cloud-anomaly response

Assembled 2026-09-11 from Rule 31 (Scheduled Dispatch Program), the Battery
Bonus Q&A of 2023-10-27, and the PUC/Hawaiian Electric program fact sheets.
Sources at the foot. This is a hypothesis framework, not an estimated result.

## What the tariffs actually say

| program | open to new | midday export | compensation | closed |
|---|---|---|---|---|
| NEM | to Oct 2015 | yes | full retail netting | 2015 |
| NEM Plus | overlay | added capacity non-export | none for the addition | |
| CGS Customer Grid-Supply | 2015-2017 | yes | fixed, roughly half retail | 2017 |
| CSS Customer Self-Supply | 2015-2024 | **no, ever** | none | 2024-03-29 |
| CGS Plus | 2019-2024 | yes, curtailable | lower than CGS | 2024-03-29 |
| Smart Export | 2019-2024 | **no credit 9am-4pm**; 14.97 c/kWh 4pm-9am on Oahu | time-differentiated | 2024-03-29 |
| Battery Bonus (SDP) | 2021-07 to 2023-12 | overlay, keeps underlying tariff | $850/kW once, $5/kW-month, 10 yr | 40 MW Oahu cap filled |
| Smart Renewable Energy | 2024- | export and non-export variants | | current |

## Battery Bonus, from Rule 31 rather than inference

- Eligibility is a battery "charged from an Eligible Customer-Generator's owned
  or leased Generating Facility" under NEM, CSS, CGS, CGS Plus, Smart Export,
  SRE or a Standard Interconnection Agreement. **It is an overlay: the customer
  keeps their underlying export tariff.**
- The operator "shall be required to manage their Battery Storage Facility to
  automatically prioritize battery charging during periods of substantial solar
  panel insolation in order to most reliably serve the two-hour battery
  discharge commitment."
- Discharge is the Committed Capacity for two consecutive hours daily, in a
  dispatch period the Company sets within 6:00-8:30pm. Discharged energy may
  serve onsite load or be exported.
- Persistent non-performance after 30 days' notice can draw up to $150/month.

So the rule points charging at midday solar and defines the battery as charged
from the customer's own PV. It does not, in the text located, explicitly forbid
grid charging, and the penalty gives a reason to top up on a dark day. MJR's
conjecture that dark days force grid draw is consistent with the incentives but
is not established by the tariff language. Rule 31 section C.3 begins
"Notwithstanding any other provision specified in the underlying Generating
Facility's governing program tariff", which is where an explicit permission
would sit if one exists; worth reading in full before relying on either reading.

## What each program predicts for the response of metered load to sunshine

Write the response as the change in grid-visible load per unit of cloud anomaly.

**NEM is the clean case.** Export is netted at retail, so the meter falls by the
full solar increment whether the energy serves load or leaves the property.
There is no reason to self-consume rather than export. The NEM coefficient is
the closest thing available to a pure physical PV response, and it is the
natural baseline every other program should be differenced against.

**CGS, CGS Plus: partial attenuation.** Export is worth materially less than
avoided purchase, so a customer prefers to consume their own output. Shifting
consumption into the sunny hours reduces how much the meter falls. The response
should be attenuated relative to NEM, and attenuated more under CGS Plus.

**CSS: censored.** No export is permitted at any hour. On a sufficiently sunny
day the meter cannot fall further, so the response saturates. This is a
one-sided nonlinearity: attenuation on sunny days, none on cloudy days.

**Smart Export: a storage-inducing tariff by construction.** Midday export earns
nothing; evening and overnight export earns 14.97 c/kWh on Oahu. A customer
with a battery is paid to move midday output into the evening. So the expected
signature is attenuation at midday and a negative evening coefficient, and it
should appear in the Smart Export cohort *whether or not they are in Battery
Bonus*.

**Battery Bonus: firm evening discharge, solar-prioritised charging.** Because
discharge is contractually fixed at the Committed Capacity every day, the
evening discharge should be roughly invariant to how sunny the day was. That
predicts an evening coefficient near zero, not negative, and puts the whole
sun-dependence in the charging window. If instead dark days force grid charging,
the daytime coefficient turns more negative. The two readings differ in sign in
the daytime window and can be told apart.

**TOU arbitrage.** A small cohort on time-of-use rates could charge from the
grid overnight and discharge in the peak. Under Rule 31 a Battery Bonus battery
is defined as charged from the customer's own PV, so this should be rare there,
and MJR's judgement is that few customers outside the program have worked it
out. If present it would show as a positive overnight coefficient, which is
worth checking against the unexplained positive overnight delta we currently
estimate.

## Why this matters for identification

The storage-versus-vintage problem is that every system installed after 2021Q2
is in a storage program, so the two are the same column. The tariff structure
offers a way around it that does not depend on separating them:

**The censoring prediction is a within-program nonlinearity.** Programs that
cannot export, or are not paid to export at midday, should show attenuation that
is asymmetric in the sign of the anomaly: present on sunny days, absent on
cloudy ones. A vintage effect, a household-composition effect, or declining
marginal effectiveness at higher penetration are all symmetric in the anomaly.
So the asymmetry is a signature of the export constraint specifically, and it is
identified within a cohort rather than across cohorts.

Whether there is enough power to see it is a separate question and unresolved.

## Caveats

- The `era` field in `der_points` is one label per system. Because Battery Bonus
  is an overlay, a system labelled BatteryBonus also sits under NEM, CSS, CGS,
  CGS Plus or Smart Export, and that underlying tariff governs its export
  economics. The current era variable therefore conflates the overlay with the
  underlying tariff.
- The CSS/SmartExport era in the panel bundles a hard non-export program with a
  time-differentiated one. They agree at midday and diverge in the evening:
  Smart Export customers are paid to export then, CSS customers cannot. The
  bundle is defensible for a midday prediction and not for an evening one.
- Rates quoted are Oahu and as of the fact sheets cited; they have been revised.

## Sources

- Rule 31, Emergency Demand Response Program Rider: Scheduled Dispatch Program.
  https://www.hawaiianelectric.com/documents/billing_and_payment/rates/hawaiian_electric_rules/31.pdf
- Battery Bonus Q&A, updated 2023-10-27.
  https://www.hawaiianelectric.com/documents/products_and_services/customer_renewable_programs/battery_bonus_QA.pdf
- Hawaii PUC, Smart Export and CGS fact sheets.
  https://puc.hawaii.gov/wp-content/uploads/2017/10/Hawaii_PUC_Smart-Export_CGS_Fact_Sheets_FINAL.pdf
- Smart Export program page.
  https://www.hawaiianelectric.com/products-and-services/smart-renewable-energy-programs/previous-renewable-programs/smart-export
