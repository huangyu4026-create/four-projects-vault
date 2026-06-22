-- 红楼梦聚拢坐标映射总库 schema snapshot
-- Source: /Users/yu/Documents/Codex/2026-06-21/new-chat-3/outputs/红楼梦聚拢坐标映射总库_CH001_120/红楼梦聚拢坐标映射总库_CH001_120.sqlite

-- index: idx_atom_codebook_event
CREATE INDEX idx_atom_codebook_event ON atom_codebook(event_id);

-- index: idx_atom_codebook_order
CREATE INDEX idx_atom_codebook_order ON atom_codebook(global_atom_order);

-- index: idx_atom_codebook_scene
CREATE INDEX idx_atom_codebook_scene ON atom_codebook(scene_id);

-- index: idx_atom_distance_containers
CREATE INDEX idx_atom_distance_containers ON atom_distance_basis(cluster_id, event_id, scene_group_id, time_block_id);

-- index: idx_atom_distance_order
CREATE INDEX idx_atom_distance_order ON atom_distance_basis(global_atom_order);

-- index: idx_atoms_chapter_order
CREATE INDEX idx_atoms_chapter_order ON clean_atoms(chapter_no, atom_order_in_chapter);

-- index: idx_atoms_global_order
CREATE INDEX idx_atoms_global_order ON clean_atoms(global_atom_order);

-- index: idx_char_atom_bridge_atom
CREATE INDEX idx_char_atom_bridge_atom ON char_atom_bridge(atom_id);

-- index: idx_char_atom_bridge_char
CREATE INDEX idx_char_atom_bridge_char ON char_atom_bridge(chapter_no, char_pos);

-- index: idx_clean_atoms_chapter
CREATE INDEX idx_clean_atoms_chapter ON clean_atoms(chapter_no, atom_order_in_chapter);

-- index: idx_clean_atoms_order
CREATE INDEX idx_clean_atoms_order ON clean_atoms(global_atom_order);

-- index: idx_container_codebook_range
CREATE INDEX idx_container_codebook_range ON container_codebook(start_atom_order, end_atom_order);

-- index: idx_container_codebook_type_id
CREATE INDEX idx_container_codebook_type_id ON container_codebook(container_type, container_id);

-- index: idx_distance_cluster
CREATE INDEX idx_distance_cluster ON atom_distance_basis(cluster_id);

-- index: idx_distance_event
CREATE INDEX idx_distance_event ON atom_distance_basis(event_id);

-- index: idx_distance_scene
CREATE INDEX idx_distance_scene ON atom_distance_basis(scene_id);

-- index: idx_hierarchy_lower
CREATE INDEX idx_hierarchy_lower ON container_hierarchy(lower_type, lower_id);

-- index: idx_hierarchy_upper
CREATE INDEX idx_hierarchy_upper ON container_hierarchy(upper_type, upper_id);

-- index: idx_links_atom
CREATE INDEX idx_links_atom ON atom_links(atom_id);

-- index: idx_links_chapter
CREATE INDEX idx_links_chapter ON atom_links(chapter_no);

-- index: idx_links_type_value
CREATE INDEX idx_links_type_value ON atom_links(link_type, link_value_name);

-- index: idx_memberships_atom
CREATE INDEX idx_memberships_atom ON atom_memberships(atom_id);

-- index: idx_memberships_container
CREATE INDEX idx_memberships_container ON atom_memberships(container_type, container_id);

-- index: idx_projection_atom
CREATE INDEX idx_projection_atom ON atom_projection_codebook(atom_id);

-- index: idx_projection_grade
CREATE INDEX idx_projection_grade ON atom_projection_codebook(granularity_level, evidence_grade);

-- index: idx_projection_type_value
CREATE INDEX idx_projection_type_value ON atom_projection_codebook(variable_type, variable_value_name);

-- index: idx_quality_findings_type
CREATE INDEX idx_quality_findings_type ON quality_findings(finding_type, severity);

-- index: idx_retired_source_map_source
CREATE INDEX idx_retired_source_map_source ON retired_source_to_atom_map(retired_source_segment_id);

-- index: idx_term_atom_pos
CREATE INDEX idx_term_atom_pos ON term_atom_occurrences(chapter_no, start_char);

-- index: idx_term_atom_start
CREATE INDEX idx_term_atom_start ON term_atom_occurrences(start_atom_id);

-- index: idx_term_atom_term
CREATE INDEX idx_term_atom_term ON term_atom_occurrences(term_norm, term_len);

-- table: atom_anchors
CREATE TABLE atom_anchors (
    atom_id TEXT PRIMARY KEY,
    old_segment_no TEXT NOT NULL,
    anchor_status TEXT,
    evidence_eligible TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    anchor_text TEXT,
    method TEXT NOT NULL,
    query_source TEXT,
    query_text TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

-- table: atom_codebook
CREATE TABLE atom_codebook (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    old_segment_no TEXT NOT NULL,
    global_atom_order INTEGER NOT NULL,
    linear_code TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    chapter_code TEXT NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    self_range_code TEXT NOT NULL,
    cluster_id TEXT,
    event_id TEXT,
    scene_id TEXT,
    scene_group_id TEXT,
    time_block_id TEXT,
    coordinate_summary TEXT NOT NULL,
    overlap_status TEXT NOT NULL,
    scene_membership_count INTEGER NOT NULL,
    scene_group_membership_count INTEGER NOT NULL,
    time_block_membership_count INTEGER NOT NULL,
    primary_scene_id TEXT,
    secondary_scene_ids TEXT,
    primary_scene_group_id TEXT,
    secondary_scene_group_ids TEXT,
    primary_time_block_id TEXT,
    secondary_time_block_ids TEXT,
    summary TEXT,
    quote TEXT
);

-- table: atom_distance_basis
CREATE TABLE atom_distance_basis (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL,
    old_segment_no TEXT NOT NULL,
    cluster_id TEXT,
    event_id TEXT,
    scene_id TEXT,
    scene_group_id TEXT,
    time_block_id TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

-- table: atom_flat_index
CREATE TABLE atom_flat_index (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL,
    old_segment_no TEXT NOT NULL,
    cluster_ids TEXT,
    event_ids TEXT,
    scene_ids TEXT,
    scene_group_ids TEXT,
    time_block_ids TEXT,
    persons TEXT,
    spaces TEXT,
    objects TEXT,
    time_points TEXT,
    seasons TEXT,
    note_types TEXT,
    note_dimensions TEXT,
    functions TEXT,
    review_flags TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

-- table: atom_links
CREATE TABLE atom_links (
    link_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    link_value_id TEXT,
    link_value_name TEXT NOT NULL,
    link_role TEXT,
    scope TEXT NOT NULL,
    precision TEXT NOT NULL,
    chapter_no INTEGER,
    source_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    review_status TEXT NOT NULL DEFAULT 'resolved',
    raw_value TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

-- table: atom_memberships
CREATE TABLE atom_memberships (
    membership_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    container_label TEXT,
    chapter_no INTEGER,
    role TEXT,
    order_in_container INTEGER,
    is_primary INTEGER NOT NULL DEFAULT 0,
    source_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    review_status TEXT NOT NULL DEFAULT 'resolved',
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

-- table: atom_projection_codebook
CREATE TABLE atom_projection_codebook (
    projection_code_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    atom_code TEXT NOT NULL,
    variable_type TEXT NOT NULL,
    variable_value_id TEXT,
    variable_value_name TEXT NOT NULL,
    variable_role TEXT,
    granularity_level TEXT NOT NULL,
    evidence_grade TEXT NOT NULL,
    scope TEXT,
    precision TEXT,
    confidence REAL,
    review_status TEXT,
    coordinate_summary TEXT NOT NULL
);

-- table: atom_source_map
CREATE TABLE atom_source_map (
    atom_id TEXT PRIMARY KEY,
    old_segment_no TEXT NOT NULL,
    page_id TEXT,
    source_db TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row INTEGER,
    source_key TEXT NOT NULL
);

-- table: build_meta
CREATE TABLE build_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- table: char_atom_bridge
CREATE TABLE char_atom_bridge (
            chapter_no INTEGER NOT NULL,
            char_pos INTEGER NOT NULL,
            char_text TEXT NOT NULL,
            atom_id TEXT NOT NULL,
            atom_code TEXT NOT NULL,
            old_segment_no TEXT NOT NULL,
            global_atom_order INTEGER NOT NULL,
            atom_order_in_chapter INTEGER NOT NULL,
            retired_source_segment_id TEXT NOT NULL,
            retired_source_segment_code TEXT NOT NULL,
            retired_source_global_order INTEGER NOT NULL,
            PRIMARY KEY (chapter_no, char_pos)
        );

-- table: clean_atoms
CREATE TABLE clean_atoms (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL UNIQUE,
    chapter_no INTEGER NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL UNIQUE,
    old_segment_no TEXT NOT NULL UNIQUE,
    page_id TEXT,
    chapter_page_id TEXT,
    chapter_label TEXT,
    summary TEXT,
    quote TEXT,
    original_version TEXT,
    scene_place_raw TEXT,
    time_point_raw TEXT,
    is_focus_raw TEXT,
    perspective_raw TEXT,
    note_type_raw TEXT,
    note_dimension_raw TEXT,
    function_tags_raw TEXT,
    old_cluster_unit_raw TEXT,
    source_row INTEGER,
    source_db TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_status TEXT NOT NULL
);

-- table: container_codebook
CREATE TABLE container_codebook (
    container_code_id TEXT PRIMARY KEY,
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    container_label TEXT,
    chapter_no INTEGER,
    start_atom_order INTEGER,
    end_atom_order INTEGER,
    start_atom_id TEXT,
    end_atom_id TEXT,
    start_atom_code TEXT,
    end_atom_code TEXT,
    range_code TEXT NOT NULL,
    atom_count INTEGER,
    coordinate_summary TEXT NOT NULL,
    boundary_status TEXT NOT NULL,
    review_status TEXT
);

-- table: container_hierarchy
CREATE TABLE container_hierarchy (
    hierarchy_id TEXT PRIMARY KEY,
    lower_type TEXT NOT NULL,
    lower_id TEXT NOT NULL,
    upper_type TEXT NOT NULL,
    upper_id TEXT NOT NULL,
    chapter_no INTEGER,
    relation_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT,
    review_status TEXT NOT NULL DEFAULT 'resolved'
);

-- table: container_index
CREATE TABLE container_index (
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    container_label TEXT,
    chapter_no INTEGER,
    start_atom_order INTEGER,
    end_atom_order INTEGER,
    atom_count INTEGER,
    source_name TEXT,
    quality_status TEXT,
    review_status TEXT,
    PRIMARY KEY(container_type, container_id)
);

-- table: coordinate_reading_rules
CREATE TABLE coordinate_reading_rules (
    rule_key TEXT PRIMARY KEY,
    rule_label TEXT NOT NULL,
    reading_rule TEXT NOT NULL
);

-- table: distance_metric_rules
CREATE TABLE distance_metric_rules (
    rule_key TEXT PRIMARY KEY,
    rule_label TEXT NOT NULL,
    rule_sql_hint TEXT NOT NULL,
    interpretation TEXT NOT NULL
);

-- table: quality_findings
CREATE TABLE quality_findings (
    finding_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    detail TEXT NOT NULL,
    source_name TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'open'
);

-- table: retired_source_refinement_quality
CREATE TABLE retired_source_refinement_quality (
            retired_source_segment_id TEXT PRIMARY KEY,
            retired_source_segment_code TEXT NOT NULL,
            retired_source_segment_no TEXT NOT NULL,
            chapter_no INTEGER NOT NULL,
            source_span_len INTEGER,
            refined_atom_count INTEGER NOT NULL,
            max_refined_atom_len INTEGER NOT NULL,
            split_status TEXT NOT NULL,
            source_span_status TEXT,
            source_span_confidence REAL,
            summary TEXT
        );

-- table: retired_source_segment_lookup
CREATE TABLE retired_source_segment_lookup (
            retired_source_segment_id TEXT PRIMARY KEY,
            retired_source_segment_code TEXT NOT NULL,
            retired_source_segment_no TEXT NOT NULL,
            chapter_no INTEGER NOT NULL,
            retired_source_order_in_chapter INTEGER,
            retired_source_global_order INTEGER NOT NULL,
            cluster_id TEXT,
            event_id TEXT,
            scene_id TEXT,
            scene_group_id TEXT,
            time_block_id TEXT,
            start_char INTEGER,
            end_char INTEGER,
            span_len INTEGER,
            span_status TEXT,
            span_confidence REAL,
            summary TEXT,
            quote TEXT
        );

-- table: retired_source_to_atom_map
CREATE TABLE retired_source_to_atom_map (
            retired_source_segment_id TEXT NOT NULL,
            retired_source_segment_code TEXT NOT NULL,
            retired_source_segment_no TEXT NOT NULL,
            retired_source_global_order INTEGER NOT NULL,
            atom_id TEXT NOT NULL,
            atom_code TEXT NOT NULL,
            old_segment_no TEXT NOT NULL,
            global_atom_order INTEGER NOT NULL,
            refined_order_in_retired_source_segment INTEGER NOT NULL,
            retired_source_split_count INTEGER NOT NULL,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            span_len INTEGER NOT NULL,
            PRIMARY KEY (retired_source_segment_id, atom_id)
        );

-- table: term_atom_occurrences
CREATE TABLE term_atom_occurrences (
            occurrence_id INTEGER PRIMARY KEY,
            term_norm TEXT NOT NULL,
            term_surface TEXT NOT NULL,
            term_len INTEGER NOT NULL,
            chapter_no INTEGER NOT NULL,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            start_atom_id TEXT,
            end_atom_id TEXT,
            start_atom_code TEXT,
            old_segment_no TEXT,
            global_atom_order INTEGER,
            start_retired_source_segment_id TEXT,
            start_retired_source_segment_code TEXT,
            retired_source_global_order INTEGER,
            refined_atom_cross INTEGER NOT NULL DEFAULT 0,
            retired_source_cross INTEGER NOT NULL DEFAULT 0,
            start_span_status TEXT,
            start_span_confidence REAL
        );

-- view: atom_coordinates
CREATE VIEW atom_coordinates AS SELECT * FROM atom_codebook;

-- view: atomic_segments
CREATE VIEW atomic_segments AS SELECT * FROM atom_codebook;

-- view: v_atom_pair_distance
CREATE VIEW v_atom_pair_distance AS
        SELECT
            a.atom_id AS left_atom_id,
            b.atom_id AS right_atom_id,
            a.atom_code AS left_atom_code,
            b.atom_code AS right_atom_code,
            ABS(a.global_atom_order - b.global_atom_order) AS atom_distance,
            CASE WHEN a.chapter_no = b.chapter_no THEN 1 ELSE 0 END AS same_chapter,
            CASE WHEN a.cluster_id IS NOT NULL AND a.cluster_id = b.cluster_id THEN 1 ELSE 0 END AS same_cluster,
            CASE WHEN a.event_id IS NOT NULL AND a.event_id = b.event_id THEN 1 ELSE 0 END AS same_event,
            CASE WHEN a.scene_id IS NOT NULL AND a.scene_id = b.scene_id THEN 1 ELSE 0 END AS same_scene,
            CASE WHEN a.scene_group_id IS NOT NULL AND a.scene_group_id = b.scene_group_id THEN 1 ELSE 0 END AS same_scene_group,
            CASE WHEN a.time_block_id IS NOT NULL AND a.time_block_id = b.time_block_id THEN 1 ELSE 0 END AS same_time_block
        FROM atom_distance_basis a
        JOIN atom_distance_basis b ON a.atom_id < b.atom_id;

-- view: v_atom_pair_distance_directed
CREATE VIEW v_atom_pair_distance_directed AS
        SELECT
            a.atom_id AS from_atom_id,
            b.atom_id AS to_atom_id,
            a.atom_code AS from_atom_code,
            b.atom_code AS to_atom_code,
            b.global_atom_order - a.global_atom_order AS signed_atom_distance,
            ABS(b.global_atom_order - a.global_atom_order) AS abs_atom_distance,
            CASE
                WHEN b.global_atom_order > a.global_atom_order THEN 'after'
                WHEN b.global_atom_order < a.global_atom_order THEN 'before'
                ELSE 'same'
            END AS direction_from_source,
            CASE WHEN a.chapter_no = b.chapter_no THEN 1 ELSE 0 END AS same_chapter,
            CASE WHEN a.cluster_id IS NOT NULL AND a.cluster_id = b.cluster_id THEN 1 ELSE 0 END AS same_cluster,
            CASE WHEN a.event_id IS NOT NULL AND a.event_id = b.event_id THEN 1 ELSE 0 END AS same_event,
            CASE WHEN a.scene_id IS NOT NULL AND a.scene_id = b.scene_id THEN 1 ELSE 0 END AS same_scene,
            CASE WHEN a.scene_group_id IS NOT NULL AND a.scene_group_id = b.scene_group_id THEN 1 ELSE 0 END AS same_scene_group,
            CASE WHEN a.time_block_id IS NOT NULL AND a.time_block_id = b.time_block_id THEN 1 ELSE 0 END AS same_time_block
        FROM atom_distance_basis a
        JOIN atom_distance_basis b ON 1 = 1;

-- view: v_enhanced_atom_distance
CREATE VIEW v_enhanced_atom_distance AS
        SELECT * FROM v_atom_pair_distance_directed;

-- view: v_term_atom_hits
CREATE VIEW v_term_atom_hits AS
        SELECT t.*, c.atom_code, c.chapter_no, c.global_atom_order, c.summary, c.quote AS atom_text,
               c.cluster_id, c.event_id, c.scene_id, c.scene_group_id, c.time_block_id
        FROM term_atom_occurrences t
        LEFT JOIN atom_codebook c ON c.atom_id=t.start_atom_id;
