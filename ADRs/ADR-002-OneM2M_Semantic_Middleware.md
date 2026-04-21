# ADR 002: Implementation of OneM2M as Semantic Middleware

## Context and Problem Statement
The Smart City living lab will use 300 different IoT nodes (internet-connected sensors). Some are cameras, some send water quality numbers, and they all use different internet languages (protocols) like MQTT or HTTP. If our main software has to understand every single sensor's language directly, the code will become a mess. How do we cleanly connect hundreds of diverse sensors to our main computer system?

## Decision Drivers
*   **Interoperability:** The ability for totally different machines to easily talk to each other.
*   **Standardization:** Using an accepted global rulebook rather than inventing our own.
*   **Extensibility:** Making it easy to plug in a brand new, never-before-seen sensor next year.

## Considered Options
*   **Option A:** Build custom translator codes (wrappers) inside our main business logic for every specific sensor type.
*   **Option B:** Use a standard Semantic Middleware layer (like the OneM2M standard framework).
*   **Option C:** Force the hardware team to only buy sensors that use one exact language (e.g., exclusively MQTT).

## Decision Outcome
We have chosen **Option B (OneM2M Semantic Middleware)**. It perfectly meets the critical interoperability driver. The middleware acts as a dedicated translator; it takes in gibberish from 300 different nodes and turns it all into a single, standard structure before it reaches our main systems.

## Consequences
*   **Positive:** The main application code never cares what hardware brand the sensor is; it only ever reads standard OneM2M formats. Highly maintainable.
*   **Negative:** The team now has to learn and maintain the somewhat steep rules of the OneM2M global standard.

## Confirmation
This can be validated in automated tests by sending fake data in three different formats (HTTP, CoAP, and MQTT) into the gateway and writing a test that asserts the output is identically formatted.

## Pros and Cons of the Options
*   **Option A (Custom Translators):** Pros: Quick for the first few sensors. Cons: Turns into a nightmare to manage once you hit 300+ nodes. 
*   **Option B (OneM2M Middleware):** Pros: Highly standardized, future-proof, and decouples hardware from software. Cons: Heavy initial learning curve.
*   **Option C (Strict Hardware Rule):** Pros: Simplest software implementation. Cons: Impossible to enforce fully; restricts the "Living Lab" research freedoms regarding physical sensors.
