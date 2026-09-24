# ADR-001: Platform for Revit automation

**Status:** Proposed · **Date:** 24 Sep 2026 · **Deciders:** BIM Lead, BIM Coordinators

## Context
The team keeps automating the same Revit tasks: renumbering sheets and views, filling parameters, QA checks, exporting schedules and IFC, and preparing for clashes. Today each person scripts in their own way, so nothing is shared, versioned or maintained. We need one main platform so tools can be reused, reviewed and handed over.

## Decision
Use **pyRevit (Python) as the main platform** for team tools. Keep **Dynamo** for visual, geometry-heavy and one-off design logic. Use **C# add-ins** only for performance-critical or product-grade tools, such as event handlers, modeless UIs and tools used across the whole company.

## Options considered

| | Dynamo | pyRevit | C# add-in |
|---|---|---|---|
| Complexity | Low | Medium | High |
| Cost | Free, built in | Free, open source | Free, but needs Visual Studio and a build pipeline |
| Scalability | Poor: large graphs are slow and hard to maintain | Good: plain code, works with Git, easy to share as a toolbar | Best: full Revit API, fastest |
| Team familiarity | High for most BIM staff | Medium: needs basic Python | Low: needs a developer |
| Deployment | Share .dyn files; Dynamo Player | One extension folder from a Git repo; a toolbar ribbon | An installer or .addin manifest per Revit version |
| Version upgrades | Packages often break between Revit versions | Usually just works | Must be rebuilt for each Revit version (.NET 8 from Revit 2025) |

**Dynamo:** easy to start with, and designers can use it. But its graphs don't diff well in Git, depend on fragile packages, and get slow on large models.

**pyRevit:** fast to write, reviewable in Git, and puts tools on a ribbon in one step. But it has no compile-time checks, some edge cases need the IronPython/CPython engine, and it depends on the community.

**C#:** full API access (dockable panes, updaters, events), the best performance, and robust. But it needs a developer, builds per Revit version, and has the slowest development cycle.

## Trade-off analysis
The biggest factors are **maintenance and handover**, not raw capability. pyRevit gives the team about 80% of C#'s reach and nearly Dynamo's speed of writing, and it can be versioned in Git. Dynamo stays useful for parametric geometry and for designers who don't write code. C# is only worth its cost when a tool needs events, a modeless UI, or has to run on very large models.

## Consequences
- **Easier:** a shared, versioned toolbar; code review; onboarding through one ribbon.
- **Harder:** staff need basic Python skills, and someone must own the extension repo.
- **Revisit:** if more than two tools need events or a modeless UI, set up a small C# layer. pyRevit can call it.

## Action items
1. [ ] Create a team pyRevit extension repo with a folder structure and README.
2. [ ] Move the three most-used Dynamo graphs that aren't geometry work to pyRevit.
3. [ ] Write coding standards for transactions, error handling and Revit version checks.
4. [ ] Set Dynamo package versions for each Revit version.
5. [ ] Arrange a 2-hour pyRevit starter session for coordinators.
