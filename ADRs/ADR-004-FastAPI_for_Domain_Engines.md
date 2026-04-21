# ADR 004: FastAPI for Domain Processing Engines

## Context and Problem Statement
Our Architecture has specific Domain Engines (isolated containers of code handling specific jobs, like the Air Quality Engine). We must use "ready-made machine learning models" inside of them to forecast data. At the same time, the web interfaces require rapid, non-blocking real-time streams of information to show live dashboards. What programming framework should we use to build these core engines?

## Decision Drivers
*   **Machine Learning (ML) Integration:** Must smoothly load and run existing AI and math models.
*   **Handling Asynchronous Operations:** Must handle thousands of tiny sensor updates without freezing up.
*   **Developer Ecosystem:** Needs to be easy for university researchers to write code for.

## Considered Options
*   **Option A:** Node.js (JavaScript).
*   **Option B:** Python using Django framework.
*   **Option C:** Python using FastAPI framework.

## Decision Outcome
We have chosen **Option C (Python using FastAPI)**. Because we must use ready-made ML models, Python is practically mandatory (it is the main language for AI). However, standard Python frameworks (like Django) can be "blocking" (slow when waiting for internet responses). FastAPI is built specifically to be incredibly fast and "asynchronous", meaning it handles live streams just as well as Node.js while keeping the AI benefits of Python.

## Consequences
*   **Positive:** The data scientists can write direct Python code right next to the web server code. Dashboards will be extremely fast and responsive.
*   **Negative:** The team has to ensure they write proper "async code" to utilize FastAPI's speed, which takes slightly more learning than standard Python.

## Confirmation
This can be validated by code reviews examining the engines to ensure standard Python AI libraries (like scikit-learn or pyTorch) are successfully imported into the routing files.

## Pros and Cons of the Options
*   **Option A (Node.js):** Pros: The kings of fast, real-time web streams. Cons: Horrible for running heavy machine learning models natively. 
*   **Option B (Python Django):** Pros: Great AI support, robust features. Cons: Can be sluggish and bulky when dealing with thousands of real-time sensor updates.
*   **Option C (Python FastAPI):** Pros: Fast, handles live streaming perfectly, and integrates Python AI instantly. Cons: Smaller community than Django.
