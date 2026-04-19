# Higher-order mode

`higher_order` detects discontinuities by looking for abrupt changes in the
second derivative, then thresholding a derived score.

Given sorted samples \((x_i, y_i)\), the method builds three grids:

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

The final score is a normalized jump in the second derivative:

$$
s_i =
\frac{\left|f^{(2)}_{i+1} - f^{(2)}_i\right|}
{\left(|f^{(2)}_i| + \varepsilon\right)
 \left(\bar{x}^{(2)}_{i+1} - \bar{x}^{(2)}_i\right)}
$$

where \(\varepsilon\) is a tiny constant that prevents division by zero.

The detector flags indices where

$$
s_i > T
$$

with \(T\) equal to the configured `threshold`.

Implementation notes:

- The score lives on the \(N-3\) grid, not the original sample grid.
- This mode is stricter than `simple` because it reacts to derivative
  structure rather than raw amplitude.
- It is still more brittle than `robust` when the curve has strong but
  legitimate curvature changes.

Use `higher_order` when you want a derivative-based detector without the
outlier filtering used by the robust mode.
