# ADR 008: PostgreSQL for RBAC and Configurations

## Context and Problem Statement
Our system has a strict requirement that "Not every stakeholder should have access to all types of functionalities/data." A student should not be able to turn off the smart-lamps, and a researcher should only see 30-day graphs. This requires strong RBAC (Role-Based Access Control). Because we chose InfluxDB to hold our speedy sensor data, we are left without a safe place to store structured passwords, user profiles, and permission roles. How do we securely store access control tables?

## Decision Drivers
*   **Data Integrity:** Passwords and roles must never get corrupted or accidentally deleted.
*   **Relational Structure:** Users belong to Teams, and Teams have specific Permissions. This data is highly interrelated.
*   **Security:** Needs proven, industry-standard access protection.

## Considered Options
*   **Option A:** Add the user data into the InfluxDB engine.
*   **Option B:** Use MongoDB (A document database).
*   **Option C:** PostgreSQL (A strict, traditional relational database).

## Decision Outcome
We have chosen **Option C (PostgreSQL)** effectively resolving the data integrity forces. Because it is a strictly typed relational database, it is impossible to accidentally misspell a role or create an "orphan" user without an assigned team. It perfectly complements the fast, chaotic sensor data of InfluxDB by providing a solid, secure foundation for all our system configurations and access control checks.

## Consequences
*   **Positive:** Bulletproof security routing. We can easily define rigid tables like "Admins", "Serviceability", and "Residents".
*   **Negative:** Managing two separate databases (InfluxDB for sensors, Postgres for users) increases the DevOps deployment complexity for the administration team.

## Confirmation
Validation is satisfied by deploying a database schema review and confirming the existence of foreign-key constraints tying User IDs to strict Role IDs before any application code is run.

## Pros and Cons of the Options
*   **Option A (InfluxDB):** Pros: Keeps the system simple with only one database. Cons: Dangerously impossible; Influx deletes old data automatically and doesn't support complex table relations.
*   **Option B (MongoDB):** Pros: Very easy for developers to toss JSON data into. Cons: Lacks the rigid, strict enforcements needed for a highly secure user-permission matrix.
*   **Option C (PostgreSQL):** Pros: The gold standard for safe, relational data. Cons: Requires strict schema definitions upfront.
