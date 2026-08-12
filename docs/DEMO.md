# 3-minute demonstration

Use the operations console (API + frontend) on the Storm Test.

1. `plantos serve` and `cd frontend && npm run dev`
2. Select STORM TEST → RUN COMPARE (live naive / rules / MPC)
3. PLAY the MPC view

Suggested narration:

**0:00–0:20** Plant in normal solar-following production. Schematic flows.

**0:20–0:40** Timeline shows forecast language and reserve. Belief ≠ reality.

**0:40–1:00** Day 4: forecast stays clear-sky; GHI collapses. Naive keeps assuming sun.

**1:00–1:20** Hour 120: electrolyser efficiency residual. Hypotheses: degradation vs sensor vs weather.

**1:20–1:40** PlantOS derates the stack; it does not black-start the site.

**1:40–2:00** Methane continues at a reduced rate. Battery reserve is defended.

**2:00–2:20** Sensor drift is diagnosed as a sensor hypothesis, not an equipment trip.

**2:20–2:40** Degraded production through the cloudy days, then recovery weather.

**2:40–3:00** Comparison table (live numbers from this run, not a slide).

Do not quote a percentage improvement that you have not just generated.
