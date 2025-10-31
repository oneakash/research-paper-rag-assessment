-- init.sql
-- This file initializes the database schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Papers table
CREATE TABLE IF NOT EXISTS papers (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    authors TEXT,
    year INTEGER,
    file_path VARCHAR(255),
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_chunks INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    file_size BIGINT,
    status VARCHAR(50) DEFAULT 'processing'
);

-- Query history table
CREATE TABLE IF NOT EXISTS query_history (
    id SERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    response_text TEXT,
    papers_referenced TEXT[],
    confidence_score FLOAT,
    response_time FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(100),
    session_id VARCHAR(100)
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
CREATE INDEX IF NOT EXISTS idx_papers_upload_date ON papers(upload_date);
CREATE INDEX IF NOT EXISTS idx_query_history_timestamp ON query_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_query_history_user_id ON query_history(user_id);

-- Initial data (optional)
INSERT INTO papers (title, authors, year, file_path, status) 
VALUES 
    ('Sample Paper 1', 'Author A, Author B', 2023, '/papers/sample1.pdf', 'completed'),
    ('Sample Paper 2', 'Author C', 2024, '/papers/sample2.pdf', 'completed')
ON CONFLICT DO NOTHING;