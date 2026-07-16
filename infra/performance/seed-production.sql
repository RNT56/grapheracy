\set ON_ERROR_STOP on
BEGIN;
INSERT INTO graph_projects (id, name, description, created_at, updated_at)
VALUES ('project-performance', 'Production-size benchmark', '100k nodes and 500k edges', now(), now())
ON CONFLICT (id) DO NOTHING;
INSERT INTO graph_settings (project_id, llm_enabled, llm_provider, llm_model, auto_commit_threshold, settings_json, created_at, updated_at)
VALUES ('project-performance', false, 'graphview-local', null, 0.92, '{}', now(), now())
ON CONFLICT (project_id) DO NOTHING;
INSERT INTO graph_layouts (id, project_id, name, algorithm, graph_version, settings_json, created_by, created_at, updated_at)
VALUES ('layout-performance-default', 'project-performance', 'default', 'seeded-grid', 1, '{}', 'benchmark', now(), now())
ON CONFLICT (project_id, name) DO NOTHING;
INSERT INTO content_nodes (id, project_id, topic_ids_json, label, kind, summary, metadata_json, provenance_json, created_at, updated_at)
SELECT 'perf-node-' || lpad(i::text, 6, '0'), 'project-performance', '[]', 'Benchmark node ' || i,
  CASE i % 6 WHEN 0 THEN 'system' WHEN 1 THEN 'concept' WHEN 2 THEN 'document' WHEN 3 THEN 'service' WHEN 4 THEN 'task' ELSE 'metric' END,
  'Seeded production-size graph node ' || i, '{}', '[]', now(), now()
FROM generate_series(1, 100000) AS i
ON CONFLICT (id) DO NOTHING;
INSERT INTO graph_layout_positions (layout_id, node_id, x, y, z, cluster_key)
SELECT 'layout-performance-default', 'perf-node-' || lpad(i::text, 6, '0'),
  ((i - 1) % 400)::float / 199.5 - 1, ((i - 1) / 400)::float / 124.5 - 1, 0, null
FROM generate_series(1, 100000) AS i
ON CONFLICT (layout_id, node_id) DO NOTHING;
INSERT INTO semantic_edges (id, project_id, source_node_id, target_node_id, relation, weight, metadata_json, provenance_json, created_at, updated_at)
SELECT 'perf-edge-' || lpad(i::text, 7, '0'), 'project-performance',
  'perf-node-' || lpad((((i - 1) % 100000) + 1)::text, 6, '0'),
  'perf-node-' || lpad((((((i - 1) % 100000) + 1) + (((i - 1) / 100000) + 1) * 7919 - 1) % 100000 + 1)::text, 6, '0'),
  CASE ((i - 1) / 100000) WHEN 0 THEN 'supports' WHEN 1 THEN 'depends_on' WHEN 2 THEN 'references' WHEN 3 THEN 'relates_to' ELSE 'part_of' END,
  0.75, '{}', '[]', now(), now()
FROM generate_series(1, 500000) AS i
ON CONFLICT (id) DO NOTHING;
UPDATE semantic_edges
SET relation = 'part_of', updated_at = now()
WHERE project_id = 'project-performance' AND relation = 'derived_from';
INSERT INTO graph_versions (project_id, version, node_count, edge_count, updated_at)
VALUES ('project-performance', 1, 100000, 500000, now())
ON CONFLICT (project_id) DO UPDATE SET node_count=excluded.node_count, edge_count=excluded.edge_count, updated_at=excluded.updated_at;
COMMIT;
ANALYZE content_nodes;
ANALYZE semantic_edges;
ANALYZE graph_layout_positions;
