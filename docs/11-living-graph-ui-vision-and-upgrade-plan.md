# Living Graph UI Vision And Upgrade Plan

> Historical vision and implementation record. Current Sigma/Graphology, Three.js, LOD, accessibility, hardware, and
> production-size acceptance evidence is tracked in `14-graphview-1.0-upgrade-ledger.md` and `05-testing.md`.

## Purpose

This document upgrades Graphview's product vision around the visual knowledge graph as the center of the user
experience. It defines what should feel alive, how users and agents should interact with the graph, what exists today,
what must be developed, what needs an overhaul, and a phased implementation plan.

The goal is to move Graphview from a graph-backed knowledge workspace to a living digital nervous system interface:
the graph should sense new knowledge, show active reasoning, react to user attention, visualize agent work, and make
reviewable changes visible before they become durable memory.

## North Star

Graphview's main UI should feel like a living map of organizational memory. The graph is not a static chart inside a
workspace. It is the workspace.

Users should be able to watch knowledge move through the system:

```text
source signal -> source chunks -> agent scan -> candidate entities -> candidate relationships -> review gate -> durable graph memory
```

Agent work should be visible in the graph itself. When an agent researches, scans evidence, opens details, finds a
relationship, proposes a node, or waits for review, the graph should show that activity through meaningful motion,
linked tooltips, graph flows, and status states.

## Design Position

### The Graph Is The Center

The visual graph should remain the dominant first-viewport object in the Graph workspace. Side panels, command bars,
review queues, source readers, and AI controls should support the graph rather than compete with it.

The user should always understand:

- What is selected.
- What is related.
- What is being scanned.
- What is being proposed.
- What is trusted.
- What is pending review.
- What the agent is doing now.

### Alive Means Meaningful

The graph should feel alive through stateful, meaningful motion. It should not use decorative movement. Every motion
should represent product state:

- A node pulse means activity or new evidence.
- A flowing edge means traversal, citation path, or relationship discovery.
- A scan wave means an agent is reading context.
- A ghost node means a candidate proposal.
- A locked-in transition means review acceptance.
- A fading transition means rejection or removal from attention.
- A blocked edge state means unresolved endpoint dependency.

### 2D And 3D Must Share The Same Semantics

2D and 3D can render differently, but they must expose the same interaction model:

- Hover reveals node details through linked tooltip geometry.
- Selection anchors a detail card to the node.
- Related nodes and edges highlight together.
- Agent scans, research flows, proposal previews, and review outcomes are visible.
- Motion can be reduced or disabled through accessibility preferences.

## What Exists Today

| Area | Current state | Assessment |
| --- | --- | --- |
| Graph as center | The `GraphCanvas` is the central workspace surface. | Good foundation. The graph is visible and interactive, but it still feels mostly static. |
| Layout modes | Force, Radial, Arc, 2D, and projected 3D modes exist. | Good exploratory base. 3D is currently a projection, not a full spatial interaction system. |
| Selection | Clicking a node selects it and opens Focus context. | Good. Needs richer camera choreography and anchored detail overlays. |
| Search | Graph search dims unrelated nodes and highlights matches. | Useful. Needs animated search reveal and path-to-result affordances. |
| Related context | Context pane shows evidence and related graph items. | Good information model. Needs direct visual links from graph nodes to tooltips and evidence. |
| Pending proposals | Pending relationship proposals can render as graph edges. | Good trust signal. Needs ghost states, proposal previews, and review transition animations. |
| Content expansion | Source chunks, proposals, review activity, and planning tasks can appear as expansion nodes. | Strong foundation for living graph behavior. Needs stronger visual hierarchy and motion. |
| AI command panel | Users can ask, summarize, research, and inspect citations. | Good agent surface. Needs in-graph agent activity, not only panel feedback. |
| Citation drawer | Citations and action proposals are inspectable. | Good audit layer. Needs graph-linked citations and path animation from answer to evidence. |
| Planning Mode | Planning sessions and build specs exist separately. | Useful. Needs better visual bridge from plan tasks into graph activity. |

## What Is Missing

| Missing capability | Why it matters |
| --- | --- |
| Motion language | Without consistent motion semantics, the graph cannot feel alive in a trustworthy way. |
| Hover-linked tooltips | Users need immediate details without losing graph context. |
| Node-to-tooltip visual tethers | Tooltips should feel attached to graph objects in 2D and 3D. |
| Graph activity event model | Agent work needs a durable, renderable stream of graph activity events. |
| Agent scan visualization | Research and Q&A should visibly scan nodes, edges, chunks, and citations. |
| Proposal ghosting | Candidate nodes and edges should preview before review commit. |
| Review transition animation | Accept, reject, edit, defer, and blocked states should be visually distinct. |
| Camera choreography | Selecting, asking, researching, or reviewing should move the graph intentionally. |
| Evidence path visualization | Users need to see how an answer or proposal connects to source chunks. |
| 3D spatial overlays | 3D needs projected labels, hit targets, depth-aware tethers, and non-overlapping details. |
| Reduced-motion mode | Living UI must remain usable and accessible for users who reduce motion. |
| Performance budget | Animated large graphs need strict budgets and quality fallbacks. |

## What Needs An Overhaul

| Area | Current shape | Needed shape |
| --- | --- | --- |
| Graph rendering state | Mostly derived from nodes, edges, layout, selection, search, and content expansion. | Explicit visual state machine for idle, hover, select, scan, propose, review, accepted, rejected, blocked, stale, and cited. |
| Tooltip model | Browser titles and side-panel context. | Anchored rich tooltips with tethers, collision handling, keyboard focus, and 2D/3D parity. |
| Agent feedback | Agent activity appears mostly in panels and cards. | Agent activity is visible directly in the graph through scans, flows, ghost proposals, citations, and review gates. |
| Review UI | Review lives in context pane and worklist cards. | Review should also happen visually on graph objects, with proposal previews and commit transitions. |
| Evidence UI | Evidence is readable in a card or modal. | Evidence should visually connect to nodes, citations, agent scans, and proposal creation. |
| 3D mode | Projected 3D effect inside SVG. | Upgrade path to a true 3D interaction layer when scale and interaction needs justify it. |
| Activity persistence | Agent runs and tool calls exist, but graph activity is not a first-class stream. | Add graph activity records/events that can replay what happened. |

## Target Experience

### Idle State

The graph rests as a living memory map:

- Nodes have subtle status-specific presence, not constant movement.
- High-value or recently active nodes have a faint pulse.
- Pending proposals appear as ghosted nodes or dashed edges.
- Stale sources, blocked proposals, and high-attention items are visible but restrained.
- The graph never feels like a screensaver; it feels responsive and ready.

### Hover State

Hovering a node should produce immediate local understanding:

1. The hovered node brightens and slightly lifts.
2. Direct neighbor nodes remain visible; unrelated nodes dim.
3. Connected edges animate lightly in the correct direction where direction matters.
4. A rich tooltip opens near the node.
5. A visual tether links the node to the tooltip.
6. The tooltip shows label, kind, summary, provenance count, confidence or review state, top source, and actions.
7. Keyboard focus triggers the same behavior.

For 3D, the tooltip should use screen-space projection from the node's 3D position. The tether should anchor to the
projected node location and adjust as the camera orbits.

### Selection State

Selecting a node should make the graph reorganize around intent:

1. Camera pans or zooms toward the selected node.
2. The node locks into focus styling.
3. Related edges flow outward or inward.
4. The context pane opens to Focus or Evidence.
5. A pinned detail card remains tethered to the node until dismissed or another node is selected.
6. Source chunks and citations can fan out around the selected node when Sources is enabled.

### Evidence Scan

When the user asks about a node, source, or passage:

1. The selected scope glows.
2. A scan wave travels across relevant nodes, source chunks, and citation edges.
3. Candidate evidence nodes briefly highlight in sequence.
4. The answer appears with citation markers.
5. Citation markers remain linked to graph nodes or source chunks.
6. Opening a citation animates the path from answer to evidence.

### Agent Research Flow

When an agent extends research inside the graph, the user should see the work unfold:

1. The research command anchors to the active node, source, or graph scope.
2. The active scope pulses as the agent starts.
3. A scan field moves through nearby graph context and source chunks.
4. External or connector-derived sources enter as incoming signals.
5. Candidate source chunks appear as small evidence particles or source nodes.
6. Candidate entities appear as ghost nodes.
7. Candidate relationships appear as ghost edges with animated flow.
8. Citations attach to each candidate as small evidence anchors.
9. The graph pauses at a review gate.
10. Accepted proposals solidify into durable nodes and edges.
11. Rejected proposals dissolve.
12. Edited proposals morph into their edited label, kind, or relationship.

### Review Flow

Review should be visible in the graph:

- Ready proposals are actionable ghost objects.
- Blocked relationship proposals show missing endpoint markers.
- Accepting a node changes it from ghost to solid.
- Accepting an edge changes it from dashed to solid and runs a brief confirmation flow.
- Rejecting fades the object and removes it from the proposal layer.
- Editing animates the object through the changed label, kind, or relation.
- Deferring quiets the object but keeps it visible in the attention layer.

### Planning-To-Graph Flow

Planning should connect visually to the graph:

- Build spec topics appear as planning nodes.
- Open questions appear as unresolved attention nodes.
- Research tasks appear as queued agent paths.
- Launching a task moves from the plan artifact into the graph scope.
- Completed research returns as source, proposal, and review-gated action visuals.

## Visual State Model

Graph objects need explicit visual states independent of their domain state.

| Visual state | Applies to | Meaning |
| --- | --- | --- |
| `idle` | Node, edge | Stable reviewed graph item. |
| `hovered` | Node, edge | User attention is on this item. |
| `focused` | Node, edge, source chunk | Selected item or active scope. |
| `related` | Node, edge | Directly connected to focus or hover. |
| `dimmed` | Node, edge | Outside current attention scope. |
| `scanning` | Node, edge, chunk | Agent is reading or retrieving this context. |
| `cited` | Node, edge, chunk | Used in an answer, proposal, or research result. |
| `incoming` | Source, chunk, node | Newly ingested or streaming into graph. |
| `candidate` | Node, edge | Proposed but not reviewed. |
| `ready` | Proposal node, proposal edge | Ready for review commit. |
| `blocked` | Proposal edge | Cannot commit until endpoint dependency is resolved. |
| `accepted` | Node, edge | Just committed into durable graph memory. |
| `rejected` | Candidate | Rejected and exiting the active graph layer. |
| `edited` | Candidate, node, edge | Changed through review. |
| `deferred` | Candidate | Kept for later attention. |
| `stale` | Source, node, edge | Source or knowledge needs freshness review. |

## Motion Language

| Motion | Use | Notes |
| --- | --- | --- |
| Pulse | Activity, freshness, selected scope, incoming signal. | Keep subtle; avoid constant global pulsing. |
| Flow | Relationship traversal, citation path, agent reasoning path. | Direction matters for directed relations. |
| Scan wave | Agent reading context or source chunks. | Should be bounded to the active scope. |
| Ghost reveal | Candidate proposal appears. | Use transparency and dashed edges. |
| Solidify | Proposal accepted. | Candidate becomes durable graph memory. |
| Dissolve | Proposal rejected. | Fade and shrink, then remove. |
| Morph | Proposal edited. | Animate label/relation/kind transition where possible. |
| Orbit/pan | Camera focuses on selected or active scope. | Avoid disorienting movement; preserve user control. |
| Tether draw | Tooltip or citation attaches to graph object. | Must update during pan, zoom, and 3D orbit. |
| Ripple | New source or research result propagates into nearby graph context. | Use sparingly for system events. |

## Required Data And Event Model

The UI needs a graph activity model that can drive animation, replay, and audit. This does not replace proposals,
review decisions, agent runs, or provenance. It gives the renderer a stable stream of visualizable events.

Proposed event shape:

```ts
type GraphActivityEventKind =
  | "source.ingesting"
  | "source.chunked"
  | "agent.scan.started"
  | "agent.scan.item"
  | "agent.scan.completed"
  | "proposal.created"
  | "proposal.ready"
  | "proposal.blocked"
  | "review.accepted"
  | "review.rejected"
  | "review.edited"
  | "review.deferred"
  | "graph.node.added"
  | "graph.edge.added"
  | "citation.linked"
  | "action.pending_review"
  | "action.approved"
  | "sync.started"
  | "sync.completed";

interface GraphActivityEvent {
  id: string;
  kind: GraphActivityEventKind;
  graphId: string;
  actorId?: string;
  agentRunId?: string;
  sourceId?: string;
  sourceChunkId?: string;
  proposalId?: string;
  nodeId?: string;
  edgeId?: string;
  relatedNodeIds: string[];
  relatedEdgeIds: string[];
  citationIds: string[];
  status: "queued" | "running" | "waiting_for_review" | "completed" | "failed" | "blocked";
  summary: string;
  createdAt: string;
}
```

Needed API surfaces:

- `GET /graph/activity?graph_id=...&limit=...`
- `GET /agent-runs/{agent_run_id}/activity`
- Optional later stream: `GET /graph/activity/stream`

The first implementation can derive activity events from existing records: ingestion runs, proposals, review decisions,
agent runs, research tasks, action proposals, connector sync runs, and citations.

## Technical Upgrade Plan

### Track 1: Interaction And Motion Foundation

Goal: Add a motion and visual state system without changing graph persistence.

Work:

- Add a graph visual state model in the web app.
- Add motion tokens for duration, easing, pulse intensity, scan speed, opacity, and reduced-motion fallbacks.
- Add hover, focus, related, dimmed, candidate, blocked, cited, and scanning classes to graph nodes and edges.
- Add `prefers-reduced-motion` handling and a user setting to reduce or disable graph animation.
- Add transition budgets so large graphs degrade gracefully.

Acceptance criteria:

- Hover and focus states are visually distinct.
- Reduced-motion mode removes nonessential animation.
- Large graphs still render within the existing render budget.
- Motion conveys state, not decoration.

### Track 2: Hover Tooltips And Visual Tethers

Goal: Make node details immediately available inside the graph.

Work:

- Build a `GraphTooltipLayer` that renders rich HTML or SVG overlays above the graph.
- Add tooltip content for node label, kind, summary, provenance count, source, review state, confidence, and actions.
- Add collision handling so tooltips stay inside the viewport.
- Draw a tether from node to tooltip.
- Support hover and keyboard focus.
- Keep the tooltip positioned during pan, zoom, and layout changes.
- Add a 3D projection adapter so 3D nodes can anchor screen-space tooltips.

Acceptance criteria:

- Hovering any visible node opens a readable tooltip in 2D.
- Tooltip tether remains attached while zooming or panning.
- Keyboard focus produces the same tooltip content.
- Tooltip text does not overlap graph controls or leave the viewport.

### Track 3: Camera And Focus Choreography

Goal: Make graph movement support user intent.

Work:

- Add a camera controller with explicit commands: `focusNode`, `fitSelection`, `tracePath`, `openEvidence`, and
  `followAgentRun`.
- Animate camera pan and zoom with interrupt support.
- Preserve user control by stopping camera animation on manual pan, zoom, or orbit.
- Add path tracing for selected node relationships, citation paths, and shortest paths.
- Add neighborhood reveal around selected nodes.

Acceptance criteria:

- Selecting a node moves the graph toward focus without disorientation.
- Manual user input immediately overrides scripted camera movement.
- Path tracing can highlight source, target, and intermediate graph items.

### Track 4: Agent Activity Visualization

Goal: Show agent research and graph Q&A inside the graph.

Work:

- Derive graph activity events from agent runs, agent tool calls, citations, research tasks, and proposals.
- Add an activity overlay for scan waves, active paths, and candidate proposal previews.
- Add agent run states: queued, scanning, synthesizing, proposing, waiting for review, completed, failed.
- Animate Graph AI Q&A as read-only scan and citation-link events.
- Animate Graph AI research as scan, incoming source, ghost proposal, review gate, and action proposal events.
- Link citation drawer entries back to graph nodes, edges, or source chunks with path animation.

Acceptance criteria:

- Asking a graph question visibly scans relevant context and highlights cited items.
- Running research shows candidate nodes and edges before review.
- Action proposals are visible as review-gated graph activity.
- Failed or blocked agent work has a clear visual state.

### Track 5: Proposal And Review Animation

Goal: Make graph mutation review visible and trustworthy.

Work:

- Render proposal nodes and edges in a distinct candidate layer.
- Add ready, blocked, accepted, rejected, edited, and deferred visual transitions.
- Show missing endpoint markers for blocked relationship proposals.
- Let reviewers act from a graph-linked tooltip or detail card while preserving the Needs attention queue.
- Animate commit results after review decisions.
- Keep provenance and source links visible during review.

Acceptance criteria:

- Reviewers can see which candidate graph objects are ready or blocked.
- Accepting a proposal visibly solidifies it into the reviewed graph.
- Rejecting or deferring proposals visibly changes the proposal layer.
- Review actions remain auditable and do not bypass API review decisions.

### Track 6: Evidence And Source Flow Visualization

Goal: Make evidence part of the graph, not only side-panel content.

Work:

- Represent source chunks as optional evidence nodes around selected graph items.
- Add source-to-node and citation-to-node path highlights.
- Animate source ingestion as incoming source chunks resolving into proposals.
- Add passage-level actions in graph-linked tooltips: ask, research, add to graph, open source.
- Add citation anchors that can be selected from the graph or answer panel.

Acceptance criteria:

- Opening evidence visually connects source chunks to graph items.
- Citation selection highlights the source chunk and graph path.
- Adding a passage to the graph creates a visible candidate proposal.

### Track 7: True 3D Interaction Upgrade (Implemented)

Goal: Keep the delivered true spatial 3D graph semantically aligned with the primary Sigma 2D renderer.

Work:

- Retain the dedicated, lazy Three.js renderer boundary and the non-WebGL SVG fallback.
- Keep the existing graph-core layout contracts and visual state model renderer-agnostic.
- Add 3D hit testing, depth-aware labels, camera orbit, tooltip projection, and tether projection.
- Add pixel/screenshot checks for nonblank 3D rendering.
- Keep 2D as the default for scanning and review-heavy workflows unless 3D improves comprehension.

Acceptance criteria:

- 3D supports hover, selection, linked tooltips, scan flows, candidate proposals, and citation paths.
- 3D never hides review state, evidence, or blocked status.
- Users can switch between 2D and 3D without losing selection or agent activity context.

### Track 8: Performance, Accessibility, And QA

Goal: Keep the living graph usable, measurable, and safe.

Work:

- Define animation budgets by graph size.
- Add render degradation rules: full motion, reduced motion, static state, sampled graph.
- Add keyboard navigation for nodes, tooltips, and review actions.
- Add ARIA labels for graph activity and agent state.
- Add Playwright screenshot tests for desktop and mobile graph states.
- Add pixel checks for 2D and 3D nonblank graph rendering.
- Add tests for reduced-motion behavior.
- Add source-contract checks for `GraphVisualState`, `GraphTooltipModel`, `GraphActivityEvent`, `/graph/activity`,
  `/agent-runs/{agent_run_id}/activity`, tooltip/tether selectors, candidate layers, and activity layers.
- Add tooltip URL browser checks for external target behavior, `rel` protection, and no current-workspace navigation on
  hover.
- Add story/demo states for idle, hover, selected, scanning, candidate, blocked, accepted, rejected, and failed.

Acceptance criteria:

- Animations do not break keyboard or screen-reader workflows.
- Mobile graph controls do not overlap tooltips or action cards.
- Large graph rendering remains bounded.
- The graph remains comprehensible when motion is reduced.

## Phase 24 QA Contract

Phase 24 QA has two layers:

- Source contracts in `apps/web/tests/shell.test.mjs` fail if the web app does not consume the shared visual state,
  tooltip, and activity models or does not reference graph activity routes.
- Browser contracts in `apps/web/tests/browser/` fail if 2D or 3D graph rendering is blank, if a rich tooltip does not
  appear with a visible tether, or if source URL actions are unsafe.

Required test selectors:

- `data-testid="graph-canvas-root"` on the graph root that carries the active 2D/3D class.
- `data-testid="graph-canvas-surface"` on the SVG or canvas surface used for pixel checks.
- `data-testid="graph-tooltip"` on the rich tooltip.
- `data-testid="graph-tooltip-tether"` on the visible tether line or overlay.
- `data-testid="graph-tooltip-source-url"` on source URL actions inside graph-linked tooltips.

These selectors are part of the QA contract, not product copy. They should remain stable across SVG and Three.js
renderer experiments.

## Suggested Implementation Phases

### Phase 24A: Living Graph Foundation

Scope:

- Visual state model.
- Motion tokens.
- Hover and focus states.
- Rich node tooltips with 2D tethers.
- Reduced-motion support.

Outcome: The existing graph feels responsive and stateful without changing backend contracts.

### Phase 24B: Graph-Linked Evidence

Scope:

- Evidence nodes and source chunk fan-out refinement.
- Citation path highlighting.
- Source-to-node tethers.
- Passage actions from graph-linked details.

Outcome: Users can see why a node exists and move between graph and source evidence fluidly.

### Phase 24C: Agent Activity In The Graph

Scope:

- Derived graph activity events.
- Agent scan visualization.
- Research flow visualization.
- Ghost proposal nodes and edges.
- Citation-linked AI answer paths.

Outcome: Users can watch the agent work inside the graph instead of only reading status cards.

### Phase 24D: Review-Gated Mutation Animation

Scope:

- Candidate proposal layer.
- Review transition animations.
- Blocked endpoint markers.
- Graph-linked review detail cards.

Outcome: The graph visibly changes through review, preserving trust in every mutation.

### Phase 24E: 3D Interaction Parity

Scope:

- 3D tooltip projection.
- 3D tethers.
- 3D scan and proposal visualization.
- Renderer evaluation for true 3D.

Outcome: 3D becomes a real exploration mode, not only a stylistic view.

### Phase 24F: Activity Persistence And Streaming

Scope:

- `GraphActivityEvent` derivation.
- Activity list endpoints.
- Optional server-sent event stream.
- Replay of recent graph activity.

Outcome: The living graph can show live, recent, and replayed activity consistently.

## Engineering Architecture

Recommended frontend layers:

```text
Graph data
  -> graph-core layout plan
  -> visual state resolver
  -> activity event reducer
  -> renderer adapter
  -> tooltip/tether overlay
  -> camera controller
```

Key boundaries:

- Domain state stays in API records: sources, chunks, proposals, review decisions, agent runs, research tasks.
- Visual state is derived in the web app or from graph activity events.
- Renderer-specific code should not own product logic.
- 2D and 3D renderers should consume the same visual state and activity event contracts.

## Design Rules

- The graph is the primary surface.
- Motion must communicate system state.
- Tooltips must be attached to graph objects with visible tethers.
- Hover, keyboard focus, and selection must reveal equivalent information.
- Agent work must be visible in the graph, not only in panels.
- Candidate graph changes must look different from reviewed graph memory.
- Review outcomes must animate through the graph.
- Every AI-generated graph extension must show citations and review state.
- 2D remains the default for clarity; 3D is an explicit exploration dimension.
- Reduced-motion mode is required, not optional.

## Redesign Decisions

| Decision | Direction |
| --- | --- |
| Keep graph center | Yes. Do not turn the product into a dashboard with a graph preview. |
| Keep review gates | Yes. Agent visualizations must not imply unreviewed work is trusted. |
| Keep side panels | Yes, but make them secondary to graph-linked overlays and visual paths. |
| Add motion | Yes, but only stateful motion with clear semantic meaning. |
| Add rich tooltips | Yes. This is a core interaction upgrade. |
| Add true 3D immediately | Not necessarily. First build renderer-agnostic state, tethers, and activity semantics. Then upgrade 3D when the interaction model is proven. |
| Replace current GraphCanvas | Not immediately. Evolve it for Phase 24A-24D, then decide whether WebGL/Three.js is required. |

## Open Product Questions

- Which graph events should be live-streamed versus derived from existing records?
- Should graph activity replay be user-facing or only useful for debugging and demos?
- What is the maximum graph size for full animation before static degradation begins?
- Which agent actions deserve graph animation versus simple status indicators?
- Should review actions be allowed directly from graph tooltips, or should tooltips deep-link to the Needs attention pane?
- What are the exact visual encodings for stale knowledge, conflicts, low confidence, and blocked actions?
- When should 3D become a primary workflow instead of an exploration option?

## Definition Of Done For The Living Graph Upgrade

The upgrade is complete when:

- The graph remains the center of the Graph workspace.
- Hovering or focusing a node opens a rich, tethered detail overlay.
- Selecting a node animates focus and related graph context.
- Evidence and citations visually connect to graph objects.
- Graph Q&A visibly scans and cites graph context.
- Agent research visibly creates incoming sources, candidate nodes, candidate edges, and review-gated actions.
- Review decisions visibly transform candidate graph objects into accepted, rejected, edited, or deferred states.
- 2D and 3D share the same interaction semantics.
- Reduced-motion mode is fully supported.
- Large graphs degrade gracefully without becoming blank, jittery, or unreadable.
- Every animated graph mutation remains backed by source, proposal, review, and provenance records.
