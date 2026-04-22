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

and rescales each point using a **local windowed MAD**. Rather than computing
a single global MAD over the entire jump series, the baseline at each index
\(i\) is estimated from a sliding window of half-width \(w\) that excludes
point \(i\) itself (leave-one-out):

$$
W_i = \{j_k : |k - i| \le w,\; k \ne i\}
$$

$$
\operatorname{MAD}_i = \operatorname{median}_{k \in W_i} \left|j_k - \operatorname{median}(W_i)\right|
$$

$$
\hat{\sigma}_i = 1.4826 \cdot \max\!\left(\operatorname{MAD}_i,\, \varepsilon\right)
$$

The final score is

$$
s_i = \frac{|j_i|}{\hat{\sigma}_i}
$$

Using a local baseline means a real discontinuity cannot inflate its own MAD
and suppress its own z-score. It also prevents a long flat saturation region
from setting a near-zero global MAD that causes false positives at the onset of
the curve.

The default half-window is \(w = 10\) samples.

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
