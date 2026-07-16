from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import insert, select

DEMO_PROJECT_ID = "project-ios26-swift-demo"
DEMO_TIMESTAMP = datetime(2026, 6, 5, tzinfo=UTC)
DEMO_ACTOR_ID = "demo-author"
DEMO_EMBEDDING_MODEL = "graphview-demo-seed-v1"


DEMO_SOURCES = [
    ("src-ios26-whats-new", "Apple iOS 26 Whats New", "url", "https://developer.apple.com/ios/whats-new/"),
    ("src-swiftui-docs", "Apple SwiftUI Documentation", "url", "https://developer.apple.com/documentation/swiftui/"),
    (
        "src-liquid-glass",
        "Apple Liquid Glass Technology Overview",
        "url",
        "https://developer.apple.com/documentation/technologyoverviews/liquid-glass",
    ),
    ("src-app-intents", "Apple App Intents Documentation", "url", "https://developer.apple.com/documentation/appintents"),
    ("src-swiftdata", "Apple SwiftData Documentation", "url", "https://developer.apple.com/documentation/swiftdata"),
    ("src-team-blueprint", "Native iOS 26 Swift App Blueprint", "markdown", "local://demo/ios26-swift-blueprint.md"),
]


DEMO_SOURCE_CONTENT = {
    "src-ios26-whats-new": """# Apple iOS 26 Whats New

The iOS 26 planning surface starts with the current SDK, simulator coverage, app icon updates, and release readiness work. Teams should validate existing app behavior with the latest Xcode and iOS SDK before adopting new platform capabilities.

Relevant demo topics include Xcode 26 and iOS 26 SDK, Icon Composer and Asset Catalogs, Apple Developer Documentation, and App Store Connect. The graph links these items so release planning can trace toolchain choices back to the sources that motivated them.

Release notes, app metadata, icon appearance, and SDK migration checks should be reviewed together because a visual or signing change can affect TestFlight rollout, App Store review, and user-facing launch quality.""",
    "src-swiftui-docs": """# Apple SwiftUI Documentation

SwiftUI defines the app structure for the demo: app entry points, scenes, navigation, previews, shared widgets, and Swift Charts. It also provides the integration boundary for UIKit interoperability where imperative lifecycle control is still required.

The source content connects SwiftUI App Structure to Navigation Architecture, Observation and State, SwiftUI Previews, Widgets and Controls, Swift Charts, and Apple Developer Documentation. Each accepted graph edge represents a reviewed planning dependency, not just a visual association.

Previews are treated as source-backed content because they preserve expected states for localization, Dynamic Type, dark mode, and Liquid Glass adaptation checks.""",
    "src-liquid-glass": """# Apple Liquid Glass Technology Overview

Liquid Glass is represented as a design and migration concept. The demo treats it as a system visual material that should be adopted through standard controls first, then evaluated in custom components only where the product need is explicit.

The content links Liquid Glass to SwiftUI App Structure, UIKit Interoperability, Human Interface Guidance, Icon Composer and Asset Catalogs, SwiftUI Previews, and the iOS 26 Migration Plan. Those relationships let reviewers see where design guidance influences architecture and test planning.

The migration plan emphasizes building with the latest SDK, auditing visual changes, testing controls and navigation, and staging compatibility work behind version checks where needed.""",
    "src-app-intents": """# Apple App Intents Documentation

App Intents expose typed app actions and entities to Shortcuts, Spotlight, widgets, controls, and Siri experiences. In the demo graph, App Intents are connected to Navigation Architecture, Siri and Spotlight, Widgets and Controls, and Live Activities.

The source content explains why discoverable actions need durable domain modeling: intents should map to real app capabilities, reuse validated data boundaries, and support system surfaces without bypassing privacy and permission decisions.

The reviewed graph intentionally keeps App Intents linked to platform services rather than treating them as a standalone feature, because intent design affects navigation, widgets, search, and commerce flows.""",
    "src-swiftdata": """# Apple SwiftData Documentation

SwiftData Persistence captures model types, queries, migrations, preview stores, and storage lifecycle decisions for the native iOS demo. ModelContainer is tracked as its own term because it scopes schemas, stores, migrations, previews, and tests.

The source content links SwiftData to Observation and State, ModelContainer, SwiftUI Previews, Swift Testing and XCTest, and Swift Package Modularization. These relationships show that persistence design affects state ownership, module boundaries, migration tests, and fixture strategy.

Reviewed content emphasizes deterministic test stores, migration validation, undo behavior, and schema ownership as release gates for durable app data.""",
    "src-team-blueprint": """# Native iOS 26 Swift App Blueprint

The product is a native iOS 26 Swift app built with a SwiftUI-first architecture, focused UIKit interoperability, SwiftData persistence, URLSession networking, Swift Concurrency, App Intents, widgets, live status surfaces, privacy review, and App Store release operations.

Architecture decisions favor explicit domain modules, shared test fixtures, scoped platform boundaries, and a release workflow that connects signing, TestFlight rings, staged rollout criteria, release notes, privacy declarations, and rollback planning.

Engineering content includes Swift Language, Navigation Architecture, Accessibility and Localization, Observation and State, URLSession Networking, Swift Concurrency, Background Tasks, Privacy and Security Decisions, Swift Testing and XCTest, Instruments and MetricKit, Distribution Workflow, Architecture Decision Record, Swift Package Modularization, StoreKit, and App Store Connect.

The blueprint is the main source for cross-cutting relationships. It connects app architecture to privacy, testing, release operations, modularization, networking, background work, commerce, and accessibility so the demo behaves like a complete reviewed planning graph.""",
}


N = {
    "app": "node-ios26-native-app",
    "xcode": "node-xcode26-ios26-sdk",
    "swift": "node-swift-language",
    "swiftui": "node-swiftui-app-structure",
    "liquidGlass": "node-liquid-glass",
    "uikit": "node-uikit-interop",
    "navigation": "node-navigation",
    "accessibility": "node-accessibility",
    "observation": "node-observation-state",
    "swiftData": "node-swiftdata",
    "modelContainer": "node-modelcontainer",
    "networking": "node-networking-urlsession",
    "concurrency": "node-swift-concurrency",
    "appIntents": "node-app-intents",
    "siri": "node-siri-spotlight-apple-intelligence",
    "widgets": "node-widgets-controls",
    "liveActivities": "node-live-activities",
    "backgroundTasks": "node-background-tasks",
    "privacy": "node-privacy-security",
    "testing": "node-swift-testing-xctest",
    "previews": "node-previews",
    "instruments": "node-instruments",
    "appStore": "node-app-store-connect",
    "distribution": "node-distribution",
    "architecture": "node-architecture-decision",
    "modularization": "node-modularization",
    "icons": "node-icon-composer-assets",
    "hig": "node-human-interface-guidelines",
    "docs": "node-apple-developer-docs",
    "migration": "node-ios26-migration-plan",
    "charts": "node-swift-charts",
    "storekit": "node-storekit",
}


DEMO_NODES = [
    (N["app"], "Native iOS 26 Swift App", "concept", "The full product surface: app target, platform APIs, design system, data layer, automation, testing, and release operations.", "src-team-blueprint", "overview"),
    (N["xcode"], "Xcode 26 and iOS 26 SDK", "system", "The required toolchain and SDK surface for adopting iOS 26 platform APIs and validating against current simulators and devices.", "src-ios26-whats-new", "Xcode 26 beta and iOS 26 beta"),
    (N["swift"], "Swift Language", "term", "The primary implementation language for app logic, models, concurrency, macros, package modules, and tests.", "src-team-blueprint", "language foundation"),
    (N["swiftui"], "SwiftUI App Structure", "system", "Declarative app entry points, scenes, navigation containers, view composition, environment values, and platform-adaptive controls.", "src-swiftui-docs", "SwiftUI apps"),
    (N["liquidGlass"], "Liquid Glass", "concept", "The iOS 26 visual material and interaction treatment that standard SwiftUI and UIKit controls adopt through the system design.", "src-liquid-glass", "Adopting Liquid Glass"),
    (N["uikit"], "UIKit Interoperability", "system", "Native UIKit controllers, representables, hosting controllers, and escape hatches for features that need imperative view lifecycle control.", "src-swiftui-docs", "SwiftUI and UIKit interoperability"),
    (N["navigation"], "Navigation Architecture", "concept", "Route modeling, deep links, tab or split navigation, restoration, and testable navigation state.", "src-team-blueprint", "navigation"),
    (N["accessibility"], "Accessibility and Localization", "concept", "VoiceOver labels, Dynamic Type, contrast, reduce motion, localized strings, right-to-left layout, and inclusive input paths.", "src-team-blueprint", "accessibility"),
    (N["observation"], "Observation and State", "concept", "State ownership through value models, observable domain objects, view-local state, and dependency injection boundaries.", "src-team-blueprint", "state model"),
    (N["swiftData"], "SwiftData Persistence", "system", "Native model persistence for SwiftUI apps, including model types, queries, undo support, and storage lifecycle decisions.", "src-swiftdata", "SwiftData overview"),
    (N["modelContainer"], "ModelContainer", "term", "The configured SwiftData persistence container that scopes schemas, stores, migrations, previews, and tests.", "src-swiftdata", "model container"),
    (N["networking"], "URLSession Networking", "system", "Native HTTP transport, background transfers, caching, authentication, retries, and decoding boundaries.", "src-team-blueprint", "networking"),
    (N["concurrency"], "Swift Concurrency", "concept", "Async/await, actors, tasks, cancellation, main actor isolation, and structured concurrency for responsive app behavior.", "src-team-blueprint", "concurrency"),
    (N["appIntents"], "App Intents", "system", "Typed actions and entities that expose app capabilities to Shortcuts, Spotlight, widgets, controls, and Siri experiences.", "src-app-intents", "App Intents overview"),
    (N["siri"], "Siri, Spotlight, and Apple Intelligence", "concept", "System surfaces that can discover, suggest, and invoke app actions when App Intents and entities are modeled well.", "src-app-intents", "system experiences"),
    (N["widgets"], "Widgets and Controls", "system", "Glanceable surfaces and Control Center controls that reuse app data and intent-driven actions outside the main app.", "src-app-intents", "widgets and controls"),
    (N["liveActivities"], "Live Activities", "system", "Time-sensitive lock-screen and Dynamic Island experiences for ongoing tasks, status, and event progress.", "src-team-blueprint", "live status"),
    (N["backgroundTasks"], "Background Tasks", "system", "Deferred refresh, processing, uploads, and system-scheduled work that respect battery, privacy, and execution limits.", "src-team-blueprint", "background execution"),
    (N["privacy"], "Privacy and Security Decisions", "decision", "Data minimization, entitlement review, local processing, keychain use, permission prompts, and privacy nutrition labels.", "src-team-blueprint", "privacy review"),
    (N["testing"], "Swift Testing and XCTest", "system", "Unit, integration, UI, snapshot, performance, and migration tests that protect app behavior across SDK updates.", "src-team-blueprint", "test strategy"),
    (N["previews"], "SwiftUI Previews", "system", "Fast local fixtures for view states, Dynamic Type sizes, localization, dark mode, and Liquid Glass adaptation checks.", "src-swiftui-docs", "previews"),
    (N["instruments"], "Instruments and MetricKit", "system", "Profiling and diagnostics for launch time, hangs, memory, energy, networking, and field performance.", "src-team-blueprint", "performance"),
    (N["appStore"], "App Store Connect", "system", "Distribution, TestFlight, phased release, app metadata, privacy declarations, analytics, and review submission workflow.", "src-team-blueprint", "release"),
    (N["distribution"], "Distribution Workflow", "concept", "Signing, provisioning, CI archives, TestFlight rings, staged rollout, rollback criteria, and release notes.", "src-team-blueprint", "ship plan"),
    (N["architecture"], "Architecture Decision Record", "decision", "Choose SwiftUI-first native architecture with focused UIKit interop, explicit domain modules, and reviewable platform boundaries.", "src-team-blueprint", "ADR-001"),
    (N["modularization"], "Swift Package Modularization", "concept", "Separate app shell, feature modules, shared domain models, persistence, networking, design system, and test support packages.", "src-team-blueprint", "module map"),
    (N["icons"], "Icon Composer and Asset Catalogs", "document", "Icon, symbol, color, image, and preview assets that support iOS 26 app icon appearance and platform rendering.", "src-ios26-whats-new", "icon updates"),
    (N["hig"], "Human Interface Guidance", "document", "Design principles for hierarchy, consistency, platform adaptation, motion, touch targets, and Liquid Glass restraint.", "src-liquid-glass", "design principles"),
    (N["docs"], "Apple Developer Documentation", "document", "The canonical reference set for framework contracts, migration notes, sample code, tutorials, and SDK updates.", "src-swiftui-docs", "documentation index"),
    (N["migration"], "iOS 26 Migration Plan", "decision", "Build with the latest Xcode, audit visual changes, test controls and navigation, then stage SDK-specific fixes behind version checks when needed.", "src-liquid-glass", "existing app adoption"),
    (N["charts"], "Swift Charts", "system", "Native data visualization for dashboards, summaries, and in-app analytical views that can share SwiftUI data models.", "src-swiftui-docs", "Swift Charts resources"),
    (N["storekit"], "StoreKit", "system", "Native commerce, subscriptions, transaction verification, entitlement state, offer flows, and testable purchase experiences.", "src-team-blueprint", "commerce"),
]


DEMO_EDGES = [
    ("edge-app-xcode", N["app"], N["xcode"], "depends_on", 0.98, "src-ios26-whats-new", "toolchain"),
    ("edge-app-swift", N["app"], N["swift"], "depends_on", 0.98, "src-team-blueprint", "language"),
    ("edge-app-swiftui", N["app"], N["swiftui"], "depends_on", 0.96, "src-swiftui-docs", "app structure"),
    ("edge-app-architecture", N["app"], N["architecture"], "depends_on", 0.92, "src-team-blueprint", "architecture"),
    ("edge-app-privacy", N["app"], N["privacy"], "depends_on", 0.9, "src-team-blueprint", "privacy"),
    ("edge-xcode-migration", N["xcode"], N["migration"], "supports", 0.9, "src-liquid-glass", "build latest"),
    ("edge-docs-xcode", N["docs"], N["xcode"], "defines", 0.82, "src-ios26-whats-new", "SDK updates"),
    ("edge-docs-swiftui", N["docs"], N["swiftui"], "defines", 0.84, "src-swiftui-docs", "SwiftUI docs"),
    ("edge-docs-app-intents", N["docs"], N["appIntents"], "defines", 0.84, "src-app-intents", "App Intents docs"),
    ("edge-docs-swiftdata", N["docs"], N["swiftData"], "defines", 0.84, "src-swiftdata", "SwiftData docs"),
    ("edge-swiftui-liquid-glass", N["swiftui"], N["liquidGlass"], "supports", 0.92, "src-liquid-glass", "standard components"),
    ("edge-uikit-liquid-glass", N["uikit"], N["liquidGlass"], "supports", 0.86, "src-liquid-glass", "UIKit components"),
    ("edge-hig-liquid-glass", N["hig"], N["liquidGlass"], "defines", 0.9, "src-liquid-glass", "design principles"),
    ("edge-icons-liquid-glass", N["icons"], N["liquidGlass"], "relates_to", 0.78, "src-ios26-whats-new", "icon updates"),
    ("edge-migration-liquid-glass", N["migration"], N["liquidGlass"], "depends_on", 0.88, "src-liquid-glass", "adoption"),
    ("edge-swiftui-uikit", N["swiftui"], N["uikit"], "relates_to", 0.72, "src-swiftui-docs", "interop"),
    ("edge-swiftui-navigation", N["swiftui"], N["navigation"], "supports", 0.88, "src-team-blueprint", "navigation"),
    ("edge-navigation-app-intents", N["navigation"], N["appIntents"], "relates_to", 0.7, "src-app-intents", "open intents"),
    ("edge-swiftui-observation", N["swiftui"], N["observation"], "depends_on", 0.84, "src-team-blueprint", "state"),
    ("edge-observation-swiftdata", N["observation"], N["swiftData"], "relates_to", 0.76, "src-swiftdata", "model changes"),
    ("edge-swiftdata-modelcontainer", N["swiftData"], N["modelContainer"], "defines", 0.94, "src-swiftdata", "container"),
    ("edge-swiftdata-previews", N["swiftData"], N["previews"], "supports", 0.72, "src-swiftdata", "preview stores"),
    ("edge-networking-concurrency", N["networking"], N["concurrency"], "depends_on", 0.86, "src-team-blueprint", "async transport"),
    ("edge-swift-concurrency", N["swift"], N["concurrency"], "supports", 0.9, "src-team-blueprint", "async await"),
    ("edge-background-networking", N["backgroundTasks"], N["networking"], "depends_on", 0.78, "src-team-blueprint", "background transfer"),
    ("edge-background-privacy", N["backgroundTasks"], N["privacy"], "depends_on", 0.74, "src-team-blueprint", "system limits"),
    ("edge-app-intents-siri", N["appIntents"], N["siri"], "supports", 0.96, "src-app-intents", "Siri and Spotlight"),
    ("edge-app-intents-widgets", N["appIntents"], N["widgets"], "supports", 0.88, "src-app-intents", "configuration intents"),
    ("edge-app-intents-live-activities", N["appIntents"], N["liveActivities"], "relates_to", 0.76, "src-app-intents", "live activity intents"),
    ("edge-widgets-swiftui", N["widgets"], N["swiftui"], "depends_on", 0.78, "src-swiftui-docs", "shared views"),
    ("edge-live-activities-background", N["liveActivities"], N["backgroundTasks"], "relates_to", 0.7, "src-team-blueprint", "ongoing status"),
    ("edge-testing-swift", N["testing"], N["swift"], "depends_on", 0.82, "src-team-blueprint", "test language"),
    ("edge-testing-swiftdata", N["testing"], N["swiftData"], "supports", 0.78, "src-swiftdata", "migration tests"),
    ("edge-testing-navigation", N["testing"], N["navigation"], "supports", 0.74, "src-team-blueprint", "route tests"),
    ("edge-testing-accessibility", N["testing"], N["accessibility"], "supports", 0.78, "src-team-blueprint", "inclusive QA"),
    ("edge-previews-accessibility", N["previews"], N["accessibility"], "supports", 0.74, "src-swiftui-docs", "variant previews"),
    ("edge-previews-liquid-glass", N["previews"], N["liquidGlass"], "supports", 0.82, "src-liquid-glass", "visual checks"),
    ("edge-instruments-testing", N["instruments"], N["testing"], "supports", 0.8, "src-team-blueprint", "performance tests"),
    ("edge-instruments-concurrency", N["instruments"], N["concurrency"], "relates_to", 0.7, "src-team-blueprint", "hang diagnostics"),
    ("edge-appstore-distribution", N["appStore"], N["distribution"], "supports", 0.92, "src-team-blueprint", "TestFlight"),
    ("edge-distribution-privacy", N["distribution"], N["privacy"], "depends_on", 0.86, "src-team-blueprint", "review declarations"),
    ("edge-distribution-testing", N["distribution"], N["testing"], "depends_on", 0.82, "src-team-blueprint", "release gates"),
    ("edge-storekit-distribution", N["storekit"], N["distribution"], "depends_on", 0.78, "src-team-blueprint", "commerce release"),
    ("edge-storekit-testing", N["storekit"], N["testing"], "depends_on", 0.8, "src-team-blueprint", "purchase tests"),
    ("edge-charts-swiftui", N["charts"], N["swiftui"], "depends_on", 0.82, "src-swiftui-docs", "Swift Charts"),
    ("edge-charts-accessibility", N["charts"], N["accessibility"], "depends_on", 0.72, "src-team-blueprint", "chart descriptions"),
    ("edge-modularization-architecture", N["modularization"], N["architecture"], "supports", 0.9, "src-team-blueprint", "module decision"),
    ("edge-modularization-testing", N["modularization"], N["testing"], "supports", 0.78, "src-team-blueprint", "testability"),
    ("edge-modularization-networking", N["modularization"], N["networking"], "supports", 0.72, "src-team-blueprint", "network module"),
    ("edge-modularization-swiftdata", N["modularization"], N["swiftData"], "supports", 0.72, "src-team-blueprint", "persistence module"),
    ("edge-architecture-migration", N["architecture"], N["migration"], "supports", 0.84, "src-team-blueprint", "versioned adoption"),
    ("edge-architecture-privacy", N["architecture"], N["privacy"], "depends_on", 0.84, "src-team-blueprint", "data boundaries"),
    ("edge-accessibility-hig", N["accessibility"], N["hig"], "depends_on", 0.82, "src-team-blueprint", "inclusive design"),
    ("edge-appstore-icons", N["appStore"], N["icons"], "depends_on", 0.74, "src-ios26-whats-new", "app metadata"),
]


def seed_demo_graph(conn, db, dump_json) -> None:
    existing = conn.execute(select(db.graph_projects.c.id).where(db.graph_projects.c.id == DEMO_PROJECT_ID)).first()
    if existing is not None:
        _ensure_demo_source_chunks(conn, db, dump_json)
        return

    conn.execute(
        insert(db.graph_projects).values(
            id=DEMO_PROJECT_ID,
            name="Native iOS 26 Swift App Graph",
            description="Live demo graph for planning, building, testing, and shipping native iOS apps with Swift, SwiftUI, UIKit, and Apple platform services.",
            created_at=DEMO_TIMESTAMP,
            updated_at=DEMO_TIMESTAMP,
        )
    )

    source_rows = [
        {
            "id": source_id,
            "project_id": DEMO_PROJECT_ID,
            "kind": kind,
            "title": title,
            "uri": uri,
            "object_key": f"demo/ios26/{source_id}",
            "checksum": _checksum(f"{title}\n{uri}"),
            "created_at": DEMO_TIMESTAMP,
            "updated_at": DEMO_TIMESTAMP,
        }
        for source_id, title, kind, uri in DEMO_SOURCES
    ]
    run_rows = [
        {
            "id": _run_id(source_id),
            "project_id": DEMO_PROJECT_ID,
            "source_id": source_id,
            "status": "committed",
            "stage": "commit",
            "trace_id": _trace_id(source_id),
            "started_at": DEMO_TIMESTAMP,
            "finished_at": DEMO_TIMESTAMP,
            "error_code": None,
        }
        for source_id, *_ in DEMO_SOURCES
    ]
    conn.execute(insert(db.sources), source_rows)
    conn.execute(insert(db.ingestion_runs), run_rows)
    chunk_rows = []
    for source_id, title, *_ in DEMO_SOURCES:
        chunk_rows.extend(_source_chunk_rows(db, source_id, title, DEMO_SOURCE_CONTENT[source_id], dump_json))
    conn.execute(insert(db.source_chunks), chunk_rows)

    node_rows = []
    edge_rows = []
    proposal_rows = []
    embedding_rows = []
    review_rows = []

    for node_id, label, kind, summary, source_id, locator in DEMO_NODES:
        provenance = [_provenance(source_id, locator)]
        metadata = {"extractionLenses": _node_lenses(kind, label)}
        node_rows.append(
            {
                "id": node_id,
                "project_id": DEMO_PROJECT_ID,
                "label": label,
                "kind": kind,
                "summary": summary,
                "topic_ids_json": dump_json([]),
                "metadata_json": dump_json(metadata),
                "provenance_json": dump_json(provenance),
                "created_at": DEMO_TIMESTAMP,
                "updated_at": DEMO_TIMESTAMP,
            }
        )
        proposed_value = {"id": node_id, "label": label, "kind": kind, "summary": summary, "topicIds": [], "metadata": metadata}
        _append_reviewed_proposal(
            db,
            dump_json,
            proposal_rows,
            embedding_rows,
            review_rows,
            proposal_id=_stable_id("proposal-demo-node", node_id),
            source_id=source_id,
            kind="content_node",
            proposed_value=proposed_value,
            provenance=provenance,
            content_node_id=node_id,
            confidence=0.92,
        )

    labels_by_node_id = {node_id: label for node_id, label, *_ in DEMO_NODES}
    for edge_id, source_node_id, target_node_id, relation, weight, source_id, locator in DEMO_EDGES:
        provenance = [_provenance(source_id, locator)]
        metadata = {"extractionLenses": _edge_lenses(relation)}
        edge_rows.append(
            {
                "id": edge_id,
                "project_id": DEMO_PROJECT_ID,
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "relation": relation,
                "weight": weight,
                "metadata_json": dump_json(metadata),
                "provenance_json": dump_json(provenance),
                "created_at": DEMO_TIMESTAMP,
                "updated_at": DEMO_TIMESTAMP,
            }
        )
        proposed_value = {
            "id": edge_id,
            "sourceNodeId": source_node_id,
            "targetNodeId": target_node_id,
            "sourceLabel": labels_by_node_id[source_node_id],
            "targetLabel": labels_by_node_id[target_node_id],
            "relation": relation,
            "weight": weight,
            "metadata": metadata,
        }
        _append_reviewed_proposal(
            db,
            dump_json,
            proposal_rows,
            embedding_rows,
            review_rows,
            proposal_id=_stable_id("proposal-demo-edge", edge_id),
            source_id=source_id,
            kind="semantic_edge",
            proposed_value=proposed_value,
            provenance=provenance,
            content_node_id=None,
            confidence=weight,
        )

    conn.execute(insert(db.content_nodes), node_rows)
    conn.execute(insert(db.semantic_edges), edge_rows)
    conn.execute(insert(db.extraction_proposals), proposal_rows)
    conn.execute(insert(db.content_embeddings), embedding_rows)
    conn.execute(insert(db.review_decisions), review_rows)


def _ensure_demo_source_chunks(conn, db, dump_json) -> None:
    existing_chunk = conn.execute(
        select(db.source_chunks.c.id).where(db.source_chunks.c.project_id == DEMO_PROJECT_ID)
    ).first()
    if existing_chunk is not None:
        return
    chunk_rows = []
    for source_id, title, *_ in DEMO_SOURCES:
        source_exists = conn.execute(select(db.sources.c.id).where(db.sources.c.id == source_id)).first()
        if source_exists is not None:
            chunk_rows.extend(_source_chunk_rows(db, source_id, title, DEMO_SOURCE_CONTENT[source_id], dump_json))
    if chunk_rows:
        conn.execute(insert(db.source_chunks), chunk_rows)


def _append_reviewed_proposal(
    db,
    dump_json,
    proposal_rows: list[dict],
    embedding_rows: list[dict],
    review_rows: list[dict],
    *,
    proposal_id: str,
    source_id: str,
    kind: str,
    proposed_value: dict,
    provenance: list[dict],
    content_node_id: str | None,
    confidence: float,
) -> None:
    proposal_rows.append(
        {
            "id": proposal_id,
            "project_id": DEMO_PROJECT_ID,
            "ingestion_run_id": _run_id(source_id),
            "kind": kind,
            "status": "accepted",
            "proposed_value_json": dump_json(proposed_value),
            "confidence": confidence,
            "provenance_json": dump_json(provenance),
            "created_at": DEMO_TIMESTAMP,
        }
    )
    embedding_rows.append(
        {
            "id": f"embedding-{proposal_id}",
            "project_id": DEMO_PROJECT_ID,
            "proposal_id": proposal_id,
            "content_node_id": content_node_id,
            "embedding_model": DEMO_EMBEDDING_MODEL,
            "vector_json": dump_json(_vector(proposal_id)),
            "created_at": DEMO_TIMESTAMP,
        }
    )
    review_rows.append(
        {
            "id": f"review-{proposal_id}",
            "project_id": DEMO_PROJECT_ID,
            "proposal_id": proposal_id,
            "reviewer_id": "demo-reviewer",
            "decision": "accept",
            "edited_value_json": None,
            "rationale": "Accepted as part of the fully linked live demo graph.",
            "decided_at": DEMO_TIMESTAMP,
        }
    )


def _source_chunk_rows(db, source_id: str, title: str, content: str, dump_json) -> list[dict]:
    rows = []
    blocks = [block.strip() for block in content.strip().split("\n\n") if block.strip()]
    for ordinal, block in enumerate(blocks):
        block_type = "heading" if block.startswith("#") else "paragraph"
        text = block.lstrip("# ").strip() if block_type == "heading" else block
        heading_path = [title] if block_type != "heading" else [text]
        rows.append(
            {
                "id": f"chunk-demo-{source_id}-{ordinal}",
                "project_id": DEMO_PROJECT_ID,
                "source_id": source_id,
                "parent_chunk_id": None,
                "heading_path_json": dump_json(heading_path),
                "block_type": block_type,
                "ordinal": ordinal,
                "text": text,
                "links_json": dump_json(_links(text)),
                "mentions_json": dump_json(_mentions(text)),
                "checksum": _checksum(f"{source_id}:{ordinal}:{text}"),
                "locator": f"demo://ios26/{source_id}#block-{ordinal + 1}",
                "created_at": DEMO_TIMESTAMP,
            }
        )
    return rows


def _provenance(source_id: str, locator: str) -> dict:
    return {
        "sourceId": source_id,
        "sourceUri": next((source[3] for source in DEMO_SOURCES if source[0] == source_id), None),
        "locator": locator,
        "extractedBy": "import",
        "actorId": DEMO_ACTOR_ID,
        "ingestionRunId": _run_id(source_id),
        "observedAt": DEMO_TIMESTAMP.isoformat(),
        "traceId": _trace_id(source_id),
    }


def _run_id(source_id: str) -> str:
    return f"run-demo-{source_id.removeprefix('src-')}"


def _trace_id(source_id: str) -> str:
    return f"trace-demo-{source_id.removeprefix('src-')}"


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:14]}"


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _links(text: str) -> list[str]:
    return [word.rstrip(".,)") for word in text.split() if word.startswith(("http://", "https://"))]


def _mentions(text: str) -> list[str]:
    names = []
    for candidate in [
        "SwiftUI",
        "UIKit",
        "SwiftData",
        "ModelContainer",
        "App Intents",
        "Liquid Glass",
        "Xcode",
        "App Store Connect",
        "TestFlight",
        "StoreKit",
    ]:
        if candidate in text:
            names.append(candidate)
    return names


def _node_lenses(kind: str, label: str) -> list[str]:
    lenses = []
    if kind in {"concept", "term", "document", "source", "dataset"}:
        lenses.append("research")
    if kind in {"system", "component", "service", "api", "repository", "module", "package", "file", "symbol"}:
        lenses.append("engineering")
    if kind in {"decision", "workflow", "process", "policy", "vendor", "incident", "project", "owner", "review_cycle", "organization", "team"}:
        lenses.append("ops")
    if any(word in label.lower() for word in ["release", "app store", "privacy", "distribution", "migration"]):
        if "ops" not in lenses:
            lenses.append("ops")
    return lenses or ["research"]


def _edge_lenses(relation: str) -> list[str]:
    lenses = []
    if relation in {"supports", "contradicts", "causes", "mentions", "defines", "relates_to", "references"}:
        lenses.append("research")
    if relation in {"depends_on", "defines", "imports", "implements", "contains", "references"}:
        lenses.append("engineering")
    if relation in {"owned_by", "has_review_cycle", "governs", "supports", "depends_on"}:
        lenses.append("ops")
    return lenses or ["research"]


def _vector(value: str) -> list[float]:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return [round(byte / 255, 6) for byte in digest[:16]]


def seed_development_demo(repository) -> None:
    from graphview_api import db
    from graphview_api.repository import dump_json

    with repository.engine.begin() as connection:
        seed_demo_graph(connection, db, dump_json)
