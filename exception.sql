-- ============================================================
--  Exception handling additions for CodeOpt
-- ============================================================

DELIMITER $$

-- ============================================================
-- STEP 1: Create execution_error_log table
-- ============================================================
CREATE TABLE IF NOT EXISTS execution_error_log (
    error_id       INT AUTO_INCREMENT PRIMARY KEY,
    submission_id  INT          NOT NULL,
    language       VARCHAR(20)  NOT NULL,
    error_type     VARCHAR(50)  NOT NULL,   -- COMPILE_ERROR | RUNTIME_ERROR | TIMEOUT
    error_message  TEXT,
    opt_flag       VARCHAR(20)  DEFAULT NULL,
    exec_time_ms   INT          DEFAULT NULL,
    logged_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_err_submission
        FOREIGN KEY (submission_id)
        REFERENCES code_submissions(submission_id)
        ON DELETE CASCADE
)$$


-- ============================================================
-- STEP 2: sp_log_execution_error
--   Inserts a row into execution_error_log.
--   Called from app.py after any failed or timed-out run.
-- ============================================================
DROP PROCEDURE IF EXISTS sp_log_execution_error$$
CREATE PROCEDURE sp_log_execution_error(
    IN p_submission_id  INT,
    IN p_language       VARCHAR(20),
    IN p_error_type     VARCHAR(50),
    IN p_error_message  TEXT,
    IN p_opt_flag       VARCHAR(20),
    IN p_exec_time_ms   INT,
    OUT p_error_id      INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        -- If even logging fails, silently set error_id = -1
        SET p_error_id = -1;
    END;

    -- Validate required inputs
    IF p_submission_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_log_execution_error: submission_id cannot be NULL';
    END IF;

    IF p_error_type NOT IN ('COMPILE_ERROR', 'RUNTIME_ERROR', 'TIMEOUT') THEN
        SIGNAL SQLSTATE '45001'
            SET MESSAGE_TEXT = 'sp_log_execution_error: invalid error_type';
    END IF;

    INSERT INTO execution_error_log
        (submission_id, language, error_type,
         error_message, opt_flag, exec_time_ms)
    VALUES
        (p_submission_id, p_language, p_error_type,
         p_error_message, p_opt_flag, p_exec_time_ms);

    SET p_error_id = LAST_INSERT_ID();
END$$


-- ============================================================
-- STEP 3: sp_save_optimization_run — with full exception handling
--   Replaces the previous version.
--   Returns p_run_id = -1 on any failure.
-- ============================================================
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

    -- ── EXIT HANDLER: catches any SQL error, rolls back, signals failure ──
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_run_id = -1;
        -- Re-raise so caller can see something went wrong
        RESIGNAL;
    END;

    -- ── Input validation ──
    IF p_submission_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_save_optimization_run: submission_id cannot be NULL';
    END IF;

    IF p_profile_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_save_optimization_run: profile_id cannot be NULL';
    END IF;

    IF p_binary_size_kb IS NULL THEN
        SET p_binary_size_kb = 0;
    END IF;

    IF p_exec_time_ms IS NULL THEN
        SET p_exec_time_ms = 0;
    END IF;

    -- Verify submission exists
    IF NOT EXISTS (
        SELECT 1 FROM code_submissions
        WHERE submission_id = p_submission_id
    ) THEN
        SIGNAL SQLSTATE '45002'
            SET MESSAGE_TEXT = 'sp_save_optimization_run: submission not found';
    END IF;

    -- Verify profile exists
    IF NOT EXISTS (
        SELECT 1 FROM optimization_profiles
        WHERE profile_id = p_profile_id
    ) THEN
        SIGNAL SQLSTATE '45003'
            SET MESSAGE_TEXT = 'sp_save_optimization_run: optimization profile not found';
    END IF;

    -- ── Begin transaction ──
    START TRANSACTION;

    SELECT run_id INTO v_existing_id
    FROM   optimization_runs
    WHERE  submission_id = p_submission_id
    AND    profile_id    = p_profile_id
    LIMIT  1;

    IF v_existing_id IS NOT NULL THEN
        -- UPDATE existing run
        UPDATE optimization_runs
        SET    binary_size_kb = p_binary_size_kb,
               exec_time_ms  = p_exec_time_ms,
               output        = p_output,
               return_code   = p_return_code,
               executed_at   = CURRENT_TIMESTAMP
        WHERE  run_id = v_existing_id;

        SET p_run_id = v_existing_id;
    ELSE
        -- INSERT new run
        INSERT INTO optimization_runs
            (submission_id, profile_id, binary_size_kb,
             exec_time_ms, output, return_code)
        VALUES
            (p_submission_id, p_profile_id, p_binary_size_kb,
             p_exec_time_ms, p_output, p_return_code);

        SET p_run_id = LAST_INSERT_ID();
    END IF;

    COMMIT;
END$$


-- ============================================================
-- STEP 4: sp_get_error_logs (READ errors for a submission)
--   Used by the app to display errors on the logs page.
-- ============================================================
DROP PROCEDURE IF EXISTS sp_get_error_logs$$
CREATE PROCEDURE sp_get_error_logs(
    IN p_submission_id INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL;
    END;

    IF p_submission_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'sp_get_error_logs: submission_id cannot be NULL';
    END IF;

    SELECT  error_id,
            submission_id,
            language,
            error_type,
            error_message,
            opt_flag,
            exec_time_ms,
            logged_at
    FROM    execution_error_log
    WHERE   submission_id = p_submission_id
    ORDER BY logged_at DESC;
END$$


DELIMITER ;