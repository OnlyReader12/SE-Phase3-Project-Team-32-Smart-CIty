# ADR 010: External Alerting Gateways

## Context and Problem Statement
The Smart City lab requires that we alert people if there are hazardous air or water quality conditions. However, the constraints explicitly state: "All the users may not have smartphones... they should be able to get real-time alerts." We cannot rely solely on push notifications via our Flutter app. How do we reliably deliver critical text messages and emails to offline users without building our own cell-tower network?

## Decision Drivers
*   **Delivery Reliability:** Emergency alerts must have a near 100% chance of reaching the user.
*   **Offline Accessibility:** Must reach basic flip-phones or offline desktops.
*   **Development Speed:** We cannot build a complex email-sending server from scratch inside a living lab.

## Considered Options
*   **Option A:** Build our own SMTP Email Server and attach a hardware GSM Sim-card modem to our server to send texts.
*   **Option B:** Rely purely on Web Dashboards and expect offline users to log in on library computers.
*   **Option C:** Offload to Third-Party Gateways (Twilio for SMS, SendGrid for Email).

## Decision Outcome
We have chosen **Option C (Third-Party Gateways)**. It solves the delivery reliability force flawlessly. Rather than managing physical SMS modems or fighting spam-filters on a custom email server, our Alerting Subsystem will simply make a quick API call to Twilio and SendGrid. These massive enterprise companies guarantee offline delivery to users' basic cell phones.

## Consequences
*   **Positive:** Instant compliance with the offline-user constraint with almost zero backend coding required.
*   **Negative:** It costs money. Twilio and SendGrid charge a tiny fraction of a cent per message, which requires allocating a small operational budget.

## Confirmation
This is easily validated through an end-to-end user test. An administrator can trigger a "Test Alert" in the management dashboard and physically verify that an offline dummy flip-phone receives the SMS text within seconds.

## Pros and Cons of the Options
*   **Option A (Build it ourselves):** Pros: Free to send messages (after hardware cost). Cons: A massive nightmare to maintain a physical SIM modem, and custom emails almost always go to the recipient's Spam folder.
*   **Option B (Just use Web):** Pros: No extra work. Cons: Directly fails the project constraint requiring real-time alerts for non-smartphone users.
*   **Option C (Twilio/SendGrid Gateways):** Pros: Guaranteed delivery, bypasses spam filters, extremely easy to code. Cons: Incurs an ongoing subscription cost for the university.
