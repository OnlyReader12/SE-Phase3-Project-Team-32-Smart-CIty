# ADR 009: Decoupled PII Scrubbing Layer

## Context and Problem Statement
The Smart City constraints explicitly state: "Due to privacy issues, the system should not store any sensitive data related to the users." However, to authenticate people at the gate, we *must* read their PII (Private personal data, like a face scan or student ID). To give researchers 30-day data sets, we must ensure user actions aren't tied to their names. How do we process user data for authentication, but guarantee it never gets stored or leaked?

## Decision Drivers
*   **Strict Regulatory Compliance:** The privacy constraint is a hard mandate.
*   **Data Usability:** Researchers still need the data (e.g., "Gate 4 was used 30 times"), just without the names.
*   **Trust:** Residents must feel safe using the Smart City application.

## Considered Options
*   **Option A:** Trust the individual domain engine programmers to remember to delete names from their datasets before saving.
*   **Option B:** Hardcoded Database Triggers (Make the database delete the names exactly as they are saved).
*   **Option C:** A Decoupled Scrubbing Layer (A completely separate software wall that filters out PII right before it reaches the database).

## Decision Outcome
We have chosen **Option C (Decoupled Scrubbing Layer)** to satisfy the privacy constraints safely. Rather than relying on human memory (which fails), we place a strict "wall" of code right in front of our storage engines and out-bound APIs. This layer programmatically drops any column labeled with PII (like `user_name` or `face_hash`) leaving only the anonymized telemetry behind.

## Consequences
*   **Positive:** Privacy is enforced "by design." A bug in the Energy Engine cannot accidentally leak student IDs because the scrubbing wall catches it.
*   **Negative:** Adds a slight processing delay to out-bound API calls as the scrubbing algorithm has to scan and clean large datasets before sending them to researchers.

## Confirmation
This can be validated by running a "Penetration Test" against the Researcher API. A developer can deliberately try to inject PII into a fake payload; if the API successfully returns the data *without* the PII, the scrubbing layer works.

## Pros and Cons of the Options
*   **Option A (Human Trust):** Pros: Fastest to code. Cons: Completely unacceptable; someone will inevitably forget and leak private data.
*   **Option B (Database Triggers):** Pros: Strong guarantee. Cons: Very hard to upgrade and scale if the privacy laws change.
*   **Option C (Decoupled Scrubbing Layer):** Pros: Centralized, easy to update when privacy laws change, impossible to bypass. Cons: Adds an extra hop in the data pipeline.
