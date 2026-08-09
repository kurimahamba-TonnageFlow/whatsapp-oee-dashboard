# TonnageFlow Pulse

## Overview

TonnageFlow Pulse is a factory-floor production intelligence application designed for food manufacturing.

It captures production activity as it happens and converts simple factory-floor updates into structured operational data.

Pulse tracks the lifecycle of a Production Run from start to finish, including:

- Production setup
- Expected production
- Hourly production updates
- Planned downtime
- Unplanned downtime
- Engineering response
- Production progress
- Changeovers
- Overrun
- Operational events

The Production Run is the core object within Pulse.

Instead of treating each hourly update as an isolated report, Pulse builds a structured operational history of what happened throughout the run.

---

# The Problem

Food manufacturing factories generate large amounts of operational information every shift.

However, much of this information is still captured through:

- Paper records
- Whiteboards
- Spreadsheets
- WhatsApp messages
- Shift handovers
- OEE reports
- Verbal communication

The information exists, but it is often fragmented.

This makes it difficult to understand the actual sequence of events behind production performance.

Traditional reporting can tell management that performance was poor.

Pulse is being designed to help explain:

**What happened?**

**When in the production run did it happen?**

**Was it planned or unplanned?**

**What production was lost?**

**Was engineering required?**

**Was the issue resolved?**

**What effect did the event have on the Production Run?**

---

# The Solution

TonnageFlow Pulse creates a digital operational history of each Production Run.

The basic model is:

```text
Production Run
      │
      ├── Production Run Started
      │
      ├── Hourly Update
      │
      ├── Planned Downtime
      │
      ├── Unplanned Downtime
      │
      ├── Engineering Response
      │
      ├── Production Progress
      │
      ├── Planned Quantity Complete
      │
      ├── Overrun
      │
      ├── Changeover
      │
      └── Production Run Finished
```

These events can later be stored, analysed and converted into operational intelligence.

---

# Product Philosophy

Pulse should require the minimum possible effort from the people running the production line.

The Line Technician should report what happened.

Pulse should handle the structure, calculations and system data.

A core principle is:

> **The user reports the event. Pulse owns the data structure and system time.**

Technicians should not be required to manually calculate:

- Expected production
- Lost packs
- Lost production time
- Run totals
- Overrun
- Performance against target

Pulse performs these calculations automatically.

---

# User Interfaces

Pulse is not dependent on a single communication channel.

The production engine should support multiple interfaces.

```text
                 TonnageFlow Pulse
                        │
                 Production Engine
                        │
          ┌─────────────┼─────────────┐
          │             │             │
     Pulse HMI       Web App      WhatsApp
      / Tablet                     Integration
          │             │             │
          └─────────────┼─────────────┘
                        │
                 Production Data
                        │
               Operational Database
                        │
                 Intelligence Layer
                        │
                 Director Dashboard
```

## Pulse HMI / Tablet

The primary factory-floor interface can run on a fixed tablet, touchscreen or industrial computer.

This is particularly useful in high-care manufacturing environments where personal mobile phones may not be permitted.

The device can remain within the production area and provide a simple interface for production updates.

## Web Interface

Managers, engineers and other authorised users can interact with Pulse through a browser-based interface.

## WhatsApp Integration

WhatsApp remains a potential input channel.

Where supported by Meta's APIs and suitable for the factory, WhatsApp integration can provide an additional method for submitting Pulse updates.

WhatsApp is therefore an integration channel rather than the foundation of the Pulse architecture.

---

# Production Run Lifecycle

## Stage 1 — Start Production Run

At the beginning of a Production Run, the Line Technician enters the production setup.

Example:

```text
Production Line: Rovema
Technician: Liam
Shift: Nights

Customer: Asda
Product: Basmati Rice

Pack Weight: 1kg
Packs per Case: 8
Pack Type: Pillow Pack

Target Speed: 120 packs/min

Cases per Pallet: 220

Pallets Remaining: 54

Previous Run Completed: 38 pallets
```

This creates the Production Run.

Pulse also creates a structured event representing the start of the run.

Example:

```text
Production Run
Production Run Started
Reported by: Liam
```

---

# Stage 2 — Production Model

Pulse calculates the theoretical production capability of the run.

Using:

```text
Target Speed = 120 packs/min
Packs per Case = 8
Cases per Pallet = 220
```

Pulse calculates:

```text
Expected Packs per Hour = 7,200

Expected Cases per Hour = 900

Expected Pallets per Hour = 4.09
```

This creates an independent production model against which actual production can be compared.

---

# Stage 3 — Production Measurement Window

For the current MVP, each hourly update represents a 60-minute production measurement window.

Pulse compares theoretical production during that period against reported actual production.

Future HMI versions can automatically manage the production timer and submission windows.

The Line Technician should not need to manually manage timestamps.

---

# Stage 4 — Hourly Production Update

The Line Technician provides a simple hourly update.

Example:

```text
OEE: 75%

Pallets Completed This Hour: 3

Planned Downtime:
Film Change

Unplanned Downtime:
None
```

Pulse then calculates the production performance for that period.

Example:

```text
Expected Packs: 7,200

Actual Packs: 5,280

Lost Packs: 1,920

Estimated Lost Production Time:
16 minutes
```

Pulse also updates the Production Run.

Example:

```text
Planned Pallets Completed: 7

Pallets Remaining: 47
```

---

# Reported OEE vs Calculated Production Performance

Pulse currently allows factories to record OEE because it is an established manufacturing measure.

However:

```text
Reported OEE
      ≠
Calculated Production Performance
```

Pulse independently calculates production performance using:

```text
Target Production
        ↓
Expected Output
        ↓
Actual Output
        ↓
Lost Output
        ↓
Estimated Lost Production Time
        ↓
Operational Reason
```

This allows Pulse to retain OEE while developing a more detailed view of production loss.

---

# Stage 5 — Planned Downtime

Current planned downtime categories include:

```text
Label Change
Film Change
CCP Check
Changeover
```

These are expected operational events.

Example:

```text
Planned Downtime
|
Film Change
|
Reported by: Line Technician
```

Planned downtime remains visible within the operational history of the Production Run.

---

# Stage 6 — Unplanned Downtime

Any other production stoppage is currently treated as unplanned downtime unless configured otherwise.

Examples:

```text
Casepacker Jam

Conveyor Stop

Machine Fault

Sensor Fault

Product Blockage
```

An unplanned event becomes part of the Production Run history.

Example:

```text
Unplanned Downtime
|
Casepacker Jam
|
Reported by: Liam
```

If engineering assistance is required, the engineering workflow begins.

---

# Engineering Response Workflow

Engineering should only enter the Pulse workflow when required.

The Line Technician owns the initial production event.

The Engineer owns the technical investigation and resolution.

The intended workflow is:

```text
Unplanned Downtime
        │
        ↓
Technician Reports Fault
        │
        ↓
Engineer Called
        │
        ↓
Engineering Event Open
        │
        ↓
Engineer Responds
        │
        ↓
Investigating
        │
        ↓
Finding / Action Recorded
        │
        ↓
Resolved or Ongoing
        │
        ↓
Production Resumes
```

Example technician event:

```text
Unplanned Downtime
Casepacker Jam
Reported by: Liam
```

Followed by:

```text
Engineering
Engineer Called
Reported by: Liam
```

Future engineering events could include:

```text
Engineering
Investigating Casepacker Jam
Reported by: Aaron
```

and:

```text
Engineering
Casepacker Fault Resolved
Reported by: Aaron
```

This separates the production report from the engineering verification.

---

# Stage 7 — Production Run Progress

Pulse continuously tracks the planned quantity remaining.

Example:

```text
Starting Pallets Remaining:
54

Hour 1:
4 completed
50 remaining

Hour 2:
3 completed
47 remaining
```

The Production Run does not automatically finish when planned quantity reaches zero.

The run remains active until the Line Technician confirms that production has finished.

---

# Planned Quantity Complete

When:

```text
Pallets Remaining = 0
```

Pulse reports:

```text
Planned quantity complete.
```

Pulse then asks:

```text
Is the Production Run finished?
```

If the answer is:

```text
No
```

the Production Run remains active.

Any additional pallets are separated from normal planned production.

---

# Potential Overrun

Production may continue after planned quantity reaches zero.

For example:

```text
Planned Quantity:
3 pallets

Planned Pallets Completed:
3

Additional Pallets Produced:
2
```

Pulse records:

```text
Potential Overrun:
2 pallets
```

These pallets are not automatically added to normal planned production.

---

# Product Changeover

If the next run uses a different product, additional pallets may be produced while emptying the remaining product from the system.

In this situation:

```text
Potential Overrun
        ↓
Product Changeover
        ↓
Confirmed Overrun
```

Example:

```text
Planned Pallets Completed: 3

Potential Overrun: 2

Confirmed Overrun: 2
```

---

# Customer Changeover

A customer changeover may occur while the same product continues.

Example:

```text
Asda Basmati
      ↓
Customer Changeover
      ↓
Tesco Basmati
```

Because the product remains the same, the system does not necessarily need to be emptied.

Therefore potential extra pallets are not automatically confirmed as product overrun.

Pulse records:

```text
Confirmed Overrun: 0
```

---

# Production Run Completion

When the Line Technician confirms the Production Run is finished, Pulse closes the run.

Example:

```text
=== Production Run Closed ===

Planned Pallets Completed:
3

Potential Overrun Pallets:
2

Confirmed Overrun Pallets:
2
```

Pulse also records:

```text
Production Run
Production Run Finished
Reported by: Liam
```

---

# Operational Event Model

Pulse stores operational activity as structured events.

Instead of storing only:

```text
Casepacker Jam
```

Pulse can store:

```python
{
    "event_type": "Unplanned Downtime",
    "reason": "Casepacker Jam",
    "reported_by": "Liam",
}
```

Current event families include:

```text
Production Run

Hourly Update

Planned Downtime

Unplanned Downtime

Engineering

Changeover
```

A Production Run therefore becomes a container containing a sequence of operational events.

Example:

```text
Production Run | Production Run Started | Reported by: Liam

Hourly Update | Hourly Update Received | Reported by: Liam

Planned Downtime | Film Change | Reported by: Liam

Hourly Update | Hourly Update Received | Reported by: Liam

Unplanned Downtime | Casepacker Jam | Reported by: Liam

Engineering | Engineer Called | Reported by: Liam

Production Run | Production Run Finished | Reported by: Liam

Changeover | Product Changeover | Reported by: Liam
```

This structured event history will become the foundation for the Pulse operational intelligence layer.

---

# System Time

Pulse should eventually record system timestamps automatically when events are submitted through the HMI, web interface or supported integrations.

The user should not normally be required to enter timestamps manually.

The principle is:

> **Users report events. Pulse records system time.**

Future versions may support retrospective event reporting where an estimated event time can optionally be supplied.

---

# Factory Roles

## Line Technician

The Line Technician is the primary factory-floor Pulse user.

Responsibilities include:

- Start Production Run
- Confirm production setup
- Submit hourly updates
- Report planned downtime
- Report unplanned downtime
- Request engineering support
- Confirm planned quantity completion
- Confirm Production Run completion

The Line Technician owns production reporting.

---

## Engineer

Engineers enter the workflow when technical support is required.

Responsibilities include:

- Respond to unplanned downtime
- Accept engineering events
- Record investigation
- Record technical findings
- Record corrective action
- Mark fault as resolved or ongoing

The Engineer owns engineering verification.

---

## Manager

Managers are responsible for production planning and operational coordination.

Future Pulse functions may include:

- Production planning
- Run priorities
- Line allocation
- Labour allocation
- Delegation
- Production exceptions
- Changeover planning

---

## Director

Directors consume the operational intelligence created by Pulse.

The Director should not need to read individual factory-floor messages.

Pulse should convert production activity into information such as:

- Production performance
- Production volatility
- Lost production
- Planned downtime
- Unplanned downtime
- Engineering response
- Recurring faults
- Run performance
- Changeover performance
- Overrun
- Operational Drag
- Cost per Tonne impact

---

# Core Business Objects

Pulse is being designed around structured business objects.

Current and planned objects include:

```text
Production Run

Production Event

Hourly Update

Downtime Event

Engineering Event

Changeover

Production Performance

Production Line

Product

Customer

Shift

Line Technician

Engineer
```

The Production Run acts as the main container.

Production Events describe what happened during that run.

---

# Current Production Lines

The current prototype contains:

```text
Rovema
GIC
Guill
```

Each line currently has four placeholder Line Technician records.

---

# Current Planned Downtime Rules

The current prototype classifies the following as planned downtime:

```text
Label Change
Film Change
CCP Check
Changeover
```

Other stoppages are treated as unplanned unless configured otherwise.

---

# Technology Direction

The current prototype is being developed in Python.

The terminal interface is temporary and is being used to build and test the production engine before introducing the graphical interface.

The intended architecture is:

```text
Factory Interface
       │
       ↓
Pulse HMI / Web Application
       │
       ↓
API Layer
       │
       ↓
Python Production Engine
       │
       ↓
Operational Database
       │
       ↓
Operational Intelligence
       │
       ↓
Director Dashboard
```

Potential technologies include:

```text
Python

FastAPI

SQL Database

Browser-based HMI

Progressive Web Application (PWA)

Power BI / Pulse Dashboard

AI / Operational Intelligence Layer
```

The architecture should allow additional communication channels, including WhatsApp, to connect to the same production engine.

---

# Current Development Status

The current Python prototype can:

- Start a Production Run
- Capture production setup
- Calculate theoretical hourly output
- Capture hourly updates
- Calculate actual production
- Estimate lost packs
- Estimate lost production time
- Track planned pallets completed
- Track pallets remaining
- Record planned downtime
- Record unplanned downtime
- Record engineer-called events
- Store structured operational events
- Continue a run after planned quantity reaches zero
- Separate potential overrun from planned production
- Confirm overrun during Product Changeover
- Handle Customer Changeover
- Close a Production Run
- Start another Production Run
- Close the Pulse session

---

# Development Roadmap

## Current Phase

Build and validate the core Production Run engine.

## Next Phase

Engineering response workflow:

```text
Unplanned Downtime
        ↓
Engineer Called
        ↓
Engineer Responds
        ↓
Investigating
        ↓
Finding / Action
        ↓
Resolved / Ongoing
```

## Future Phases

- Data persistence
- Automatic system timestamps
- Production Run history
- Shift summaries
- Factory HMI
- Tablet interface
- User authentication
- Role-based interfaces
- Manager workflows
- Director dashboard
- Operational Drag analysis
- Cost per Tonne intelligence
- AI operational analysis
- Optional WhatsApp integration

---

# Long-Term Direction

TonnageFlow Pulse is intended to become more than an OEE data-entry tool.

The long-term goal is to create a structured digital history of what actually happened during production.

Instead of relying on disconnected spreadsheets, messages and reports, Pulse can create a sequence of operational events for every Production Run.

That creates the foundation for TonnageFlow to analyse:

```text
What was planned?

What actually happened?

Where was production lost?

Why was it lost?

What intervention occurred?

Was the issue resolved?

How predictable was the run?

What Operational Drag was created?

What was the impact on Cost per Tonne?
```

The objective is to turn factory-floor activity into operational intelligence that helps manufacturing teams improve production stability, predictability and profitability.