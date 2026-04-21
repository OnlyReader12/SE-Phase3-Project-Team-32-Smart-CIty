# ADR 006: RabbitMQ as the Central Message Broker

## Context and Problem Statement
Our Smart City uses a Microkernel (plugin) structure, meaning we have a central core routing messages to isolated domain engines (like EHS or Energy). Additionally, because external power sockets are limited, our outdoor sensors run on batteries. They cannot afford to stay constantly turned on waiting for "polls" from the server. How do we securely route messages and allow sensors to safely wake up, send data, and sleep?

## Decision Drivers
*   **Asynchronous Communication:** Components should drop off a message and move on, not wait around blocking the network.
*   **Energy Efficiency:** Outdoor hardware must limit its radio-on time to preserve battery life.
*   **Message Routing:** The central core needs to know *where* to send specific types of data (e.g., routing water data away from the energy engine).

## Considered Options
*   **Option A:** Direct HTTP REST API (Services talk to each other directly).
*   **Option B:** Apache Kafka (A massive, highly-durable streaming ledger).
*   **Option C:** RabbitMQ (A flexible, routing-focused message broker supporting MQTT).

## Decision Outcome
We have chosen **Option C (RabbitMQ)** as the central message broker. It solves the communication forces perfectly. RabbitMQ natively supports MQTT (a super lightweight protocol perfect for our battery-powered outdoor sensors). Furthermore, it excels at complex "routing," allowing our central gateway to easily fan-out data only to the specific domain plug-ins that request it.

## Consequences
*   **Positive:** Battery-powered sensors can rapidly publish an MQTT message and immediately sleep. Engines can independently subscribe to exactly the topics they care about.
*   **Negative:** Adds a piece of infrastructural "plumbing" that requires an administrator to monitor (ensuring message queues don't back up).

## Confirmation
This can be validated by checking the RabbitMQ dashboard during operations to ensure "Publish/Subscribe" queues are successfully dropping down to zero, confirming that domain engines are keeping up with the sensor traffic.

## Pros and Cons of the Options
*   **Option A (Direct HTTP):** Pros: Simplest to understand. Cons: Fails the battery requirement; if the server is busy, the sensor has to stay awake waiting for an HTTP 200 OK response.
*   **Option B (Apache Kafka):** Pros: Unmatched for holding massive amounts of permanent log data. Cons: Overkill for our routing-heavy use case, and less native support for low-power MQTT devices out of the box. 
*   **Option C (RabbitMQ):** Pros: Exceptional routing flexibility and lightweight sensor friendly. Cons: Messages are not inherently stored forever like they are in a Kafka ledger.
