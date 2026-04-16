-- 001_initial.sql — sessions table (PRD §5.3)

CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT    NOT NULL,  -- ISO 8601
    ended_at   TEXT    NOT NULL,  -- ISO 8601
    duration_s INTEGER NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('work', 'short_break', 'long_break')),
    tag        TEXT,
    completed  INTEGER NOT NULL DEFAULT 1
);
