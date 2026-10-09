# Hourly production card review

Status: approved for commit and deployment on 9 October 2026. No database migration required.

## Verified production example (read-only live query)

Run 53, reading 30: 9 October 2026, 01:32:56.741521?02:00 UK time.
Standard 120 packs/min; duration 27.054307983 minutes. Target 3,246.516958 packs.
Actual entry: 5 pallets x 220 cases/pallet x 10 packs/case = 11,000 packs.
This is the only reading for this run, not a cumulative total accidentally
used as an hourly count. The target includes the full partial reporting period;
planned downtime was not deducted. Attainment is 338.8%, mathematically correct
for those inputs. No production records have been changed.

Recorded stops: Film Change and Label Change total 1.056 minutes; infeed fault
20.495858 minutes. Notes: infeed jam; cycle chain. Those output and downtime
records imply performance of 1,397.7%, so review is required. The code cannot
establish whether the entered pallet count, 220 cases/pallet, standard or stop
timestamps reflect the physical trial. They need operator verification.

## Calculation contract

- Decimal arithmetic until API serialization. Target = standard x full scheduled
  reporting duration. Partial hours use timestamps, not rounded display minutes.
- Variance = actual - target; shortfall = max(target - actual, 0).
- Display packs as integers and percentages to one decimal. Only the ring fill
  is bounded to 100%; percentages and review flags remain visible.
- OEE uses the same shared module for hourly card and management dashboard.
  Availability = operating / planned production time. Planned production time
  excludes only explicitly configured stop reasons. Operating time subtracts
  unplanned downtime. Interval union and planned precedence prevent double counts.
- Performance = gross output / (standard x operating time). Until gross output
  is captured per period, the user approved palletised output as an explicitly
  provisional basis. Do not reverse-calculate fictitious rejects from 98% quality.
- `PULSE_TRIAL_QUALITY_PERCENT=98` is the provisional trial assumption. Invalid
  or blank configuration makes quality unavailable. This is not measured quality.
- `PULSE_OEE_EXCLUDED_PLANNED_REASONS` is a comma-separated exact reason list
  (case-insensitive), empty by default. Film and label changes are not excluded
  automatically. Configuration applies consistently to card and dashboard reads.
- Shared calculation supports reliable same-period gross and rejected counts.
  Current hourly storage has neither. Shift-end X-ray captures do not carry
  matching hourly coverage, so they are not assigned to hourly OEE. Existing
  X-ray/QA reporting remains intact and no quality module is introduced.
- A successfully queried empty stop list means no recorded stops. Missing stop
  data produces "Awaiting downtime data", never invented zero downtime.
- Zero operating time makes performance/OEE unavailable. Above-100% performance
  is not capped and requires review; high OEE derived from it is not validated.
- Sample status is optional technician confirmation on the share card only,
  like share notes. Passed/concern never changes the quality assumption. It is
  not persisted as an audited quality record.
- Unexplained shortfall is only shown when standard, counts and stop records
  are available. It is a residual estimate, not confirmed downtime. Over-target
  records suppress this residual. Existing reasons and notes are kept concise.

## Verification

Automated cases cover full hour at standard (98% provisional OEE), unplanned
stops (81.7% OEE with 10 minutes stopped and 5,000/6,000 packs), partial hour,
45% and 65% colour boundaries, over-target, missing stops, failed sample, zero
output, zero operating time, pallet conversions, original 338.8%, configured
planned exclusions, overlapping stops, invalid quality configuration and measured
reject arithmetic. Sample failure changes status only, not the percentage.

Local browser captures cover red, amber, green, zero, partial, missing-data and
original examples at 390px mobile width, plus a quality concern. Downloadable
WhatsApp images are 1080px wide. These are previews/test fixtures, not new
production readings. Before and after images are under the workspace
`work/hourly-card-review` directory.

## OEE infographic refinement

The primary ring now uses the backend Estimated OEE value; output attainment remains
a separate figure beside the pack comparison. The agreed trial bands are red below
45%, amber below 65%, green through 100%. These are trial thresholds, not industry
benchmarks. Missing inputs produce a grey ring. Above-100% OEE, a performance warning
or a technician quality concern produces an amber dashed review ring, retaining the
calculated percentage without suggesting good performance. Screen and PNG share this
state logic. Calculation, data storage and delivery are unchanged.

## Final user-approved card metric
The primary ring is Output vs Target: produced / expected x 100. It no longer
shows OEE or the availability/performance/quality breakdown. The card retains
pack totals, positive shortfall, recorded downtime and review warnings. Existing
backend calculations remain available to the dashboard.
