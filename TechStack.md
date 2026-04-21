# Smart City Living Lab: Technology Stack Decision

This document outlines the finalized technology stack for the Smart City Living Lab, alongside the reasoning behind each choice. These decisions specifically address the architectural constraints: heterogeneous IoT interoperability, real-time telemetry processing, privacy compliance, and strict latency requirements (<1s authentication).

## 1. Application Mediums

*   **Progressive Web Application (PWA):** For management dashboards, deep ML analytics, and long-term data trends (used by Campus Managers and Serviceability Teams).
*   **Cross-Platform Mobile Application:** For end-user features (Residents) such as quick smart-classroom configuration, and push notifications.
*   **Offline Gateway (SMS/Email):** For emergency broadcasting to offline residents.
*   **RESTful Developer Gateway:** For secure, 30-day bounded historical data extraction (used by Researchers).

---

## 2. Technology Choices & Reasoning

### A. Frontend & Client-Side (Web & Mobile)

*   **Unified UI Framework: Flutter (for both Web and Mobile)**
    *   *Reasoning:* Adopting a pure-Flutter UI architecture enables us to write a single codebase that compiles smoothly to iOS, Android, and the Web Dashboard. This drastically minimizes the engineering effort required, creating an identical, pixel-perfect user experience across both resident smartphones and the administrative management web dashboards. Flutter also natively supports the real-time streams required for our telemetry panels.

### B. Backend Core & Middleware (The Microkernel Engines)

*   **Core Microservices Framework: Python (FastAPI)**
    *   *Reasoning:* The project explicitly mandates the use of "ready-made machine learning models." Python is the native ecosystem for data science. FastAPI brings asynchronous, non-blocking execution (crucial for hitting the `<1 second` entrance authentication requirement) while seamlessly importing existing ML libraries (scikit-learn, TensorFlow) in the same process.
*   **IoT Interoperability Middleware: Eclipse OM2M**
    *   *Reasoning:* Eclipse OM2M is a fully complaint, open-source implementation of the OneM2M standard explicitly referenced in the system constraints to handle the heterogeneity of 300+ diverse outdoor communication protocols.
*   **Message broker / Event Bus: RabbitMQ**
    *   *Reasoning:* As the backbone of the Microkernel (Plug-in) Architecture, RabbitMQ provides excellent routing capabilities. It allows the system to prioritize critical traffic (like entrance authentication and emergency EHS alerts) over standard telemetry polling.

### C. Data Persistence

*   **Telemetry & Sensor Storage: InfluxDB**
    *   *Reasoning:* An influx of data from 300 nodes every few seconds requires a Time-Series Database (TSDB). InfluxDB is optimized for high-write workloads and makes enforcing the "allow researchers to query up to 30 days of data" constraint trivial using built-in data retention policies.
*   **Relational Storage (RBAC & Configs): PostgreSQL**
    *   *Reasoning:* A proven, strictly structured relational database. Perfect for safely managing user accounts, access roles, and system configuration data without risk of data corruption.

### D. Integration Services

*   **Alerting Gateways: Twilio (SMS) & SendGrid (Email)**
    *   *Reasoning:* Industry-standard, highly reliable services to fulfill the requirement that critical safety or environmental alerts reach residents out-of-band, even if they do not possess smartphones.
*   **Data Scrubbing Layer: Python Dataframes (Pandas)**
    *   *Reasoning:* Sits in front of the Researcher REST API endpoint. Fast, tabular processing logic to strip out PII and enforce the strict privacy constraints before payload transmission.
