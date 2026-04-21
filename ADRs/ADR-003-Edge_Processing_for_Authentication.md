# ADR 003: High-Speed Edge Processing for Fast-Track Authentication

## Context and Problem Statement
The Smart City requirements state that the Fast-Track Authentication for residents entering the campus must take less than 1 second to complete. If the authentication sensor takes a picture, sends it over the internet to a central cloud database, waits for processing, and sends an "Unlock" signal back, network delays might make it take 2 or 3 seconds. How do we guarantee the entrance opens in under 1 second?

## Decision Drivers
*   **Performance (Latency):** The absolute delay speed (< 1 second) is a strict requirement.
*   **Network Reliability:** Entrance gates must work even if the campus internet is slow.
*   **Security:** Unauthorized people must not be let in.

## Considered Options
*   **Option A:** Centralized Cloud Processing (Sensor sends data to a far-away main server to decide).
*   **Option B:** Local Campus Server (A main server kept directly inside the university).
*   **Option C:** Edge Processing (Putting a small computer right at the physical entrance gate to make the decision locally).

## Decision Outcome
We have chosen **Option C (Edge Processing)** to resolve the latency forces. By placing the authentication logic (the decision-maker) on a small device directly connected to the gate (the edge), we completely skip the internet trip. The entrance opens instantly, solving the < 1-second requirement gracefully. 

## Consequences
*   **Positive:** Blistering fast entrance speeds. It also works if the main campus internet goes down offline.
*   **Negative:** We now have to safely deliver user updates to the edge devices (syncing the approved list) rather than just managing one central database. 

## Confirmation
We can validate this compliance through fitness functions by physically load-testing the gate under simulated "poor network" conditions and measuring if the gate still triggers in under 1.00 seconds.

## Pros and Cons of the Options
*   **Option A (Cloud):** Pros: Easiest to build and manage. Cons: Completely fails the < 1-second rule due to internet round-trip delays.
*   **Option B (Local Server):** Pros: Faster than cloud, keeps data on campus. Cons: Still relies on campus WIFI/LAN which can get congested when thousands of students are active.
*   **Option C (Edge Processing):** Pros: Guaranteed sub-second latency and offline resilience. Cons: Harder to update code since small computers are scattered across physical gates in the city.
