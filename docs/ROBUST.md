# Robust mode

`robust` is the default detector. It turns discontinuity detection into a
scale-aware outlier problem on a curvature-jump score, then filters candidate
peaks by height, prominence, and separation.

Given sorted samples \((x_i, y_i)\), the method computes:

$$
f^{(1)}_i = \frac{y_{i+1} - y_i}{x_{i+1} - x_i}
\qquad
\bar{x}^{(1)}_i = \frac{x_i + x_{i+1}}{2}
$$

$$
f^{(2)}_i = \frac{f^{(1)}_{i+1} - f^{(1)}_i}{\bar{x}^{(1)}_{i+1} - \bar{x}^{(1)}_i}
\qquad
\bar{x}^{(2)}_i = \frac{\bar{x}^{(1)}_i + \bar{x}^{(1)}_{i+1}}{2}
$$

Then it forms a jump series

$$
j_i =
\frac{f^{(2)}_{i+1} - f^{(2)}_i}
{\max\left(\left|\bar{x}^{(2)}_{i+1} - \bar{x}^{(2)}_i\right|, \varepsilon\right)}
$$

and rescales that series with a robust estimate of spread:

$$
\operatorname{MAD}(j) = \operatorname{median}_i \left|j_i - \operatorname{median}(j)\right|
$$

$$
\hat{\sigma} = 1.4826 \cdot \operatorname{MAD}(j)
$$

The final score is

$$
s_i = \frac{|j_i|}{\hat{\sigma}}
$$

So the detector is looking for unusually large MAD-z-scores in the curvature
jump signal.

## Peak filtering

Candidates are passed to `scipy.signal.find_peaks` with three constraints:

1. **Height**: \(s_i \ge \sigma\)
2. **Prominence**: `min_prominence`
3. **Separation**: `min_separation`

### Prominence

Prominence measures how much a peak stands above the surrounding valley.
For a peak at index \(p\), let \(b_L\) and \(b_R\) be the lowest reachable
values on the left and right sides before the signal hits a higher peak or the
array boundary. The prominence is

$$
\operatorname{prom}(p) = s_p - \max(b_L, b_R)
$$

Intuitively, this is the vertical drop from the peak to the higher of the two
surrounding saddles. A broad hump can have large height but low prominence, so
prominence helps reject clustered false positives.

### Separation

Separation is a minimum distance in score-sample indices, not in \(x\)-units.
If the distance parameter is \(d\), then any two accepted peaks \(p\) and \(q\)
must satisfy

$$
|p - q| \ge d
$$

In the implementation, `min_separation` is converted to
`distance=max(1, int(min_separation))`, so it is always at least 1 sample.
This prevents consecutive-index bursts from being reported as many separate
discontinuities.

## Defaults

- `sigma = 50`
- `min_prominence = 20`
- `min_separation = 3`

These values are conservative because healthy SPICE curves can have real but
smooth curvature transitions, while true discontinuities tend to produce very
large isolated peaks.

Use `robust` when you need the most stable detector across varying scales and
nonlinear but valid curve behavior.
