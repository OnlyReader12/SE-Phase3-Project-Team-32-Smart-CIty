# ADR 001: Adoption of a Microkernel Architecture

## Context and Problem Statement
The Smart City project will have multiple distinct functional areas like Energy Management, Air Quality monitoring, and Crowd Access Management. If we build these all into one massive program (a monolith), a crash in the Energy system could take down the critical campus entry gate system. How do we ensure that adding new features doesn't break existing, critical city functions?

## Decision Drivers
*   **Fault Isolation:** One failing system shouldn't break others.
*   **Extensibility:** Easy addition of new smart city services in the future.
*   **Maintainability:** Easier to update separate parts of the code.

## Considered Options
*   **Option A:** Monolithic Architecture (One single large program).
*   **Option B:** Microservices Architecture (Many small, independent web services communicating over networks).
*   **Option C:** Microkernel (Plug-in) Architecture (A central core messaging bus with separate plug-in modules for each domain).

## Decision Outcome
We have chosen **Option C (Microkernel Architecture)** because it perfectly resolves the force of isolation. The central core will just route messages, while domain engines (the separate containers holding business logic) act as isolated plug-ins. If the energy plug-in crashes, the central core and the crowd access plug-in keep running seamlessly.

## Consequences
*   **Positive:** New developer teams can build new features (like a smart parking plug-in) without touching the main system code at all.
*   **Negative:** Developers have to learn how to communicate through the central messaging bus instead of just calling functions directly.

## Confirmation
This architecture can be validated during design reviews by checking if the source code for the Energy Engine has zero direct dependencies on the source code of the Crowd Access Engine.

## Pros and Cons of the Options
*   **Option A (Monolithic):** Pros: Very simple to build initially. Cons: A single bug crashes the entire city dashboard.
*   **Option B (Microservices):** Pros: Great isolation. Cons: Highly complex to set up and deploy for a university living lab.
*   **Option C (Microkernel):** Pros: Offers a middle ground with excellent isolation (plug-ins) without the massive network complexity of full microservices. Cons: Creating the central core bus requires careful initial planning.
