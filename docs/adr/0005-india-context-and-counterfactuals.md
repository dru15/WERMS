# India context and counterfactual planning

Use a newly acquired Rajpur–Malsi, Dehradun OSM graph rather than relabelling California geometry. Preserve the old extract and operational database; initialize a separate India database so existing bookings cannot be attached to unrelated roads or sites. Import profiles carry geography, origin presets, country and timezone with source provenance.

Keep provider model weather outside route restriction/scoring decisions. Its timestamps, units, cache behavior and failure state are independently validated. Without a validated mapping from these readings to fire hazards, using a weather-derived fire probability would create an unsupported safety claim. A fixed pilot-centre request avoids sending a civilian's location to the provider.

Run counterfactual route comparisons from one transactional snapshot using copies of hazard and shelter state. Hypothetical closures are additive to recorded restrictions; simulated destinations can be removed but live closed sites cannot be reopened. Expired demand is excluded at analysis time without updating saved reservations. Return graph version, revision, inputs and results as exportable evidence. Tests enforce the absence of operational/audit writes.
