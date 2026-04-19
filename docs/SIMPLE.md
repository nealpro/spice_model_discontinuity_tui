# Simple mode

`simple` is the most direct detector. It does not estimate derivatives or
normalize by spacing; it only looks for large adjacent jumps in the dependent
series.

For samples \(y_0, y_1, \dots, y_{n-1}\), define the absolute step size

$$
\Delta_i = |y_i - y_{i-1}| \qquad \text{for } i = 1, \dots, n-1
$$

A discontinuity is flagged when

$$
\Delta_i \ge T
$$

where \(T\) is the `threshold` / `sensitivity` value passed to the detector.

Implementation notes:

- The score stored in the result is `[0, Δ1, Δ2, ...]`.
- Flagged indices point to the right-hand sample of each jump.
- `threshold` must be positive.
- Because `x` is not used, this mode is best when the samples are already
  evenly spaced and you only care about raw output jumps.

Use `simple` when you want the smallest possible rule and your data are
already clean and uniformly scaled.
