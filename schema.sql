-- ============================================================
--  CodeOpt — MySQL Schema DDL
--  Run this FIRST, before plsql.sql and exception.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS code_optimization_db;
USE code_optimization_db;

-- ────────────────────────────────────────────────────────────
-- 1. users
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- ────────────────────────────────────────────────────────────
-- 2. projects
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    project_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT          NOT NULL,
    project_name VARCHAR(255) NOT NULL,
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_project_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 3. code_submissions
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS code_submissions (
    submission_id   INT AUTO_INCREMENT PRIMARY KEY,
    project_id      INT          NOT NULL,
    submission_name VARCHAR(255),
    language        VARCHAR(20)  NOT NULL,  -- 'c' | 'cpp' | 'python'
    source_code     LONGTEXT     NOT NULL,
    input_data      TEXT,
    last_output     TEXT,
    submitted_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP
                                 ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_submission_project
        FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 4. optimization_profiles
--    Seed data included below
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS optimization_profiles (
    profile_id      INT AUTO_INCREMENT PRIMARY KEY,
    profile_name    VARCHAR(100) NOT NULL UNIQUE,
    compiler_flags  VARCHAR(50)  NOT NULL,
    description     TEXT
);

-- Default optimization profiles
INSERT IGNORE INTO optimization_profiles (profile_name, compiler_flags, description) VALUES
    ('No Optimization',     '-O0', 'No optimization; fastest compilation, largest/slowest binary.'),
    ('Basic Optimization',  '-O1', 'Basic speed and size optimizations.'),
    ('Standard Optimization', '-O2', 'Recommended for most production code.'),
    ('Aggressive Optimization', '-O3', 'Maximum speed; may increase binary size.'),
    ('Size Optimization',   '-Os', 'Optimize for smallest binary size.'),
    ('Size + Speed',        '-Oz', 'Most aggressive size reduction (GCC/Clang).'),
    ('Debug',               '-Og', 'Optimize for debugging experience.');

-- ────────────────────────────────────────────────────────────
-- 5. optimization_runs
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS optimization_runs (
    run_id         INT AUTO_INCREMENT PRIMARY KEY,
    submission_id  INT            NOT NULL,
    profile_id     INT            NOT NULL,
    binary_size_kb DECIMAL(10,2)  DEFAULT 0,
    exec_time_ms   INT            DEFAULT 0,
    output         TEXT,
    return_code    INT            DEFAULT 0,
    executed_at    DATETIME       DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_run_submission
        FOREIGN KEY (submission_id)
        REFERENCES code_submissions(submission_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_run_profile
        FOREIGN KEY (profile_id)
        REFERENCES optimization_profiles(profile_id)
        ON DELETE CASCADE
);

-- ────────────────────────────────────────────────────────────
-- 6. execution_error_log
--    (also created by exception.sql — safe to run either way)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS execution_error_log (
    error_id       INT AUTO_INCREMENT PRIMARY KEY,
    submission_id  INT          NOT NULL,
    language       VARCHAR(20)  NOT NULL,
    error_type     VARCHAR(50)  NOT NULL,  -- COMPILE_ERROR | RUNTIME_ERROR | TIMEOUT
    error_message  TEXT,
    opt_flag       VARCHAR(20)  DEFAULT NULL,
    exec_time_ms   INT          DEFAULT NULL,
    logged_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_err_submission
        FOREIGN KEY (submission_id)
        REFERENCES code_submissions(submission_id)
        ON DELETE CASCADE
);
