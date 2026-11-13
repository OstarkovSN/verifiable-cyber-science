# Coffee cooling (Newton's law)

Question: coffee poured at 90 C in a 20 C room is at 70 C ten minutes later. Assuming Newton's law of cooling with a
constant coefficient, when does it reach 50 C? Answer as a guaranteed interval in minutes.

Measurements: T(0) = 90 C, room = 20 C, T(10 min) = 70 C (treated as exact; no measurement error is modelled).

Assumptions (plain words): the room stays at exactly 20 C; the whole cup has one uniform temperature; the cooling
coefficient k is constant in time and unknown a priori; dT/dt = -k (T - 20). The solution with T(0) = 90 is
T(t) = 20 + 70 exp(-k t); the Spec writes this closed form down and states separately that it satisfies the ODE.
Time is in minutes, temperature in Celsius.

Lean checks: (1) for every k, the function satisfies Newton's law at every time; (2) it matches T(0)=90, and there is a
unique k with T(10)=70, and that k is positive; (3) for every k matching T(10)=70 and every time t with T(t)=50,
t lies in [25, 26] minutes, and such a t exists.
Lean does not check: that Newton's law is true of real coffee (evaporation, radiation, non-uniform temperature),
uniqueness of ODE solutions (the closed form is the model, not derived from the ODE inside Lean), or that the data
are exact. The true value is about 25.2 min.
