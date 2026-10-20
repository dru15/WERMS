# WERMS operations

WERMS supports evacuation planning and shelter coordination during changing incidents.

## Language

**Route preview**: A comparison of a possible path and destination against the currently known conditions. A preview does not hold shelter spaces.
_Avoid_: booking, confirmed route

**Confirmed plan**: A selected route with shelter spaces held for the entire party until the plan expires, is cancelled, is invalidated, or the party arrives.
_Avoid_: guaranteed safe route

**Reservation**: The shelter spaces held by an active confirmed plan. Arrival converts these spaces into occupancy; cancellation, expiry, or invalidation releases them.

**Hard closure**: A restriction excluding a road from every eligible route. Reopening the road does not revive previously invalidated plans.

**Occupancy**: People checked into a shelter. Reserved demand counts separately when judging available capacity.

**Pilot district**: The bounded geographic area supported by the imported road network. Road geography is sourced from OpenStreetMap; operational incident conditions remain demonstration data until authoritative feeds are integrated.

**Demonstration assembly site**: A mapped landmark used as a destination to exercise capacity and arrival workflows. Its emergency suitability, access, and current operation have not been verified.
_Avoid_: official shelter, certified safe destination

**What-if scenario**: A hypothetical change to recorded road or destination availability, used to compare possible outcomes without changing actual operational conditions or reservations.

**Model weather context**: Provider-generated weather estimates for a geographic area and validity time. Context is separate from local station readings, fire detections, and evacuation restrictions.
