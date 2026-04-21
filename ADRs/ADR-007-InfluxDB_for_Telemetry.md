# ADR 007: InfluxDB for Telemetry Storage

## Context and Problem Statement
300 IoT nodes are continuously generating numbers (water pH levels, solar output, crowd counts) every few seconds. Our requirements explicitly state that third-party stakeholders (Researchers) must be able to securely query "up to 30 days of data". Trying to stuff thousands of rapid numerical temperature readings per minute into a standard database will bloat it rapidly. What database technology should hold this continuous stream of numbers?

## Decision Drivers
*   **High-Write Throughput:** The database must be capable of surviving constant, non-stop writes from the sensors.
*   **Time-Bounded Windowing:** We must easily limit access and storage to exactly 30 days of history.
*   **Analytics querying:** Data Scientists need to easily query average trends over time.

## Considered Options
*   **Option A:** PostgreSQL / MySQL (Traditional Relational Databases).
*   **Option B:** MongoDB (A Document/NoSQL database).
*   **Option C:** InfluxDB (A purpose-built Time-Series Database / TSDB).

## Decision Outcome
We have chosen **Option C (InfluxDB)** perfectly resolves the storage forces. InfluxDB is built explicitly to handle "Telemetry (Sensor Data Streams)"—it writes incoming numbers blazingly fast. More importantly, it features native "Data Retention Policies," meaning we can tell the database to automatically delete or archive any row of data that becomes older than exactly 30 days, satisfying the researcher constraint automatically.

## Consequences
*   **Positive:** The system easily survives the massive influx of data. The 30-day compliance rule happens automatically without manual code.
*   **Negative:** InfluxDB is awful at storing things like "User Accounts" or "Passwords", meaning we have to run a second database (like PostgreSQL) for that kind of data.

## Confirmation
Validation is achieved by stress-testing the database with 300 simulated nodes firing data to confirm it doesn't crash, and reviewing the configured retention policy file to ensure the 'duration' is set precisely to 30d.

## Pros and Cons of the Options
*   **Option A (PostgreSQL):** Pros: Very reliable for structured data. Cons: Quickly bogs down if you try to write 10,000 new rows every minute.
*   **Option B (MongoDB):** Pros: Flexible for unstructured inputs. Cons: Does not have native, highly-optimized time-windowing analytics queries.
*   **Option C (InfluxDB):** Pros: Incredibly fast writes and built-in 30-day auto-deletion. Cons: Strict focus on time-series means it's useless for standard relational data.
