# TonnageFlow Pulse

## Overview

TonnageFlow Pulse is a free operational intelligence application for food manufacturers.

It transforms the WhatsApp conversations that already happen on the factory floor into structured operational data and live production intelligence.

Instead of asking factories to adopt another complex software platform, TonnageFlow Pulse works alongside their existing communication process.

Line Technicians continue using WhatsApp.

Managers receive structured production information.

Directors receive live operational dashboards.

TonnageFlow Pulse is the first product in the TonnageFlow ecosystem and acts as the entry point into the Operational Drag Audit and the full TonnageFlow Platform.

---

# The Problem

Most food manufacturers already communicate through WhatsApp.

Production updates are often sent as unstructured messages such as:

> OEE 67%
>
> Film Change
>
> Casepacker Jam
>
> 4 Pallets Completed

The information exists.

The intelligence does not.

Production Managers spend time reading messages.

Engineering Managers spend time investigating issues.

Directors only receive reports after production has already been lost.

---

# The Solution

TonnageFlow Pulse converts operational conversations into structured production intelligence.

Instead of simply storing messages, Pulse understands:

- Production Runs
- Hourly Progress
- Planned Downtime
- Unplanned Downtime
- Engineering Responses
- Production Progress
- Operational Drag
- Expected vs Actual Production
- Cost per Produced Tonne indicators

---

# Philosophy

TonnageFlow Pulse is built around one principle:

> **Manufacturing thinks in Production Runs, not hourly reports.**

The hourly update is simply a checkpoint within a production run.

Everything revolves around the Production Run.

---

# Production Run Lifecycle

Every production run follows the same lifecycle.

```
Start Production Run
        │
        ▼
Build Production Model
        │
        ▼
Hourly Production Updates
        │
        ▼
Operational Intelligence
        │
        ▼
Run Completion
        │
        ▼
Next Production Run
```

---

# Stage 1 — Start Production Run

At the beginning of every production run, the Line Technician creates a new run by entering the production details.

Example:

```
Production Line: Rovema

Customer: Tesco

Product: Long Grain Rice

Format: 1kg × 8

Pack Type: Pillow Pack

Target Speed: 120 Packs per Minute

Cases per Pallet: 220

Pallets Remaining: 38

Previous Run Completed: 42 Pallets

Shift: Nights

Line Technician: Ben
```

This information creates the Production Run.

Everything else is measured against it.

---

# Stage 2 — Production Model

Once the Production Run starts, Pulse automatically calculates:

- Expected Packs per Minute
- Expected Packs per Hour
- Expected Cases per Hour
- Expected Pallets per Hour
- Expected Completion Time
- Remaining Production Time

The Line Technician never performs these calculations.

Pulse performs them automatically.

---

# Stage 3 — Internal Timer

When production begins, Pulse starts an internal timer.

The technician never enters the time.

Every sixty minutes Pulse expects another operational update.

---

# Stage 4 — Hourly Production Update

Every hour the Line Technician provides a simple production update.

Example:

```
Pallets Completed: 4

OEE: 67%

Downtime:
Film Change

Downtime:
Casepacker Jam
```

Pulse already understands the Production Run.

The technician simply reports what happened.

---

# Stage 5 — Operational Intelligence

Pulse compares:

Expected Production

against

Actual Production.

It automatically calculates:

- Expected Packs
- Actual Packs
- Expected Cases
- Actual Cases
- Expected Pallets
- Actual Pallets
- Production Loss
- Lost Time
- Throughput Loss
- Operational Drag
- Cost per Produced Tonne indicators

---

# Stage 6 — Live Run Progress

The technician enters the number of pallets remaining only once.

Example:

```
Pallets Remaining

38
```

Hour One

```
Completed

4
```

Pulse updates automatically.

```
34 Remaining
```

Hour Two

```
Completed

4
```

Pulse updates again.

```
30 Remaining
```

The software continuously tracks the production run.

---

# Stage 7 — Run Completion

When the remaining pallets reach zero, Pulse determines whether the run has genuinely finished or whether production continues.

## Product Changeover

If the next run is a different product, the line must be emptied.

Product remaining inside the cooker, conveyors, elevators, weighers and packaging equipment is converted into finished product.

This creates an **Overrun**.

Example:

```
Planned Run

38 Pallets
```

Actual Production

```
40 Pallets
```

Pulse records:

```
Planned Production

38

Actual Production

40

Overrun

2 Pallets
```

The Overrun is stored separately because it represents product recovered while emptying the process before changing product.

---

## Customer Changeover

Sometimes only the customer changes.

Example:

```
Tesco

↓

Asda
```

The product remains exactly the same.

No product needs to be emptied from the system.

Production continues directly into the next customer order.

In this situation Pulse records:

```
Overrun

0 Pallets
```

and immediately begins the next Production Run.

---

# Factory Roles

## Line Technician

Primary user of TonnageFlow Pulse.

Responsibilities:

- Start Production Runs
- Submit Hourly Updates
- Report Downtime
- Report Production Progress
- Confirm Production Restart

---

## Engineer

Responds to unplanned downtime.

Responsibilities:

- Acknowledge Breakdown
- Investigate Fault
- Record Root Cause
- Record Corrective Action
- Confirm Repair
- Close Engineering Event

---

## Manager

Uses Pulse to coordinate production.

Responsibilities:

- Monitor Production
- Allocate Resources
- Delegate Work
- Manage Escalations
- Track Open Engineering Events

---

## Director

Consumes operational intelligence.

Receives:

- Live Production Dashboard
- OEE Trends
- Production Progress
- Operational Drag
- Downtime Analysis
- Cost per Produced Tonne Insights

---

# Core Business Objects

TonnageFlow Pulse is built around real manufacturing objects.

- Production Run
- Hourly Update
- Downtime Event
- Engineering Response
- Production Progress
- Operational Drag
- Production Line
- Line Technician
- Engineer
- Manager

---

# Technology Stack

Current Version

- Python
- Git
- GitHub
- Virtual Environments

Future Versions

- SQLite
- Power BI
- WhatsApp Integration
- REST API
- AI Agents
- Cloud Deployment

---

# Product Ecosystem

```
Free

TonnageFlow Pulse
        │
        ▼
Operational Drag Audit
        │
        ▼
TonnageFlow Platform
        │
        ▼
AI Operational Intelligence
```

TonnageFlow Pulse creates trust by delivering immediate value.

That trust leads naturally into the Operational Drag Audit.

The Audit demonstrates where Cost per Produced Tonne is being lost.

The TonnageFlow Platform then provides continuous operational intelligence and AI-powered decision support.

---

# Mission

To transform everyday factory conversations into operational intelligence that helps food manufacturers reduce Cost per Produced Tonne, improve production stability and make better operational decisions before losses occur.