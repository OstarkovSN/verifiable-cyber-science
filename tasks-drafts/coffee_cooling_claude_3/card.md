# Coffee cooling (Newton's law)

**Question.** Coffee poured at 90 °C in a 20 °C room is at 70 °C ten minutes later. Under Newton's law of cooling, when does it reach 50 °C? Answer as a guaranteed interval in minutes.

**Measurements (taken as exact).** T(0)=90 °C, T(10)=70 °C; room 20 °C.

**Assumptions.** The temperature T(t) is differentiable and T'(t) = -c (T(t) - 20) for all t with one constant c (unknown, determined by the data). The room temperature is constant at 20 °C, the coffee is uniform in temperature, no evaporation or other effects. Time starts at pouring.

**Spec.** `temp t = 20 + 70 exp(-coeff t)`, `coeff = log(7/5)/10` (the closed form). Lean checks: temp satisfies the ODE; matches both data points; coeff>0; any solution of the ODE with any constant c through both data points equals temp (so the closed form is forced, not assumed); the 50 °C time exists, is unique, and lies in [25, 25.5] minutes (true value ≈ 25.18).

**Not checked.** That Newton's law describes real coffee; measurement error (data exact); the numerical values are only what the definitions say. Interval is on the model's exact answer 10·log(7/3)/log(7/5).
