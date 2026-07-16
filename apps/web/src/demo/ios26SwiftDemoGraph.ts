import type {
  ContentNode,
  ContentNodeId,
  ExtractionLensDescriptor,
  GraphLensDescriptor,
  GraphProject,
  GraphProjectId,
  Provenance,
  SemanticEdge,
  SemanticEdgeId,
  Source,
  SourceId
} from "@graphview/shared-types";

const timestamp = "2026-06-05T00:00:00.000Z";
const projectId = "project-ios26-swift-demo" as GraphProjectId;

export const demoProject: GraphProject = {
  id: projectId,
  name: "Native iOS 26 Swift App Graph",
  description:
    "Demo knowledge graph for planning, building, testing, and shipping native iOS 26 apps with Swift, SwiftUI, UIKit, and Apple platform services.",
  createdAt: timestamp,
  updatedAt: timestamp
};

export const demoSources: Source[] = [
  source("src-ios26-whats-new", "Apple iOS 26 Whats New", "url", "https://developer.apple.com/ios/whats-new/"),
  source("src-swiftui-docs", "Apple SwiftUI Documentation", "url", "https://developer.apple.com/documentation/swiftui/"),
  source(
    "src-liquid-glass",
    "Apple Liquid Glass Technology Overview",
    "url",
    "https://developer.apple.com/documentation/technologyoverviews/liquid-glass"
  ),
  source("src-app-intents", "Apple App Intents Documentation", "url", "https://developer.apple.com/documentation/appintents"),
  source("src-swiftdata", "Apple SwiftData Documentation", "url", "https://developer.apple.com/documentation/swiftdata"),
  source("src-team-blueprint", "Native iOS 26 Swift App Blueprint", "markdown", "local://demo/ios26-swift-blueprint.md")
];

const sourceIds = {
  whatsNew: demoSources[0].id,
  swiftui: demoSources[1].id,
  liquidGlass: demoSources[2].id,
  appIntents: demoSources[3].id,
  swiftData: demoSources[4].id,
  blueprint: demoSources[5].id
};

export const demoExtractionLenses: ExtractionLensDescriptor[] = [
  {
    id: "research",
    label: "Research",
    summary: "Product, architecture, design, and release planning concepts for a native iOS 26 app.",
    defaultProposalLimit: 6,
    sourceKinds: ["text", "markdown", "url", "pdf", "repository", "ops-document"],
    primaryNodeKinds: ["concept", "document", "decision", "term"],
    provenanceFields: ["source", "locator", "reviewer", "trace"]
  },
  {
    id: "engineering",
    label: "Engineering",
    summary: "Swift modules, app targets, framework dependencies, and test surfaces.",
    defaultProposalLimit: 8,
    sourceKinds: ["repository", "markdown", "text"],
    primaryNodeKinds: ["system", "repository", "file", "symbol", "package"],
    provenanceFields: ["repository", "path", "symbol", "dependency", "issue_or_pr"]
  },
  {
    id: "ops",
    label: "Release Ops",
    summary: "Privacy, signing, review, telemetry, incident, and operational readiness documents.",
    defaultProposalLimit: 8,
    sourceKinds: ["ops-document", "markdown", "text"],
    primaryNodeKinds: ["document", "decision", "organization", "process", "policy", "owner"],
    provenanceFields: ["document", "owner", "review_cycle", "effective_date", "incident_or_project"]
  }
];

export const demoGraphLenses: GraphLensDescriptor[] = [
  { id: "all", label: "All", summary: "Full reviewed graph.", activeByDefault: true },
  { id: "research", label: "Research", summary: "Concepts, documents, terms, and provenance.", activeByDefault: false },
  { id: "engineering", label: "Engineering", summary: "Systems, modules, dependencies, and architecture hotspots.", activeByDefault: false },
  { id: "ops", label: "Ops", summary: "Release operations, ownership, policy, and review freshness.", activeByDefault: false }
];

const n = {
  app: "node-ios26-native-app",
  xcode: "node-xcode26-ios26-sdk",
  swift: "node-swift-language",
  swiftui: "node-swiftui-app-structure",
  liquidGlass: "node-liquid-glass",
  uikit: "node-uikit-interop",
  navigation: "node-navigation",
  accessibility: "node-accessibility",
  observation: "node-observation-state",
  swiftData: "node-swiftdata",
  modelContainer: "node-modelcontainer",
  networking: "node-networking-urlsession",
  concurrency: "node-swift-concurrency",
  appIntents: "node-app-intents",
  siri: "node-siri-spotlight-apple-intelligence",
  widgets: "node-widgets-controls",
  liveActivities: "node-live-activities",
  backgroundTasks: "node-background-tasks",
  privacy: "node-privacy-security",
  testing: "node-swift-testing-xctest",
  previews: "node-previews",
  instruments: "node-instruments",
  appStore: "node-app-store-connect",
  distribution: "node-distribution",
  architecture: "node-architecture-decision",
  modularization: "node-modularization",
  icons: "node-icon-composer-assets",
  hig: "node-human-interface-guidelines",
  docs: "node-apple-developer-docs",
  migration: "node-ios26-migration-plan",
  charts: "node-swift-charts",
  storekit: "node-storekit"
} as const;

export const demoNodes: ContentNode[] = [
  node(n.app, "Native iOS 26 Swift App", "concept", "The full product surface: app target, platform APIs, design system, data layer, automation, testing, and release operations.", sourceIds.blueprint, "overview"),
  node(n.xcode, "Xcode 26 and iOS 26 SDK", "system", "The required toolchain and SDK surface for adopting iOS 26 platform APIs and validating against current simulators and devices.", sourceIds.whatsNew, "Xcode 26 beta and iOS 26 beta"),
  node(n.swift, "Swift Language", "term", "The primary implementation language for app logic, models, concurrency, macros, package modules, and tests.", sourceIds.blueprint, "language foundation"),
  node(n.swiftui, "SwiftUI App Structure", "system", "Declarative app entry points, scenes, navigation containers, view composition, environment values, and platform-adaptive controls.", sourceIds.swiftui, "SwiftUI apps"),
  node(n.liquidGlass, "Liquid Glass", "concept", "The iOS 26 visual material and interaction treatment that standard SwiftUI and UIKit controls adopt through the system design.", sourceIds.liquidGlass, "Adopting Liquid Glass"),
  node(n.uikit, "UIKit Interoperability", "system", "Native UIKit controllers, representables, hosting controllers, and escape hatches for features that need imperative view lifecycle control.", sourceIds.swiftui, "SwiftUI and UIKit interoperability"),
  node(n.navigation, "Navigation Architecture", "concept", "Route modeling, deep links, tab or split navigation, restoration, and testable navigation state.", sourceIds.blueprint, "navigation"),
  node(n.accessibility, "Accessibility and Localization", "concept", "VoiceOver labels, Dynamic Type, contrast, reduce motion, localized strings, right-to-left layout, and inclusive input paths.", sourceIds.blueprint, "accessibility"),
  node(n.observation, "Observation and State", "concept", "State ownership through value models, observable domain objects, view-local state, and dependency injection boundaries.", sourceIds.blueprint, "state model"),
  node(n.swiftData, "SwiftData Persistence", "system", "Native model persistence for SwiftUI apps, including model types, queries, undo support, and storage lifecycle decisions.", sourceIds.swiftData, "SwiftData overview"),
  node(n.modelContainer, "ModelContainer", "term", "The configured SwiftData persistence container that scopes schemas, stores, migrations, previews, and tests.", sourceIds.swiftData, "model container"),
  node(n.networking, "URLSession Networking", "system", "Native HTTP transport, background transfers, caching, authentication, retries, and decoding boundaries.", sourceIds.blueprint, "networking"),
  node(n.concurrency, "Swift Concurrency", "concept", "Async/await, actors, tasks, cancellation, main actor isolation, and structured concurrency for responsive app behavior.", sourceIds.blueprint, "concurrency"),
  node(n.appIntents, "App Intents", "system", "Typed actions and entities that expose app capabilities to Shortcuts, Spotlight, widgets, controls, and Siri experiences.", sourceIds.appIntents, "App Intents overview"),
  node(n.siri, "Siri, Spotlight, and Apple Intelligence", "concept", "System surfaces that can discover, suggest, and invoke app actions when App Intents and entities are modeled well.", sourceIds.appIntents, "system experiences"),
  node(n.widgets, "Widgets and Controls", "system", "Glanceable surfaces and Control Center controls that reuse app data and intent-driven actions outside the main app.", sourceIds.appIntents, "widgets and controls"),
  node(n.liveActivities, "Live Activities", "system", "Time-sensitive lock-screen and Dynamic Island experiences for ongoing tasks, status, and event progress.", sourceIds.blueprint, "live status"),
  node(n.backgroundTasks, "Background Tasks", "system", "Deferred refresh, processing, uploads, and system-scheduled work that respect battery, privacy, and execution limits.", sourceIds.blueprint, "background execution"),
  node(n.privacy, "Privacy and Security Decisions", "decision", "Data minimization, entitlement review, local processing, keychain use, permission prompts, and privacy nutrition labels.", sourceIds.blueprint, "privacy review"),
  node(n.testing, "Swift Testing and XCTest", "system", "Unit, integration, UI, snapshot, performance, and migration tests that protect app behavior across SDK updates.", sourceIds.blueprint, "test strategy"),
  node(n.previews, "SwiftUI Previews", "system", "Fast local fixtures for view states, Dynamic Type sizes, localization, dark mode, and Liquid Glass adaptation checks.", sourceIds.swiftui, "previews"),
  node(n.instruments, "Instruments and MetricKit", "system", "Profiling and diagnostics for launch time, hangs, memory, energy, networking, and field performance.", sourceIds.blueprint, "performance"),
  node(n.appStore, "App Store Connect", "system", "Distribution, TestFlight, phased release, app metadata, privacy declarations, analytics, and review submission workflow.", sourceIds.blueprint, "release"),
  node(n.distribution, "Distribution Workflow", "concept", "Signing, provisioning, CI archives, TestFlight rings, staged rollout, rollback criteria, and release notes.", sourceIds.blueprint, "ship plan"),
  node(n.architecture, "Architecture Decision Record", "decision", "Choose SwiftUI-first native architecture with focused UIKit interop, explicit domain modules, and reviewable platform boundaries.", sourceIds.blueprint, "ADR-001"),
  node(n.modularization, "Swift Package Modularization", "concept", "Separate app shell, feature modules, shared domain models, persistence, networking, design system, and test support packages.", sourceIds.blueprint, "module map"),
  node(n.icons, "Icon Composer and Asset Catalogs", "document", "Icon, symbol, color, image, and preview assets that support iOS 26 app icon appearance and platform rendering.", sourceIds.whatsNew, "icon updates"),
  node(n.hig, "Human Interface Guidance", "document", "Design principles for hierarchy, consistency, platform adaptation, motion, touch targets, and Liquid Glass restraint.", sourceIds.liquidGlass, "design principles"),
  node(n.docs, "Apple Developer Documentation", "document", "The canonical reference set for framework contracts, migration notes, sample code, tutorials, and SDK updates.", sourceIds.swiftui, "documentation index"),
  node(n.migration, "iOS 26 Migration Plan", "decision", "Build with the latest Xcode, audit visual changes, test controls and navigation, then stage SDK-specific fixes behind version checks when needed.", sourceIds.liquidGlass, "existing app adoption"),
  node(n.charts, "Swift Charts", "system", "Native data visualization for dashboards, summaries, and in-app analytical views that can share SwiftUI data models.", sourceIds.swiftui, "Swift Charts resources"),
  node(n.storekit, "StoreKit", "system", "Native commerce, subscriptions, transaction verification, entitlement state, offer flows, and testable purchase experiences.", sourceIds.blueprint, "commerce")
];

export const demoEdges: SemanticEdge[] = [
  edge("edge-app-xcode", n.app, n.xcode, "depends_on", 0.98, sourceIds.whatsNew, "toolchain"),
  edge("edge-app-swift", n.app, n.swift, "depends_on", 0.98, sourceIds.blueprint, "language"),
  edge("edge-app-swiftui", n.app, n.swiftui, "depends_on", 0.96, sourceIds.swiftui, "app structure"),
  edge("edge-app-architecture", n.app, n.architecture, "depends_on", 0.92, sourceIds.blueprint, "architecture"),
  edge("edge-app-privacy", n.app, n.privacy, "depends_on", 0.9, sourceIds.blueprint, "privacy"),
  edge("edge-xcode-migration", n.xcode, n.migration, "supports", 0.9, sourceIds.liquidGlass, "build latest"),
  edge("edge-docs-xcode", n.docs, n.xcode, "defines", 0.82, sourceIds.whatsNew, "SDK updates"),
  edge("edge-docs-swiftui", n.docs, n.swiftui, "defines", 0.84, sourceIds.swiftui, "SwiftUI docs"),
  edge("edge-docs-app-intents", n.docs, n.appIntents, "defines", 0.84, sourceIds.appIntents, "App Intents docs"),
  edge("edge-docs-swiftdata", n.docs, n.swiftData, "defines", 0.84, sourceIds.swiftData, "SwiftData docs"),
  edge("edge-swiftui-liquid-glass", n.swiftui, n.liquidGlass, "supports", 0.92, sourceIds.liquidGlass, "standard components"),
  edge("edge-uikit-liquid-glass", n.uikit, n.liquidGlass, "supports", 0.86, sourceIds.liquidGlass, "UIKit components"),
  edge("edge-hig-liquid-glass", n.hig, n.liquidGlass, "defines", 0.9, sourceIds.liquidGlass, "design principles"),
  edge("edge-icons-liquid-glass", n.icons, n.liquidGlass, "relates_to", 0.78, sourceIds.whatsNew, "icon updates"),
  edge("edge-migration-liquid-glass", n.migration, n.liquidGlass, "depends_on", 0.88, sourceIds.liquidGlass, "adoption"),
  edge("edge-swiftui-uikit", n.swiftui, n.uikit, "relates_to", 0.72, sourceIds.swiftui, "interop"),
  edge("edge-swiftui-navigation", n.swiftui, n.navigation, "supports", 0.88, sourceIds.blueprint, "navigation"),
  edge("edge-navigation-app-intents", n.navigation, n.appIntents, "relates_to", 0.7, sourceIds.appIntents, "open intents"),
  edge("edge-swiftui-observation", n.swiftui, n.observation, "depends_on", 0.84, sourceIds.blueprint, "state"),
  edge("edge-observation-swiftdata", n.observation, n.swiftData, "relates_to", 0.76, sourceIds.swiftData, "model changes"),
  edge("edge-swiftdata-modelcontainer", n.swiftData, n.modelContainer, "defines", 0.94, sourceIds.swiftData, "container"),
  edge("edge-swiftdata-previews", n.swiftData, n.previews, "supports", 0.72, sourceIds.swiftData, "preview stores"),
  edge("edge-networking-concurrency", n.networking, n.concurrency, "depends_on", 0.86, sourceIds.blueprint, "async transport"),
  edge("edge-swift-concurrency", n.swift, n.concurrency, "supports", 0.9, sourceIds.blueprint, "async await"),
  edge("edge-background-networking", n.backgroundTasks, n.networking, "depends_on", 0.78, sourceIds.blueprint, "background transfer"),
  edge("edge-background-privacy", n.backgroundTasks, n.privacy, "depends_on", 0.74, sourceIds.blueprint, "system limits"),
  edge("edge-app-intents-siri", n.appIntents, n.siri, "supports", 0.96, sourceIds.appIntents, "Siri and Spotlight"),
  edge("edge-app-intents-widgets", n.appIntents, n.widgets, "supports", 0.88, sourceIds.appIntents, "configuration intents"),
  edge("edge-app-intents-live-activities", n.appIntents, n.liveActivities, "relates_to", 0.76, sourceIds.appIntents, "live activity intents"),
  edge("edge-widgets-swiftui", n.widgets, n.swiftui, "depends_on", 0.78, sourceIds.swiftui, "shared views"),
  edge("edge-live-activities-background", n.liveActivities, n.backgroundTasks, "relates_to", 0.7, sourceIds.blueprint, "ongoing status"),
  edge("edge-testing-swift", n.testing, n.swift, "depends_on", 0.82, sourceIds.blueprint, "test language"),
  edge("edge-testing-swiftdata", n.testing, n.swiftData, "supports", 0.78, sourceIds.swiftData, "migration tests"),
  edge("edge-testing-navigation", n.testing, n.navigation, "supports", 0.74, sourceIds.blueprint, "route tests"),
  edge("edge-testing-accessibility", n.testing, n.accessibility, "supports", 0.78, sourceIds.blueprint, "inclusive QA"),
  edge("edge-previews-accessibility", n.previews, n.accessibility, "supports", 0.74, sourceIds.swiftui, "variant previews"),
  edge("edge-previews-liquid-glass", n.previews, n.liquidGlass, "supports", 0.82, sourceIds.liquidGlass, "visual checks"),
  edge("edge-instruments-testing", n.instruments, n.testing, "supports", 0.8, sourceIds.blueprint, "performance tests"),
  edge("edge-instruments-concurrency", n.instruments, n.concurrency, "relates_to", 0.7, sourceIds.blueprint, "hang diagnostics"),
  edge("edge-appstore-distribution", n.appStore, n.distribution, "supports", 0.92, sourceIds.blueprint, "TestFlight"),
  edge("edge-distribution-privacy", n.distribution, n.privacy, "depends_on", 0.86, sourceIds.blueprint, "review declarations"),
  edge("edge-distribution-testing", n.distribution, n.testing, "depends_on", 0.82, sourceIds.blueprint, "release gates"),
  edge("edge-storekit-distribution", n.storekit, n.distribution, "depends_on", 0.78, sourceIds.blueprint, "commerce release"),
  edge("edge-storekit-testing", n.storekit, n.testing, "depends_on", 0.8, sourceIds.blueprint, "purchase tests"),
  edge("edge-charts-swiftui", n.charts, n.swiftui, "depends_on", 0.82, sourceIds.swiftui, "Swift Charts"),
  edge("edge-charts-accessibility", n.charts, n.accessibility, "depends_on", 0.72, sourceIds.blueprint, "chart descriptions"),
  edge("edge-modularization-architecture", n.modularization, n.architecture, "supports", 0.9, sourceIds.blueprint, "module decision"),
  edge("edge-modularization-testing", n.modularization, n.testing, "supports", 0.78, sourceIds.blueprint, "testability"),
  edge("edge-modularization-networking", n.modularization, n.networking, "supports", 0.72, sourceIds.blueprint, "network module"),
  edge("edge-modularization-swiftdata", n.modularization, n.swiftData, "supports", 0.72, sourceIds.blueprint, "persistence module"),
  edge("edge-architecture-migration", n.architecture, n.migration, "supports", 0.84, sourceIds.blueprint, "versioned adoption"),
  edge("edge-architecture-privacy", n.architecture, n.privacy, "depends_on", 0.84, sourceIds.blueprint, "data boundaries"),
  edge("edge-accessibility-hig", n.accessibility, n.hig, "depends_on", 0.82, sourceIds.blueprint, "inclusive design"),
  edge("edge-appstore-icons", n.appStore, n.icons, "depends_on", 0.74, sourceIds.whatsNew, "app metadata")
];

export const demoGraph = {
  project: demoProject,
  nodes: demoNodes,
  edges: demoEdges
};

export interface DemoProposal {
  id: string;
  kind: "content_node" | "semantic_edge";
  status: "pending_review" | "accepted" | "rejected" | "edited" | "deferred";
  proposed_value: {
    label?: string;
    kind?: string;
    summary?: string;
    relation?: string;
    id?: string;
    sourceNodeId?: string;
    targetNodeId?: string;
    sourceLabel?: string;
    targetLabel?: string;
    weight?: number;
  };
}

export const demoProposals: DemoProposal[] = [
  {
    id: "proposal-liquid-glass-adoption",
    kind: "content_node",
    status: "accepted",
    proposed_value: {
      id: n.liquidGlass,
      label: "Liquid Glass",
      kind: "concept",
      summary: "Adopt the system visual material through standard controls first, then evaluate custom elements."
    }
  },
  {
    id: "proposal-app-intents-storekit-edge",
    kind: "semantic_edge",
    status: "pending_review",
    proposed_value: {
      id: "edge-proposed-storekit-app-intents",
      sourceNodeId: n.storekit,
      targetNodeId: n.appIntents,
      sourceLabel: "StoreKit",
      targetLabel: "App Intents",
      relation: "relates_to",
      weight: 0.62
    }
  },
  {
    id: "proposal-navigation-tests",
    kind: "semantic_edge",
    status: "accepted",
    proposed_value: {
      id: "edge-testing-navigation",
      sourceNodeId: n.testing,
      targetNodeId: n.navigation,
      relation: "supports",
      weight: 0.74
    }
  }
];

export const demoReviewDashboard = {
  proposal_count: demoProposals.length,
  pending_count: 1,
  ready_count: 1,
  blocked_count: 0,
  review_decision_count: 2,
  accepted_count: 2,
  rejected_count: 0,
  edited_count: 0,
  deferred_count: 0,
  acceptance_rate: 100,
  commit_rate: 100,
  oldest_pending_proposal_id: "proposal-app-intents-storekit-edge",
  oldest_pending_created_at: timestamp
};

export const demoReviewQueue = {
  pending_count: 1,
  ready_count: 1,
  blocked_count: 0,
  items: [
    {
      proposal: demoProposals[1],
      source: demoSources[5],
      priority_score: 82,
      action: "review_relationship" as const,
      work_item_kind: "new_relation" as const,
      change_summary: "StoreKit relates_to App Intents",
      evidence_summary: "Commerce entitlement state may need intent-driven exposure.",
      affected_graph_ids: [n.storekit, n.appIntents],
      citations: [
        {
          id: "citation-proposal-app-intents-storekit-edge",
          label: "Native iOS 26 Swift App Blueprint",
          source_id: demoSources[5].id,
          source_title: demoSources[5].title,
          proposal_id: "proposal-app-intents-storekit-edge",
          locator: "commerce release",
          quote: "Review whether commerce entitlement state should be exposed through App Intents.",
          confidence: 0.62
        }
      ],
      blocked: false,
      ready_to_commit: true,
      reason: "Review whether commerce entitlement state should be exposed through App Intents.",
      endpoint_node_ids: [n.storekit, n.appIntents],
      missing_endpoint_node_ids: []
    }
  ]
};

export const demoReviewActivity = {
  review_decision_count: 2,
  returned_count: 2,
  items: [
    {
      decision: {
        id: "review-liquid-glass-adoption",
        reviewer_id: "maintainer",
        decision: "accept" as const,
        decided_at: timestamp
      },
      proposal: demoProposals[0],
      source: demoSources[2],
      summary: "Accepted Liquid Glass as a first-class iOS 26 design concept."
    },
    {
      decision: {
        id: "review-navigation-tests",
        reviewer_id: "maintainer",
        decision: "accept" as const,
        decided_at: timestamp
      },
      proposal: demoProposals[2],
      source: demoSources[5],
      summary: "Accepted navigation route tests as a release gate."
    }
  ]
};

export const demoSourceReviewCoverage = {
  source_count: demoSources.length,
  proposal_count: demoProposals.length,
  pending_count: 1,
  reviewed_count: 2,
  returned_count: demoSources.length,
  sources: demoSources.map((demoSource, index) => ({
    source: demoSource,
    status: index === 5 ? "mixed" as const : "reviewed" as const,
    proposal_count: index === 5 ? 2 : index === 2 ? 1 : 0,
    pending_count: index === 5 ? 1 : 0,
    reviewed_count: index === 5 ? 1 : index === 2 ? 1 : 0,
    decision_count: index === 5 ? 1 : index === 2 ? 1 : 0,
    accepted_count: index === 5 ? 1 : index === 2 ? 1 : 0,
    rejected_count: 0,
    edited_count: 0,
    deferred_count: 0,
    last_reviewed_at: index === 5 || index === 2 ? timestamp : null
  }))
};

export const demoInsights = buildDemoInsights();

export const demoNeighborhood = {
  center_node: apiNode(demoNodes[0]),
  depth: 1,
  limit: 12,
  nodes: demoNodes
    .filter((nodeItem) => nodeItem.id === n.app || demoEdges.some((edgeItem) => edgeItem.sourceNodeId === n.app && edgeItem.targetNodeId === nodeItem.id))
    .slice(0, 12)
    .map(apiNode),
  edges: demoEdges.filter((edgeItem) => edgeItem.sourceNodeId === n.app).slice(0, 12).map(apiEdge),
  omitted_node_count: Math.max(0, demoNodes.length - 12),
  omitted_edge_count: Math.max(0, demoEdges.filter((edgeItem) => edgeItem.sourceNodeId === n.app).length - 12)
};

export const demoPath = {
  source_node: apiNode(demoNodes[0]),
  target_node: apiNode(demoNodes.find((nodeItem) => nodeItem.id === n.appStore) ?? demoNodes[0]),
  max_depth: 4,
  path_found: true,
  distance: 3,
  nodes: [n.app, n.privacy, n.distribution, n.appStore].flatMap((nodeId) => {
    const match = demoNodes.find((nodeItem) => nodeItem.id === nodeId);
    return match ? [apiNode(match)] : [];
  }),
  edges: ["edge-app-privacy", "edge-distribution-privacy", "edge-appstore-distribution"].flatMap((edgeId) => {
    const match = demoEdges.find((edgeItem) => edgeItem.id === edgeId);
    return match ? [apiEdge(match)] : [];
  })
};

export const demoLineage = {
  entity_kind: "node" as const,
  entity_id: n.app,
  source: demoSources[5],
  proposals: demoProposals,
  review_decisions: demoReviewActivity.items.map((item) => item.decision),
  nodes: [apiNode(demoNodes[0])],
  edges: demoEdges.filter((edgeItem) => edgeItem.sourceNodeId === n.app).slice(0, 4).map(apiEdge),
  provenance: demoNodes[0].provenance
};

export const demoDefaultSourceText =
  "Native iOS 26 Swift apps start with a SwiftUI-first app structure, adopt Liquid Glass through system controls, model durable data with SwiftData, expose key actions through App Intents, validate with Swift Testing and XCTest, and ship through App Store Connect with privacy and release gates.";

function source(id: string, title: string, kind: Source["kind"], uri: string): Source {
  return {
    id: id as SourceId,
    projectId,
    kind,
    title,
    uri,
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

function node(
  id: string,
  label: string,
  kind: ContentNode["kind"],
  summary: string,
  sourceId: SourceId,
  locator: string
): ContentNode {
  return {
    id: id as ContentNodeId,
    projectId,
    topicIds: [],
    label,
    kind,
    summary,
    metadata: { extractionLenses: nodeLenses(kind, label) },
    provenance: [provenance(sourceId, locator)],
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

function edge(
  id: string,
  sourceNodeId: string,
  targetNodeId: string,
  relation: SemanticEdge["relation"],
  weight: number,
  sourceId: SourceId,
  locator: string
): SemanticEdge {
  return {
    id: id as SemanticEdgeId,
    projectId,
    sourceNodeId: sourceNodeId as ContentNodeId,
    targetNodeId: targetNodeId as ContentNodeId,
    relation,
    weight,
    metadata: { extractionLenses: edgeLenses(relation) },
    provenance: [provenance(sourceId, locator)],
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

function nodeLenses(kind: ContentNode["kind"], label: string): Array<"research" | "engineering" | "ops"> {
  const lenses: Array<"research" | "engineering" | "ops"> = [];
  if (["concept", "term", "document", "source", "dataset"].includes(kind)) lenses.push("research");
  if (["system", "component", "service", "api", "repository", "module", "package", "file", "symbol"].includes(kind)) {
    lenses.push("engineering");
  }
  if (["decision", "workflow", "process", "policy", "vendor", "incident", "project", "owner", "review_cycle", "organization", "team"].includes(kind)) {
    lenses.push("ops");
  }
  if (["release", "app store", "privacy", "distribution", "migration"].some((word) => label.toLowerCase().includes(word))) {
    if (!lenses.includes("ops")) lenses.push("ops");
  }
  return lenses.length > 0 ? lenses : ["research"];
}

function edgeLenses(relation: SemanticEdge["relation"]): Array<"research" | "engineering" | "ops"> {
  const lenses: Array<"research" | "engineering" | "ops"> = [];
  if (["supports", "contradicts", "causes", "mentions", "defines", "relates_to", "references"].includes(relation)) lenses.push("research");
  if (["depends_on", "defines", "imports", "implements", "contains", "references"].includes(relation)) lenses.push("engineering");
  if (["owned_by", "has_review_cycle", "governs", "supports", "depends_on"].includes(relation)) lenses.push("ops");
  return lenses.length > 0 ? lenses : ["research"];
}

function provenance(sourceId: SourceId, locator: string): Provenance {
  const sourceItem = demoSources.find((item) => item.id === sourceId);
  return {
    sourceId,
    sourceUri: sourceItem?.uri,
    locator,
    extractedBy: "human",
    actorId: "demo-author",
    observedAt: timestamp,
    traceId: `trace-demo-${sourceId}-${locator}`.replaceAll(/[^a-zA-Z0-9_-]+/g, "-")
  };
}

function apiNode(nodeItem: ContentNode) {
  return {
    id: nodeItem.id,
    project_id: nodeItem.projectId,
    topic_ids: nodeItem.topicIds,
    label: nodeItem.label,
    kind: nodeItem.kind,
    summary: nodeItem.summary,
    metadata: nodeItem.metadata,
    provenance: nodeItem.provenance,
    created_at: nodeItem.createdAt,
    updated_at: nodeItem.updatedAt
  };
}

function apiEdge(edgeItem: SemanticEdge) {
  return {
    id: edgeItem.id,
    project_id: edgeItem.projectId,
    source_node_id: edgeItem.sourceNodeId,
    target_node_id: edgeItem.targetNodeId,
    relation: edgeItem.relation,
    weight: edgeItem.weight,
    metadata: edgeItem.metadata,
    provenance: edgeItem.provenance,
    created_at: edgeItem.createdAt,
    updated_at: edgeItem.updatedAt
  };
}

function buildDemoInsights() {
  const degreeByNodeId = new Map<ContentNode["id"], number>(demoNodes.map((nodeItem) => [nodeItem.id, 0]));
  for (const edgeItem of demoEdges) {
    degreeByNodeId.set(edgeItem.sourceNodeId, (degreeByNodeId.get(edgeItem.sourceNodeId) ?? 0) + 1);
    degreeByNodeId.set(edgeItem.targetNodeId, (degreeByNodeId.get(edgeItem.targetNodeId) ?? 0) + 1);
  }

  return {
    node_count: demoNodes.length,
    edge_count: demoEdges.length,
    source_count: demoSources.length,
    proposal_count: demoProposals.length,
    pending_proposal_count: demoProposals.filter((proposal) => proposal.status === "pending_review").length,
    connected_edge_count: demoEdges.length,
    orphan_edge_count: 0,
    provenance_coverage: {
      reviewed_item_count: demoNodes.length + demoEdges.length,
      traced_item_count: demoNodes.length + demoEdges.length,
      missing_item_count: 0,
      coverage_percent: 100
    },
    top_nodes: [...demoNodes]
      .sort((left, right) => (degreeByNodeId.get(right.id) ?? 0) - (degreeByNodeId.get(left.id) ?? 0))
      .slice(0, 5)
      .map((nodeItem) => ({
        id: nodeItem.id,
        label: nodeItem.label,
        kind: nodeItem.kind,
        degree: degreeByNodeId.get(nodeItem.id) ?? 0
      }))
  };
}
