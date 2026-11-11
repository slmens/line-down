# Line Down: Project Summary

November 10, 2026

## What it is

Line Down is a system that watches Toronto’s transport network and measures what happens when part of it fails.

The core case is a subway disruption. When a line goes down, the system tracks how the effect spreads to nearby bike share stations, how far it reaches and how long recovery takes. A later phase adds highway incidents and traffic cameras to the same system.

## Its purpose

The project has two purposes, one for the project itself and one for the person building it.

### The project’s purpose

To answer a real question with real data: when a subway line fails, where do people go, and can that be predicted as it happens? In practice it does three things:

- Measures past disruptions, using years of TTC delay records and bike share trips.
- Predicts new ones as they start: how long the delay will last and which bike docks will empty.
- Shows the result on an animated pixel map of Toronto, with an agent that writes a short brief for each incident.

### The builder’s purpose

To prove, in one piece of work, the skills that data teams hire for.

| Skill | Where it shows |
|-------|----------------|
| Data engineering | Live collectors, a warehouse, tested and re-runnable pipelines |
| Data analysis | A measured finding about the city, with honest statistics |
| Machine learning | Prediction models scored against a simple baseline |
| AI agents | An agent whose accuracy is measured and published |
| Communication | A map anyone in Toronto understands in ten seconds |

## Why this project over the others

- The data is confirmed. The TTC alert feed, the delay history, the live bike share feed and the bike trip history all exist.
- The history is long enough to analyse and train models immediately, without waiting weeks to collect data.
- Every interviewer in Toronto rides the TTC, so the finding needs no explanation.
- It can grow. Highways and cameras attach to the same pipeline later.

## How it gets built

The map, the models and the agent are the fun parts and will pull the time. If the collectors and warehouse end up as a few scripts and a folder of CSVs, the project teaches analysis and machine learning but little data engineering. Three rules prevent that.

### The pipeline comes first and is the product

The code that fetches and stores data is built before the map, the models or the agent, and held to the standard of something people depend on. The map is one consumer of a solid data system, not the reason the data system exists.

### The collectors run unattended for weeks

Running a collector once while watching is easy. The real problems only appear when it runs for a long time without anyone touching it:

- The feed goes down at 3am. The collector retries and carries on instead of crashing.
- The feed returns the same alert twice. It is stored once.
- The machine restarts. The collector comes back on its own.
- The collector stops. Something reports it.

### The warehouse rebuilds from raw with one command

Raw data is kept exactly as it arrived. Everything else (cleaned tables, joined tables, the numbers behind the map) is produced from it by code. The test: delete every produced table, run one command, and get them all back, identical.

- A bug in the cleaning logic is fixed by correcting the code and rebuilding, not by hand-patching tables.
- Nothing depends on a manual step done once and forgotten.
- Anyone can reproduce the finding from scratch, which is what makes the statistics credible.

## What it will not teach

- Scale. The data fits on a laptop, so Spark, partitioning strategy and cost tuning never become necessary.
- True streaming. Polling a feed every 30 seconds is micro-batch, not Kafka-style streaming.
- Team concerns. Access control, schema changes that break other people's dashboards, on-call.
