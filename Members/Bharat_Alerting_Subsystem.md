# Team Member 4: Alerting & Notification Subsystem

## Overview
You are the **Outbound Services Developer**. You are handling a core business requirement: "Not all users have smartphones; they must receive real-time offline alerts." You act as the dispatcher for the Smart City, translating internal machine warnings into physical texts and emails.

## Module Boundaries
Your module is a highly decoupled sink. You never generate safety numbers yourself; you strictly act forcefully on what the domain engines declare as emergencies.
*   **What you don't care about:** You do not care how an ML algorithm determined the air was toxic. You simply trust the incoming payload. You also don't store 30-day analytics.
*   **Core Responsibilities:** 
	*   Building the isolated **FastAPI** notification service.
	*   Implementing the **Chain of Responsibility Pattern** to elegantly parse different urgency levels (Information vs Critical) and map them to their correct physical outputs without massive `if/else` ladders.
	*   Managing the external API tokens and request libraries securely for **Twilio** and **SendGrid**.

## Frontend Touchpoints
*   The Flutter web/mobile frontend can surface alert delivery status, alert history, and manual test-trigger controls.
*   The frontend should call this service for previewing notifications and configuring user-facing alert preferences, while the backend stays the source of truth for actual dispatch.

## Integration & Independence
*   **Inbound Integration:** Your service is an **AMQP Consumer** strictly bound to the `alerts.*` topics on RabbitMQ. If every other domain engine fails except EHS, your service stays alive gracefully processing the single EHS feed. 
*   **Outbound Integration:** You execute standard HTTPS POST requests explicitly to Twilio/SendGrid. Because you are separated from the rest of the backend, a sudden timeout or crash from the Twilio API only crashes your specific container—leaving the critical physical entrance gates, Flutter dashboard, and backend databases entirely unbothered.
