# ============================================================
#  mysql_ops.py
#  All MySQL / PL-SQL operations for CodeOpt
#  Uses stored procedures where available, direct queries otherwise.
# ============================================================

from db import get_mysql_connection


# ============================================================
# USERS
# ============================================================

def mysql_register_user(name, email, password_hash):
    """
    CREATE user via stored procedure.
    Returns 'OK' or 'EMAIL_EXISTS'.
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "CALL sp_register_user(%s, %s, %s, @result)",
        (name, email, password_hash)
    )
    conn.commit()
    cursor.execute("SELECT @result AS result")
    result = cursor.fetchone()["result"]

    cursor.close()
    conn.close()
    return result


def mysql_get_user_by_email(email):
    """READ user by email (used for login)."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def mysql_get_user_by_id(user_id):
    """READ user by ID."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def mysql_get_user_id_by_email(email):
    """READ just the user_id for a given email (post-registration)."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row["user_id"] if row else None


def mysql_update_user(user_id, name, email):
    """UPDATE user name and email."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        UPDATE users SET name = %s, email = %s
        WHERE user_id = %s
    """, (name, email, user_id))
    conn.commit()
    cursor.close()
    conn.close()


def mysql_delete_user(user_id):
    """DELETE user and cascade-delete their projects/submissions."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()


def mysql_get_all_project_ids_for_user(user_id):
    """READ — list of project_ids owned by a user."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT project_id FROM projects WHERE user_id = %s", (user_id,)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r["project_id"] for r in rows]

# ============================================================
# DASHBOARD STATS
# ============================================================

def mysql_get_dashboard_stats(user_id):
    """
    READ stats via stored procedure.
    Returns dict: {projects, submissions, runs}
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "CALL sp_get_dashboard_stats(%s, @p, @s, @r)",
        (user_id,)
    )
    cursor.execute("SELECT @p AS projects, @s AS submissions, @r AS runs")
    row = cursor.fetchone()

    cursor.close()
    conn.close()
    return {
        "projects":    row["projects"],
        "submissions": row["submissions"],
        "runs":        row["runs"],
    }


# ============================================================
# PROJECTS
# ============================================================

def mysql_create_project(user_id, project_name):
    """
    CREATE project via stored procedure.
    Returns new project_id.
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "CALL sp_create_project(%s, %s, @new_pid)",
        (user_id, project_name)
    )
    conn.commit()
    cursor.execute("SELECT @new_pid AS new_pid")
    new_pid = cursor.fetchone()["new_pid"]

    cursor.close()
    conn.close()
    return new_pid


def mysql_get_projects_by_user(user_id):
    """READ all projects for a user with owner name."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, u.name
        FROM projects p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.user_id = %s
        ORDER BY p.project_id DESC
    """, (user_id,))
    projects = cursor.fetchall()
    cursor.close()
    conn.close()
    return projects


def mysql_get_project(project_id, user_id):
    """READ single project — verifies ownership."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT project_id, project_name
        FROM projects
        WHERE project_id = %s AND user_id = %s
    """, (project_id, user_id))
    project = cursor.fetchone()
    cursor.close()
    conn.close()
    return project


def mysql_update_project(project_id, user_id, new_name):
    """UPDATE project name — verifies ownership."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        UPDATE projects SET project_name = %s
        WHERE project_id = %s AND user_id = %s
    """, (new_name, project_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()


def mysql_delete_project(project_id, user_id):
    """DELETE project — verifies ownership. Cascades to submissions."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        DELETE FROM projects
        WHERE project_id = %s AND user_id = %s
    """, (project_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()


# ============================================================
# SUBMISSIONS
# ============================================================

def mysql_create_submission(project_id, language,
                             source_code, input_data, submission_name):
    """
    CREATE submission via stored procedure.
    Returns (new_submission_id, actual_name_after_trigger).
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "CALL sp_save_submission(%s, %s, %s, %s, %s, @new_sid)",
        (project_id, language, source_code, input_data, submission_name)
    )
    conn.commit()

    cursor.execute("SELECT @new_sid AS new_sid")
    new_sid = cursor.fetchone()["new_sid"]

    # Fetch actual name — trigger may have auto-generated it
    cursor.execute(
        "SELECT submission_name FROM code_submissions WHERE submission_id = %s",
        (new_sid,)
    )
    actual_name = cursor.fetchone()["submission_name"]

    cursor.close()
    conn.close()
    return new_sid, actual_name


def mysql_get_submissions_by_project(project_id):
    """READ all submissions for a project (history list)."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT submission_id, submission_name, language, submitted_at
        FROM code_submissions
        WHERE project_id = %s
        ORDER BY submitted_at DESC
    """, (project_id,))
    submissions = cursor.fetchall()
    cursor.close()
    conn.close()
    return submissions


def mysql_get_submission(submission_id, project_id=None):
    """READ single submission. Optionally verify it belongs to project_id."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    if project_id:
        cursor.execute("""
            SELECT submission_id, submission_name, language,
                   source_code, input_data, submitted_at, last_output, project_id
            FROM code_submissions
            WHERE submission_id = %s AND project_id = %s
        """, (submission_id, project_id))
    else:
        cursor.execute("""
            SELECT submission_id, submission_name, language,
                   source_code, input_data, submitted_at, last_output, project_id
            FROM code_submissions
            WHERE submission_id = %s
        """, (submission_id,))

    submission = cursor.fetchone()
    cursor.close()
    conn.close()
    return submission


def mysql_update_last_output(submission_id, output):
    """UPDATE last_output after a normal run."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        UPDATE code_submissions
        SET last_output = %s
        WHERE submission_id = %s
    """, (output, submission_id))
    conn.commit()
    cursor.close()
    conn.close()


def mysql_delete_submission(submission_id, project_id):
    """DELETE a submission — verifies it belongs to project."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        DELETE FROM code_submissions
        WHERE submission_id = %s AND project_id = %s
    """, (submission_id, project_id))
    conn.commit()
    cursor.close()
    conn.close()


# ============================================================
# OPTIMIZATION RUNS
# ============================================================

def mysql_get_optimization_profiles():
    """READ all optimization profiles."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM optimization_profiles")
    profiles = cursor.fetchall()
    cursor.close()
    conn.close()
    return profiles


def mysql_get_optimization_profile(profile_id):
    """READ single optimization profile."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT profile_id, profile_name, compiler_flags AS opt_flag
        FROM optimization_profiles
        WHERE profile_id = %s
    """, (profile_id,))
    profile = cursor.fetchone()
    cursor.close()
    conn.close()
    return profile


def mysql_save_optimization_run(submission_id, profile_id,
                                 binary_size_kb, exec_time_ms,
                                 output, return_code):
    """
    CREATE or UPDATE optimization run via stored procedure.
    Returns run_id.
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "CALL sp_save_optimization_run(%s, %s, %s, %s, %s, %s, @run_id)",
        (submission_id, profile_id, binary_size_kb,
         exec_time_ms, output, return_code)
    )
    conn.commit()
    cursor.execute("SELECT @run_id AS run_id")
    run_id = cursor.fetchone()["run_id"]

    cursor.close()
    conn.close()
    return run_id


# ============================================================
# EXECUTION ERROR LOG
# ============================================================

# Error types
ERROR_COMPILE  = "COMPILE_ERROR"
ERROR_RUNTIME  = "RUNTIME_ERROR"
ERROR_TIMEOUT  = "TIMEOUT"

# Threshold — runs over this ms are flagged as TIMEOUT
EXEC_TIMEOUT_MS = 30000


def mysql_log_execution_error(submission_id, language, error_type,
                               error_message, opt_flag=None, exec_time_ms=None):
    """
    CREATE — log an execution error via stored procedure.
    error_type must be: COMPILE_ERROR | RUNTIME_ERROR | TIMEOUT
    Returns error_id, or -1 if logging itself failed.
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "CALL sp_log_execution_error(%s, %s, %s, %s, %s, %s, @eid)",
            (submission_id, language, error_type,
             error_message, opt_flag, exec_time_ms)
        )
        conn.commit()
        cursor.execute("SELECT @eid AS eid")
        row = cursor.fetchone()
        return row["eid"] if row else -1
    except Exception as e:
        print(f"[mysql_log_execution_error] Failed to log error: {e}")
        return -1
    finally:
        cursor.close()
        conn.close()


def mysql_get_error_logs(submission_id):
    """
    READ — all execution error logs for a submission via stored procedure.
    Returns list of dicts.
    """
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("CALL sp_get_error_logs(%s)", (submission_id,))
        results = cursor.fetchall()
        return results
    except Exception as e:
        print(f"[mysql_get_error_logs] Failed: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# ============================================================
# PASSWORD
# ============================================================

def mysql_create_reset_token(user_id, token, expires_at):
    """CREATE — store a password-reset token."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    # Delete any existing unused token for this user first
    cursor.execute(
        "DELETE FROM reset_tokens WHERE user_id = %s", (user_id,)
    )
    cursor.execute(
        "INSERT INTO reset_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user_id, token, expires_at)
    )
    conn.commit()
    cursor.close()
    conn.close()
 
 
def mysql_get_reset_token(token):
    """READ — fetch a reset token row by token string."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM reset_tokens WHERE token = %s AND used = 0", (token,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row
 
 
def mysql_mark_token_used(token):
    """UPDATE — mark a reset token as used."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "UPDATE reset_tokens SET used = 1 WHERE token = %s", (token,)
    )
    conn.commit()
    cursor.close()
    conn.close()
 
def mysql_update_password(user_id, new_password_hash):
    """UPDATE a user's password hash."""
    conn   = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        UPDATE users
        SET    password_hash = %s
        WHERE  user_id = %s
    """, (new_password_hash, user_id))
    conn.commit()
    cursor.close()
    conn.close()