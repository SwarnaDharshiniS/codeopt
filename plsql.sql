-- ============================================================
--  CodeOpt  —  PL/SQL : Functions, Stored Procedures, Triggers
--  MySQL 8.x compatible
-- ============================================================
use code_optimization_db;
DELIMITER $$

-- ============================================================
-- SECTION 1 : FUNCTIONS
-- ============================================================

-- ------------------------------------------------------------
-- fn_get_submission_count(user_id)
--   Returns total code submissions owned by a user
-- ------------------------------------------------------------
DROP FUNCTION IF EXISTS fn_get_submission_count$$
CREATE FUNCTION fn_get_submission_count(p_user_id INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_count INT;

    SELECT COUNT(*)
    INTO   v_count
    FROM   code_submissions cs
    JOIN   projects p ON cs.project_id = p.project_id
    WHERE  p.user_id = p_user_id;

    RETURN v_count;
END$$


-- ------------------------------------------------------------
-- fn_get_run_count(user_id)
--   Returns total optimisation runs owned by a user
-- ------------------------------------------------------------
DROP FUNCTION IF EXISTS fn_get_run_count$$
CREATE FUNCTION fn_get_run_count(p_user_id INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_count INT;

    SELECT COUNT(*)
    INTO   v_count
    FROM   optimization_runs  orr
    JOIN   code_submissions   cs  ON orr.submission_id = cs.submission_id
    JOIN   projects           p   ON cs.project_id     = p.project_id
    WHERE  p.user_id = p_user_id;

    RETURN v_count;
END$$


-- ------------------------------------------------------------
-- fn_get_project_count(user_id)
--   Returns total projects owned by a user
-- ------------------------------------------------------------
DROP FUNCTION IF EXISTS fn_get_project_count$$
CREATE FUNCTION fn_get_project_count(p_user_id INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_count INT;

    SELECT COUNT(*)
    INTO   v_count
    FROM   projects
    WHERE  user_id = p_user_id;

    RETURN v_count;
END$$


-- ============================================================
-- SECTION 2 : STORED PROCEDURES
-- ============================================================

-- ------------------------------------------------------------
-- sp_register_user(name, email, password_hash, OUT result)
--   OUT result:
--     'OK'              — user created successfully
--     'EMAIL_EXISTS'    — email already registered
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_register_user$$
CREATE PROCEDURE sp_register_user(
    IN  p_name          VARCHAR(255),
    IN  p_email         VARCHAR(255),
    IN  p_password_hash VARCHAR(255),
    OUT p_result        VARCHAR(50)
)
BEGIN
    DECLARE v_existing INT DEFAULT 0;

    SELECT COUNT(*) INTO v_existing
    FROM   users
    WHERE  email = p_email;

    IF v_existing > 0 THEN
        SET p_result = 'EMAIL_EXISTS';
    ELSE
        INSERT INTO users (name, email, password_hash)
        VALUES (p_name, p_email, p_password_hash);

        SET p_result = 'OK';
    END IF;
END$$


-- ------------------------------------------------------------
-- sp_get_dashboard_stats(user_id, OUT projects, OUT submissions, OUT runs)
--   Returns all three dashboard counter values in one call,
--   reusing the scalar functions defined above.
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_get_dashboard_stats$$
CREATE PROCEDURE sp_get_dashboard_stats(
    IN  p_user_id     INT,
    OUT p_projects    INT,
    OUT p_submissions INT,
    OUT p_runs        INT
)
BEGIN
    SET p_projects    = fn_get_project_count(p_user_id);
    SET p_submissions = fn_get_submission_count(p_user_id);
    SET p_runs        = fn_get_run_count(p_user_id);
END$$


-- ------------------------------------------------------------
-- sp_save_optimization_run(submission_id, profile_id,
--                           binary_size_kb, exec_time_ms,
--                           output_text,   return_code,
--                           OUT run_id)
--   Upserts an optimization_runs row:
--     • If a row already exists for (submission_id, profile_id)
--       → UPDATE it in-place
--     • Otherwise → INSERT a new row
--   Returns the run_id either way.
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_save_optimization_run$$
CREATE PROCEDURE sp_save_optimization_run(
    IN  p_submission_id   INT,
    IN  p_profile_id      INT,
    IN  p_binary_size_kb  DECIMAL(10,2),
    IN  p_exec_time_ms    INT,
    IN  p_output          TEXT,
    IN  p_return_code     INT,
    OUT p_run_id          INT
)
BEGIN
    DECLARE v_existing_id INT DEFAULT NULL;

    SELECT run_id INTO v_existing_id
    FROM   optimization_runs
    WHERE  submission_id = p_submission_id
    AND    profile_id    = p_profile_id
    LIMIT  1;

    IF v_existing_id IS NOT NULL THEN
        UPDATE optimization_runs
        SET    binary_size_kb = p_binary_size_kb,
               exec_time_ms  = p_exec_time_ms,
               output        = p_output,
               return_code   = p_return_code,
               executed_at   = CURRENT_TIMESTAMP
        WHERE  run_id = v_existing_id;

        SET p_run_id = v_existing_id;
    ELSE
        INSERT INTO optimization_runs
            (submission_id, profile_id, binary_size_kb,
             exec_time_ms, output, return_code)
        VALUES
            (p_submission_id, p_profile_id, p_binary_size_kb,
             p_exec_time_ms, p_output, p_return_code);

        SET p_run_id = LAST_INSERT_ID();
    END IF;
END$$

-- ------------------------------------------------------------
-- sp_create_project(user_id, project_name, OUT project_id)
--   Inserts a new project and returns its generated ID.
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_create_project$$
CREATE PROCEDURE sp_create_project(
    IN  p_user_id      INT,
    IN  p_project_name VARCHAR(255),
    OUT p_project_id   INT
)
BEGIN
    INSERT INTO projects (user_id, project_name)
    VALUES (p_user_id, p_project_name);

    SET p_project_id = LAST_INSERT_ID();
END$$


-- ------------------------------------------------------------
-- sp_save_submission(project_id, language, source_code,
--                    input_data, submission_name, OUT submission_id)
--   Inserts a code submission and returns its generated ID.
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_save_submission$$
CREATE PROCEDURE sp_save_submission(
    IN  p_project_id      INT,
    IN  p_language        VARCHAR(20),
    IN  p_source_code     LONGTEXT,
    IN  p_input_data      TEXT,
    IN  p_submission_name VARCHAR(255),
    OUT p_submission_id   INT
)
BEGIN
    INSERT INTO code_submissions
        (project_id, language, source_code, input_data, submission_name)
    VALUES
        (p_project_id, p_language, p_source_code, p_input_data, p_submission_name);
    SET p_submission_id = LAST_INSERT_ID();
    IF p_submission_name IS NULL OR TRIM(p_submission_name) = '' THEN
        UPDATE code_submissions
        SET submission_name = CONCAT('Submission #', p_submission_id)
        WHERE submission_id = p_submission_id;
    END IF;
END$$


-- ============================================================
-- SECTION 3 : TRIGGERS
-- ============================================================

-- ------------------------------------------------------------
-- trg_after_optimization_run_insert
--   After every new optimisation run, stamp the parent
--   code_submissions row with the latest output and timestamp.
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_after_optimization_run_insert$$

CREATE TRIGGER trg_after_optimization_run_insert
AFTER INSERT ON optimization_runs
FOR EACH ROW
BEGIN
    UPDATE code_submissions
    SET    updated_at = CURRENT_TIMESTAMP
    WHERE  submission_id = NEW.submission_id;
END$$

-- ------------------------------------------------------------
-- trg_after_optimization_run_update
--   Same as above, fires when an existing run row is updated.
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_after_optimization_run_update$$

CREATE TRIGGER trg_after_optimization_run_update
AFTER UPDATE ON optimization_runs
FOR EACH ROW
BEGIN
    UPDATE code_submissions
    SET    updated_at = CURRENT_TIMESTAMP
    WHERE  submission_id = NEW.submission_id;
END$$

DELIMITER ;

 