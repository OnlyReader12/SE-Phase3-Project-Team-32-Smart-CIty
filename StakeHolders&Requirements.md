## ## Functional Requirements Specification

### ### 1. Energy Management Team
Focused on maximizing solar output and minimizing waste.

* **Manager Role:**
    * **FR-E1:** The system shall provide real-time dashboards for solar power generation and AC energy consumption.
    * **FR-E2:** The system shall generate energy savings recommendations based on historical usage patterns.
    * **FR-E3:** The system shall allow managers to configure automated on/off timings for campus smart lamp posts.
* **Serviceability Role:**
    * **FR-E4:** The system shall provide a maintenance dashboard specifically for the health status of solar devices and AC IoT nodes.
* **Analytics Role:**
    * **FR-E5:** The system shall integrate ready-made models to forecast future energy consumption based on historical data.

### ### 2. EHS (Environmental Health & Safety) Management Team
Focused on campus-wide vitals like air and water quality.

* **Manager Role:**
    * **FR-H1:** The system shall visualize real-time Air Quality Index (AQI) and water quality (pH, turbidity) data.
    * **FR-H2:** The system shall allow configuration of SMS/Email alert thresholds for hazardous air or water conditions.
* **Serviceability Role:**
    * **FR-H3:** The system shall report the calibration status and heartbeat of all 300 outdoor air and water sensor nodes.
* **Analytics Role:**
    * **FR-H4:** The system shall generate water quality forecasts using integrated predictive algorithms.

### ### 3. Crowd & Access Management (CAM)
Focused on traffic flow, crowd density, and secure access.

* **Manager Role:**
    * **FR-O1:** The system shall display real-time crowd density information and heatmaps for specific campus areas.
    * **FR-O2:** The system shall monitor and log user authentication events at campus entrances.
* **Serviceability Role:**
    * **FR-O3:** The system shall monitor the operational status of entrance sensors and crowd-monitoring cameras.
* **Analytics Role:**
    * **FR-O4:** The system shall provide crowd movement forecasting for event planning and security distribution.

### ### 4. Researchers (Data Scientists)
Focused on long-term study and innovation.

* **FR-R1:** The system shall provide third-party REST APIs to allow stakeholders to query and export up to 30 days of historical datasets.
* **FR-R2:** The system shall allow for data filtering based on specific IoT node types (e.g., only solar or only water data).

### ### 5. Residents (End-Users)
The primary beneficiaries of the "Smart City" services[cite: 68, 101].

* **FR-U1:** The system shall provide real-time alerts via SMS/Email to users who do not have access to smartphones.
* **FR-U2:** The system shall support automated control of fans, lights, and ACs in smart classrooms based on occupancy or predefined settings.
* **FR-U3:** The system shall allow residents to view parameter visualizations (like AQI) through mobile and web applications.

---

## ## Architecturally Significant Non-Functional Requirements (NFRs)
These define the quality of the service provided to the stakeholders listed above.

* **Performance / Latency (< 1 second entrance authentication):** 
  * **Architectural Significance:** This strict constraint dictates that the Crowd & Access Management Engine must use high-speed, non-blocking asynchronous processing or local edge-processing. Synchronous database lookups or long network round-trips would cause unacceptable entrance bottlenecks.
* **Privacy (No PII storage):** 
  * **Architectural Significance:** This forces a decoupled "Data Scrubbing Unit" into the architecture. Telemetry and resident logs must pass through strict sanitization before hitting persistent storage or the 3rd-party API to ensure compliance by design.
* **Interoperability (300 heterogeneous nodes):** 
  * **Architectural Significance:** The presence of diverse protocols and payload types (Images vs Numerical) necessitates the dedicated Gateway and Semantic Middleware (OneM2M). Without this, domain engines would be tightly coupled to hardware, destroying extensibility.
* **Availability / Power Limitations (Outdoor sensors):** 
  * **Architectural Significance:** Because external power is heavily restricted, the system must employ lightweight messaging protocols (like MQTT over a RabbitMQ broker). It must rely on event-driven updates rather than continuously polling the heavily constrained outdoor nodes.
* **Accuracy (Crowd Monitoring processing):**
  * **Architectural Significance:** Processing dense camera heatmaps requires substantial computational power. This demands architectural isolation—separating heavy ML processing workloads into dedicated service containers so they don't starve resources from critical access gateways.

---
