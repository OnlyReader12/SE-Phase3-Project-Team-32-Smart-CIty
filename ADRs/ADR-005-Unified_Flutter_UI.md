# ADR 005: Unified UI Framework Using Flutter

## Context and Problem Statement
The Smart City lab requires both web platforms (management dashboards) and mobile applications (resident alerts and smart-class controls). Managing two entirely separate teams—one writing React.js for the web and another writing Swift/Kotlin for mobile—can strain university resources. How can we deliver both web and mobile experiences without duplicating engineering effort?

## Decision Drivers
*   **Engineering Efficiency:** We want to write code once and run it everywhere to save time.
*   **Visual Consistency:** The management interface and resident interfaces should look identically sleek.
*   **Real-time Capabilities:** The UI must be able to handle live data streams (Telemetry) natively without stuttering.

## Considered Options
*   **Option A:** Native Mobile + React Web (Two totally separate codebases).
*   **Option B:** React Native (Web developers use React to try and output mobile apps).
*   **Option C:** Pure-Flutter Architecture (Using Google's Flutter framework to output web, iOS, and Android from one single file).

## Decision Outcome
We have chosen **Option C (Pure-Flutter Architecture)**. Adopting a unified UI framework using Flutter enables us to write a single codebase that compiles directly to all required mediums (web and mobile). It solves the engineering efficiency force remarkably well, as a single team can maintain the entire front-end of the city ecosystem.

## Consequences
*   **Positive:** Massively reduced developer maintenance time. The UI is pixel-perfect across all devices.
*   **Negative:** The web dashboard might have a slightly larger initial download size since it has to download the Flutter graphics engine first. 

## Confirmation
This can be validated during the Continuous Integration (CI) build process by ensuring that a single "push" to the codebase successfully triggers compilation for an Android APK build, an iOS IPA build, and a Web HTML/JS bundle.

## Pros and Cons of the Options
*   **Option A (Separate Codebases):** Pros: Best highly-specialized performance. Cons: Requires hiring two separate teams with completely different skills.
*   **Option B (React Native):** Pros: Great community support. Cons: Often struggles with complex, heavy animations across different phone brands compared to native code.
*   **Option C (Flutter):** Pros: A single codebase that feels exactly like a native app on phones, and draws perfectly on the web canvas. Cons: Smaller community ecosystem compared to React/Javascript.
