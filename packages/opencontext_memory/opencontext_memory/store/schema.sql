-- opencontext_memory schema (PR2.a canonical DDL).
--
-- Source of truth for tables, indices, and the FTS5 virtual table. Loaded by
-- MemoryStore on first open; never edited by application code. Migrations land
-- in store/migrations.py (PR2.b) and stay additive unless the migrate flag is
-- explicit.

-- observations -----------------------------------------------------------------

CREATE TABLE observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_id TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'mem_save',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project TEXT,
    scope TEXT NOT NULL DEFAULT 'project',
    topic_key TEXT,
    revision_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    review_after TEXT,
    pinned INTEGER NOT NULL DEFAULT 0,
    lifecycle_state TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX observations_idx_topic
    ON observations(topic_key) WHERE deleted_at IS NULL;
CREATE INDEX observations_idx_project
    ON observations(project, scope) WHERE deleted_at IS NULL;
CREATE INDEX observations_idx_review
    ON observations(review_after) WHERE deleted_at IS NULL;

CREATE VIRTUAL TABLE observations_fts USING fts5(
    title,
    content,
    content='observations',
    content_rowid='id'
);

-- memory_relations --------------------------------------------------------------

CREATE TABLE memory_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relation TEXT NOT NULL CHECK (relation IN
        ('related','compatible','scoped','conflicts_with','supersedes','not_conflict')),
    judgment_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (judgment_status IN ('pending','judged','orphaned','ignored')),
    marked_by_actor TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    reasoning TEXT,
    model TEXT,
    judgment_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX relations_idx_a
    ON memory_relations(source_id, target_id);
CREATE INDEX relations_idx_pending
    ON memory_relations(judgment_status) WHERE judgment_status='pending';

-- sessions ----------------------------------------------------------------------

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    directory TEXT,
    project TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    -- PR2.c.i — mem_session_summary structured fields (REQ-OMT-004)
    goal TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    discoveries TEXT NOT NULL DEFAULT '[]',
    accomplished TEXT NOT NULL DEFAULT '[]',
    next_steps TEXT NOT NULL DEFAULT '[]',
    relevant_files TEXT NOT NULL DEFAULT '[]',
    summary_created_at TEXT
);