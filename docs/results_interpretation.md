# Interpreting results.csv

## Column reference

| Column | Meaning |
|--------|---------|
| `field` | Semantic field name — e.g. `drain_current` for FET device mode, or the raw CSV column name in generic mode |
| `group_field` | Semantic name of the grouping axis — e.g. `source_bulk_voltage`. Present only in device mode with grouping configured |
| `group` | Value of the grouping variable for this curve — e.g. the V_SB voltage in volts. Present only in device mode with grouping configured |
| `input_row` | 1-based row number in the original CSV (after the header) for the closest data point to the flagged x-value. Use this to jump directly to the suspect row in a spreadsheet |
| `x_value` | Independent-axis value where the discontinuity was detected — e.g. gate voltage V_GS in volts |
| `y_value` | Dependent-axis value at that point — e.g. drain current I_D in amperes |
| `score` | MAD z-score at the flagged point. Unitless. Default threshold is 5; healthy curvature variations typically stay below ~20; sharp injected faults produce values in the hundreds or higher |
| `threshold` | Minimum score required to flag a point (configurable via `[detection].sensitivity` or `-s`) |
| `method` | Detection algorithm used — always `robust` |

## Why scores can be very large (e.g. over 300,000)

The robust method computes a MAD-normalized z-score of the jump in the second derivative. When the dataset contains a single sharp injected fault that dwarfs all other curvature variation, the median absolute deviation (MAD) of the score distribution approaches zero, causing all flagged z-scores to saturate at a very large number.

A score of \~334,800 and a score of \~400,000 are both "certain faults" — the magnitude difference is meaningless once scores are this far above threshold. Scores near the threshold (e.g. \~20) are marginal detections that may warrant closer inspection.

## Manual verification workflow

1. Note the `group_field` and `group` values to identify which curve the flag belongs to — e.g. `source_bulk_voltage = 0` means the V_SB = 0 V curve.
2. Use `input_row` to jump directly to that row in the original CSV (row 1 = first data row after the header).
3. Confirm the independent-axis column (e.g. `V(X1.GATE,X1.SOURCE)`) matches `x_value` at that row.
4. Confirm the dependent-axis column (e.g. `I(VDRAIN)`) matches `y_value` at that row.
5. Look at the ±5 surrounding rows to see the discontinuity visually — there should be a visible step, kink, or spike in the current values.

## Worked example

Given a row in `results.csv`:

```
drain_current, source_bulk_voltage, 0, 312, 0.255, 3.47e-05, 334799, 5, robust
```

- **field** = `drain_current` → this is I_D
- **group_field** = `source_bulk_voltage`, **group** = `0` → V_SB = 0 V curve
- **input_row** = `312` → go to row 312 of the original CSV (after the header)
- **x_value** = `0.255` → the discontinuity is near V_GS = 0.255 V (close to threshold voltage)
- **y_value** = `3.47e-05` → I_D ≈ 34.7 µA at that point
- **score** = `334799` → ~67,000× above threshold; a clear, unambiguous fault

Three consecutive hits at x = 0.255, 0.305, 0.325 V for the same group indicate a single injected spike that disturbs curvature across multiple derivative windows — this is expected behavior for a point fault near the threshold region.
