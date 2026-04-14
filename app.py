import subprocess, tempfile, time, os, csv, io, secrets
from flask import Flask, render_template, request, redirect, session, jsonify, flash, Response
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from mysql_ops import (
    mysql_register_user, mysql_get_user_by_email, mysql_get_user_by_id,
    mysql_get_user_id_by_email, mysql_get_dashboard_stats,
    mysql_create_project, mysql_get_projects_by_user, mysql_get_project,
    mysql_create_submission, mysql_get_submissions_by_project,
    mysql_get_submission, mysql_update_last_output, mysql_save_optimization_run,
    mysql_get_optimization_profiles, mysql_get_optimization_profile,
    mysql_update_user, mysql_delete_user, mysql_update_project, mysql_delete_project,
    mysql_delete_submission, mysql_log_execution_error, mysql_get_error_logs,
    mysql_get_all_project_ids_for_user , mysql_update_password,
    mysql_create_reset_token, mysql_get_reset_token, mysql_mark_token_used,
    ERROR_COMPILE, ERROR_RUNTIME, ERROR_TIMEOUT, EXEC_TIMEOUT_MS
)
from mongodb_ops import (
    mongo_insert_execution_log, mongo_insert_optimization_log,
    mongo_get_execution_logs, mongo_get_optimization_logs,
    mongo_avg_exec_time_by_language, mongo_avg_metrics_by_opt_flag,
    mongo_total_execution_logs, mongo_total_optimization_logs,
    mongo_delete_execution_logs_for_submission,mongo_delete_optimization_logs_for_submission,
    mongo_avg_exec_time_by_language_for_projects, mongo_avg_metrics_by_opt_flag_for_projects,
    mongo_total_execution_logs_for_projects, mongo_total_optimization_logs_for_projects,
)
from neo4j_ops import (
    neo4j_create_user, neo4j_create_project, neo4j_create_submission,
    neo4j_create_opt_run, neo4j_get_user_graph, neo4j_get_submission_runs,
    neo4j_update_user, neo4j_update_project,
    neo4j_delete_user, neo4j_delete_project, neo4j_delete_submission,
    neo4j_get_best_opt, neo4j_get_best_opt_across_project,
    neo4j_record_user_used_profile, neo4j_get_popular_profiles_globally,
    neo4j_detect_and_link_similar, neo4j_get_similar_submissions,
    neo4j_update_submission_run_stats, neo4j_get_graph_analytics,
    neo4j_link_evolution_on_new_submission, neo4j_get_evolution_path
)

PYTHON_PATH = r"C:\Users\swarna\AppData\Local\Programs\Python\Python314\python.exe"
GCC_PATH    = r"C:\msys64\ucrt64\bin\gcc.exe"
GPP_PATH    = r"C:\msys64\ucrt64\bin\g++.exe"
PER_PAGE = 10
# Binary output directory — must be outside AppLocker-blocked temp folders
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BINARY_PATH = os.path.join(BASE_DIR, "compiled_output.exe")

# ==============================
# 1. NORMAL EXECUTION
# ==============================

def execute_code(language, code, input_data=None):
 
    with tempfile.TemporaryDirectory() as temp_dir:
        source_file = os.path.join(temp_dir, "code")
 
        if language == "c":
            source_file += ".c"
        elif language == "cpp":
            source_file += ".cpp"
        else:
            source_file += ".py"
 
        with open(source_file, "w", encoding="utf-8") as f:
            f.write(code)
 
        # ── PYTHON ──────────────────────────────────────────────────────
        if language == "python":
            start = time.time()
            try:
                proc = subprocess.run(
                    [PYTHON_PATH, source_file],
                    input=input_data,          # <-- stdin fix
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                output = proc.stdout + proc.stderr
            except subprocess.TimeoutExpired:
                output = "Execution timed out!"
                proc   = None
 
            end         = time.time()
            exec_time   = round((end - start) * 1000)
            output      = (proc.stdout + proc.stderr) if proc else output
            return_code = proc.returncode if proc else -1
            return output, exec_time, 0, return_code
 
        # ── C / C++ ─────────────────────────────────────────────────────
        compiler = GCC_PATH if language == "c" else GPP_PATH
 
        compile_proc = subprocess.run(
            [compiler, source_file, "-o", BINARY_PATH],
            capture_output=True,
            text=True
        )
 
        if compile_proc.returncode != 0:
            return compile_proc.stderr, 0, 0, compile_proc.returncode
 
        start = time.time()
        try:
            run_proc = subprocess.run(
                [BINARY_PATH],
                input=input_data,              # <-- stdin fix
                capture_output=True,
                text=True,
                timeout=30
            )
            output = run_proc.stdout + run_proc.stderr
        except subprocess.TimeoutExpired:
            output   = "Execution timed out (30s limit)"
            run_proc = None
 
        end         = time.time()
        exec_time   = round((end - start) * 1000)
        file_size   = round(os.path.getsize(BINARY_PATH) / 1024, 2) if os.path.exists(BINARY_PATH) else 0
        return_code = run_proc.returncode if run_proc else -1
 
        try: os.remove(BINARY_PATH)
        except: pass
 
        return output, exec_time, file_size, return_code
 
# ==============================
# 2. EXECUTION WITH OPTIMIZATION
# ==============================
 
def execute_code_with_opt(language, code, opt_flag, input_data=None):
 
    with tempfile.TemporaryDirectory() as temp_dir:
 
        # ── PYTHON — profile instead of "N/A" ───────────────────────────
        if language == "python":
            source_file = os.path.join(temp_dir, "code.py")
            with open(source_file, "w", encoding="utf-8") as f:
                f.write(code)
 
            profile_file = os.path.join(temp_dir, "profile.txt")
 
            # Build a wrapper script that:
            #   • runs cProfile and saves stats to profile.txt
            #   • times 3 runs with time.perf_counter for avg exec time
            wrapper = f"""
import cProfile
import pstats
import io
import time
import sys
 
# Redirect stdin if input data provided
_input = {repr(input_data or "")}
if _input:
    import io as _io
    sys.stdin = _io.StringIO(_input)
 
# ── timeit-style: run 3x, report avg ────────────────────────
times = []
for _ in range(3):
    if _input:
        sys.stdin = _io.StringIO(_input)
    t0 = time.perf_counter()
    exec(open({repr(source_file)}).read(), {{}})
    times.append(time.perf_counter() - t0)
 
avg_ms = round(sum(times) / len(times) * 1000, 2)
print(f"[timeit] avg over 3 runs: {{avg_ms}} ms")
 
# ── cProfile ────────────────────────────────────────────────
if _input:
    sys.stdin = _io.StringIO(_input)
pr = cProfile.Profile()
pr.enable()
exec(open({repr(source_file)}).read(), {{}})
pr.disable()
 
sio = io.StringIO()
ps  = pstats.Stats(pr, stream=sio).sort_stats("cumulative")
ps.print_stats(10)
print("\\n[cProfile] Top 10 functions by cumulative time:")
print(sio.getvalue())
"""
            runner_file = os.path.join(temp_dir, "runner.py")
            with open(runner_file, "w", encoding="utf-8") as f:
                f.write(wrapper)
 
            start = time.time()
            try:
                proc = subprocess.run(
                    [PYTHON_PATH, runner_file],
                    capture_output=True,
                    text=True,
                    timeout=60        # longer timeout — 3 runs + profiling
                )
                output          = proc.stdout
                compiler_output = proc.stderr if proc.stderr else "No errors."
                return_code     = proc.returncode
            except subprocess.TimeoutExpired:
                output          = "Profiling timed out (60s limit)"
                compiler_output = "Timeout"
                return_code     = -1
 
            end       = time.time()
            exec_time = round((end - start) * 1000)
 
            # Parse avg_ms from output if available for accurate reporting
            for line in output.splitlines():
                if line.startswith("[timeit] avg over 3 runs:"):
                    try:
                        exec_time = int(float(line.split(":")[1].strip().split()[0]))
                    except Exception:
                        pass
 
            return output, exec_time, 0, return_code, compiler_output
 
        # ── C / C++ — unchanged ──────────────────────────────────────────
        source_file = os.path.join(temp_dir, f"code.{'c' if language=='c' else 'cpp'}")
        with open(source_file, "w", encoding="utf-8") as f:
            f.write(code)
 
        compiler = GCC_PATH if language == "c" else GPP_PATH
 
        compile_proc = subprocess.run(
            [compiler, source_file, opt_flag, "-o", BINARY_PATH],
            capture_output=True,
            text=True
        )
        compiler_output = compile_proc.stdout + compile_proc.stderr
 
        if compile_proc.returncode != 0:
            return compiler_output, 0, 0, compile_proc.returncode, compiler_output
 
        start = time.time()
        try:
            run_proc = subprocess.run(
                [BINARY_PATH],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=30
            )
            output      = run_proc.stdout + run_proc.stderr
            return_code = run_proc.returncode
        except subprocess.TimeoutExpired:
            output      = "Execution timed out (30s limit)"
            return_code = -1
 
        end       = time.time()
        exec_time = round((end - start) * 1000)
        file_size = round(os.path.getsize(BINARY_PATH) / 1024, 2) if os.path.exists(BINARY_PATH) else 0
 
        try: os.remove(BINARY_PATH)
        except: pass
 
        return output, exec_time, file_size, return_code, compiler_output
 

app = Flask(__name__)
app.secret_key = "a1f9d2e0c1b4841289abff22f7cab91a3b48bbdd"

@app.route("/")
def index():
    return render_template("home.html")


# ── /register ────────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name     = request.form["name"]
        email    = request.form["email"]
        password = request.form["password"]
 
        hashed_password = generate_password_hash(password)
        result = mysql_register_user(name, email, hashed_password)
 
        if result == "EMAIL_EXISTS":
            flash("That email is already registered. Please log in.", "error")
            return redirect("/register")
 
        new_user_id = mysql_get_user_id_by_email(email)
        neo4j_create_user(new_user_id, name, email)
 
        flash("Account created! Please log in.", "success")
        return redirect("/login")
 
    return render_template("register.html")
 
 
# ── /login ───────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]
 
        user = mysql_get_user_by_email(email)
 
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect("/login")
 
        session["user_id"]   = user["user_id"]
        session["user_name"] = user["name"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect("/dashboard")
 
    return render_template("login.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        user  = mysql_get_user_by_email(email)
 
        # Always show the same message — don't reveal whether email exists
        if user:
            token      = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=1)
            mysql_create_reset_token(user["user_id"], token, expires_at)
 
            reset_url = f"http://127.0.0.1:5000/reset-password/{token}"
 
            # ── In production, send an email here ───────────────────────
            # For now, print to console so you can test locally:
            print(f"\n[PASSWORD RESET] Link for {email}:\n  {reset_url}\n")
            # ────────────────────────────────────────────────────────────
 
        flash("If that email is registered, a reset link has been sent.", "info")
        return redirect("/forgot-password")
 
    return render_template("forgot_password.html")
 
 
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    row = mysql_get_reset_token(token)
 
    # Validate token
    if not row:
        flash("This reset link is invalid or has already been used.", "error")
        return redirect("/login")
 
    if datetime.utcnow() > row["expires_at"]:
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect("/forgot-password")
 
    if request.method == "POST":
        new_password     = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
 
        if len(new_password) < 6:
            return render_template("reset_password.html", token=token,
                                   error="Password must be at least 6 characters.")
 
        if new_password != confirm_password:
            return render_template("reset_password.html", token=token,
                                   error="Passwords do not match.")
 
        new_hash = generate_password_hash(new_password)
        mysql_update_password(row["user_id"], new_hash)
        mysql_mark_token_used(token)
 
        flash("Password reset successfully. Please log in.", "success")
        return redirect("/login")
 
    return render_template("reset_password.html", token=token, error=None)
 
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    # MySQL: fetch user + dashboard stats
    user  = mysql_get_user_by_id(session["user_id"])
    stats = mysql_get_dashboard_stats(session["user_id"])

    return render_template("dashboard.html", user=user, stats=stats)

@app.route("/projects", methods=["GET", "POST"])
def projects():
    if "user_id" not in session:
        return redirect("/login")

    current_user = mysql_get_user_by_id(session["user_id"])

    # CREATE project
    if request.method == "POST":
        project_name = request.form["project_name"]
        user_id      = session["user_id"]

        new_pid = mysql_create_project(user_id, project_name)
        neo4j_create_project(user_id, new_pid, project_name)

    # READ all projects for this user
    projects = mysql_get_projects_by_user(session["user_id"])
    users    = [current_user]

    return render_template("projects.html",
                           users=users,
                           projects=projects)

 
# ── /submissions/<project_id> ─────────────────────────────
@app.route("/submissions/<int:project_id>", methods=["GET", "POST"])
def submissions(project_id):
    if "user_id" not in session:
        return redirect("/login")
 
    if request.method == "POST":
        sub_name  = request.form.get("submission_name", "").strip() or None
        language  = request.form.get("language")
 
        if not language:
            flash("Please select a language.", "error")
            return redirect(f"/submissions/{project_id}")
 
        code_file = request.files.get("code_file")
        code_text = request.form.get("code_text", "").strip()
        if code_file and code_file.filename != "":
            source_code = code_file.read().decode("utf-8")
        elif code_text:
            source_code = code_text
        else:
            flash("You must upload a code file or paste code.", "error")
            return redirect(f"/submissions/{project_id}")
 
        input_file = request.files.get("input_file")
        input_text = request.form.get("input_text", "").strip()
        if input_file and input_file.filename != "":
            input_data = input_file.read().decode("utf-8")
        elif input_text:
            input_data = input_text
        else:
            input_data = None
 
        new_sid, actual_name = mysql_create_submission(
            project_id, language, source_code, input_data, sub_name
        )
        neo4j_create_submission(project_id, new_sid, actual_name, language)
 
        import threading
        threading.Thread(
            target=neo4j_link_evolution_on_new_submission,
            args=(project_id, new_sid, language, None),   # <-- 4 positional args
            daemon=True
        ).start()
 
        flash(f"Submission '{actual_name}' saved.", "success")
        return redirect(f"/submissions/{project_id}")
 
    # GET — pagination
    project = mysql_get_project(project_id, session["user_id"])
    if not project:
        flash("Project not found or access denied.", "error")
        return redirect("/projects")
 
    PER_PAGE = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
 
    all_submissions = mysql_get_submissions_by_project(project_id)
    total           = len(all_submissions)
    total_pages     = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page            = min(page, total_pages)
    submissions     = all_submissions[(page - 1) * PER_PAGE : page * PER_PAGE]
 
    selected = None
    if "view" in request.args:
        selected = mysql_get_submission(request.args.get("view"), project_id)
 
    return render_template(
        "submissions.html",
        project=project,
        submissions=submissions,
        selected=selected,
        page=page,
        total_pages=total_pages,
        total=total
    )

@app.route("/run/<int:submission_id>")
def run_submission(submission_id):

    submission = mysql_get_submission(submission_id)

    output, exec_time, file_size, return_code = execute_code(
    submission["language"], submission["source_code"],
    input_data=submission.get("input_data")        # <-- add this
      )

    # ── Exception detection ──
    if return_code != 0 and exec_time == 0:
        # Compilation failed — no binary produced
        mysql_log_execution_error(
            submission_id, submission["language"],
            ERROR_COMPILE, output
        )
    elif exec_time > EXEC_TIMEOUT_MS:
        # Execution took too long — likely timeout/infinite loop
        mysql_log_execution_error(
            submission_id, submission["language"],
            ERROR_TIMEOUT, output, exec_time_ms=exec_time
        )
    elif return_code != 0:
        # Binary ran but crashed
        mysql_log_execution_error(
            submission_id, submission["language"],
            ERROR_RUNTIME, output, exec_time_ms=exec_time
        )

    # MySQL: UPDATE last_output
    mysql_update_last_output(submission_id, output)

    # MongoDB: CREATE execution log
    mongo_insert_execution_log(
        submission_id, submission["project_id"],
        submission["language"], submission["source_code"],
        output, exec_time, file_size, return_code
    )

    # Neo4j Feature 3: store run stats on node (fast, stays in request)
    neo4j_update_submission_run_stats(submission_id, output, exec_time)

    # Similarity detection runs in background so it never blocks the response
    import threading
    threading.Thread(
        target=neo4j_detect_and_link_similar,
        args=(submission_id, submission["language"], output, exec_time),
        daemon=True
    ).start()

    return render_template(
        "run_result.html",
        submission=submission,
        output=output,
        exec_time=exec_time,
        file_size=file_size,
        return_code=return_code
    )

@app.route("/opt/<int:submission_id>")
def run_with_optimization(submission_id):
    submission = mysql_get_submission(submission_id)
    profiles   = mysql_get_optimization_profiles()
    return render_template("opt_profiles.html",
                           submission=submission, profiles=profiles)

@app.route("/opt/run/<int:submission_id>/<int:profile_id>")
def run_optimized(submission_id, profile_id):

    submission   = mysql_get_submission(submission_id)
    profile      = mysql_get_optimization_profile(profile_id)
    opt_flag     = profile["opt_flag"]
    profile_name = profile["profile_name"]

    
    output, exec_time, file_size, return_code, compiler_output = execute_code_with_opt(
        submission["language"], submission["source_code"], opt_flag,
        input_data=submission.get("input_data")        # <-- add this
    )
    

    # ── Exception detection for optimized runs ──
    if return_code != 0 and exec_time == 0:
        # Compilation failed with opt flag
        mysql_log_execution_error(
            submission_id, submission["language"],
            ERROR_COMPILE,
            f"[{opt_flag}] {compiler_output or output}",
            opt_flag=opt_flag
        )
    elif exec_time > EXEC_TIMEOUT_MS:
        # Optimized binary timed out
        mysql_log_execution_error(
            submission_id, submission["language"],
            ERROR_TIMEOUT,
            f"[{opt_flag}] Execution exceeded {EXEC_TIMEOUT_MS}ms",
            opt_flag=opt_flag, exec_time_ms=exec_time
        )
    elif return_code != 0:
        # Optimized binary crashed at runtime
        mysql_log_execution_error(
            submission_id, submission["language"],
            ERROR_RUNTIME,
            f"[{opt_flag}] {output}",
            opt_flag=opt_flag, exec_time_ms=exec_time
        )

    # MongoDB: CREATE optimization log
    mongo_insert_optimization_log(
        submission_id, submission["project_id"], profile_id,
        opt_flag, submission["language"], submission["source_code"],
        output, compiler_output, exec_time, file_size, return_code
    )

    # MySQL: UPSERT optimization run via stored procedure
    mysql_save_optimization_run(
        submission_id, profile_id, file_size, exec_time, output, return_code
    )

    # Neo4j writes run in background — never blocks the response
    import threading
    _uid = session["user_id"]
    def _neo4j_opt_writes():
        neo4j_create_opt_run(
            submission_id=submission_id, profile_id=profile_id,
            profile_name=profile_name,  compiler_flags=opt_flag,
            exec_time_ms=exec_time,     file_size_kb=file_size,
            return_code=return_code
        )
        neo4j_record_user_used_profile(_uid, profile_id, profile_name, opt_flag)
        neo4j_update_submission_run_stats(submission_id, output, exec_time)

    threading.Thread(target=_neo4j_opt_writes, daemon=True).start()

    return render_template(
        "opt_result.html",
        submission=submission,
        output=output,
        exec_time=exec_time,
        file_size=file_size,
        return_code=return_code,
        optimization_flag=opt_flag,
        compilation_output=compiler_output
    )


# ======================================================
# MONGODB ROUTES
# ======================================================

# ------------------------------------------------------
# /logs/<submission_id>
#   Shows all execution + optimization logs for a submission
# ------------------------------------------------------

# ── /logs/<submission_id> ────────────────────────────────────────────────────
@app.route("/logs/<int:submission_id>")
def logs(submission_id):
    if "user_id" not in session:
        return redirect("/login")
 
    submission = mysql_get_submission(submission_id)
    if not submission:
        flash("Submission not found.", "error")
        return redirect("/projects")
 
    exec_logs  = mongo_get_execution_logs(submission_id)
    opt_logs   = mongo_get_optimization_logs(submission_id)
    error_logs = mysql_get_error_logs(submission_id)
 
    return render_template("logs.html",
                           submission=submission,
                           exec_logs=exec_logs,
                           opt_logs=opt_logs,
                           error_logs=error_logs)
 

@app.route("/logs/<int:submission_id>/export")
def export_logs_csv(submission_id):
    """
    Export all execution + optimization logs for a submission as CSV.
    GET /logs/<submission_id>/export?type=exec   → execution logs only
    GET /logs/<submission_id>/export?type=opt    → optimization logs only
    GET /logs/<submission_id>/export             → both (default)
    """
    if "user_id" not in session:
        return redirect("/login")
 
    submission = mysql_get_submission(submission_id)
    if not submission:
        flash("Submission not found.", "error")
        return redirect("/projects")
 
    log_type = request.args.get("type", "all")
    output   = io.StringIO()
    writer   = csv.writer(output)
 
    if log_type in ("exec", "all"):
        writer.writerow(["--- Execution Logs ---"])
        writer.writerow(["submission_id", "project_id", "language",
                         "exec_time_ms", "file_size_kb", "return_code",
                         "output", "ran_at"])
        for log in mongo_get_execution_logs(submission_id):
            writer.writerow([
                log.get("submission_id"), log.get("project_id"),
                log.get("language"),      log.get("exec_time_ms"),
                log.get("file_size_kb"),  log.get("return_code"),
                (log.get("output") or "").replace("\n", " | "),
                log.get("ran_at")
            ])
        writer.writerow([])
 
    if log_type in ("opt", "all"):
        writer.writerow(["--- Optimization Logs ---"])
        writer.writerow(["submission_id", "project_id", "profile_id",
                         "optimization_flag", "language",
                         "exec_time_ms", "file_size_kb", "return_code",
                         "compiler_diagnostics", "output", "ran_at"])
        for log in mongo_get_optimization_logs(submission_id):
            writer.writerow([
                log.get("submission_id"),       log.get("project_id"),
                log.get("profile_id"),          log.get("optimization_flag"),
                log.get("language"),            log.get("exec_time_ms"),
                log.get("file_size_kb"),        log.get("return_code"),
                (log.get("compiler_diagnostics") or "").replace("\n", " | "),
                (log.get("output") or "").replace("\n", " | "),
                log.get("ran_at")
            ])
 
    filename = f"logs_submission_{submission_id}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
 

@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect("/login")
 
    # scope=me → filter to logged-in user's projects only
    # scope=all (default) → global aggregations (original behaviour)
    scope = request.args.get("scope", "all")
 
    if scope == "me":
        project_ids = mysql_get_all_project_ids_for_user(session["user_id"])
 
        if project_ids:
            lang_stats = mongo_avg_exec_time_by_language_for_projects(project_ids)
            opt_stats  = mongo_avg_metrics_by_opt_flag_for_projects(project_ids)
            total_exec = mongo_total_execution_logs_for_projects(project_ids)
            total_opt  = mongo_total_optimization_logs_for_projects(project_ids)
        else:
            lang_stats = []
            opt_stats  = []
            total_exec = 0
            total_opt  = 0
    else:
        lang_stats = mongo_avg_exec_time_by_language()
        opt_stats  = mongo_avg_metrics_by_opt_flag()
        total_exec = mongo_total_execution_logs()
        total_opt  = mongo_total_optimization_logs()
 
    best_opt = opt_stats[0]["_id"] if opt_stats else "N/A"
 
    return render_template("analytics.html",
                           lang_stats=lang_stats,
                           opt_stats=opt_stats,
                           best_opt=best_opt,
                           total_exec=total_exec,
                           total_opt=total_opt,
                           scope=scope)
 
 
@app.route("/analytics/export")
def export_analytics_csv():
    if "user_id" not in session:
        return redirect("/login")
 
    import csv, io
    scope    = request.args.get("scope", "all")
    log_type = request.args.get("type", "all")
    output   = io.StringIO()
    writer   = csv.writer(output)
 
    if scope == "me":
        project_ids = mysql_get_all_project_ids_for_user(session["user_id"])
        lang_data   = mongo_avg_exec_time_by_language_for_projects(project_ids) if project_ids else []
        opt_data    = mongo_avg_metrics_by_opt_flag_for_projects(project_ids) if project_ids else []
    else:
        lang_data = mongo_avg_exec_time_by_language()
        opt_data  = mongo_avg_metrics_by_opt_flag()
 
    scope_label = "My Runs" if scope == "me" else "All Users"
    writer.writerow([f"Scope: {scope_label}"])
    writer.writerow([])
 
    if log_type in ("lang", "all"):
        writer.writerow(["--- Avg Exec Time by Language ---"])
        writer.writerow(["language", "avg_time_ms", "total_runs"])
        for row in lang_data:
            writer.writerow([row["_id"],
                             round(row.get("avg_time_ms") or 0, 2),
                             row.get("total_runs")])
        writer.writerow([])
 
    if log_type in ("opt", "all"):
        writer.writerow(["--- Avg Metrics by Optimization Flag ---"])
        writer.writerow(["opt_flag", "avg_time_ms", "avg_size_kb", "total_runs"])
        for row in opt_data:
            writer.writerow([row["_id"],
                             round(row.get("avg_time_ms") or 0, 2),
                             round(row.get("avg_size_kb") or 0, 2),
                             row.get("total_runs")])
 
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=analytics_export.csv"}
    )
 

# ======================================================
# NEO4J ROUTES
# ======================================================

# ------------------------------------------------------
# /graph  —  full graph view for logged-in user
# ------------------------------------------------------
@app.route("/graph")
def graph():
    if "user_id" not in session:
        return redirect("/login")

    return render_template("graph.html",
                           user_name=session.get("user_name"),
                           user_id=session["user_id"])


# ------------------------------------------------------
# /graph/data  —  JSON API for vis.js graph rendering
# ------------------------------------------------------
@app.route("/graph/data")
def graph_data():           
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    seen_edges = set()

    def add_edge(e):
        key = (e["from"], e["to"], e["label"])
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append(e)

    rows = neo4j_get_user_graph(session["user_id"])

    nodes = {}
    edges = []
    edge_id = 1

    for row in rows:
        # User
        uid = f"u_{row.get('user_id', session['user_id'])}"
        if uid not in nodes:
            nodes[uid] = {
                "id": uid,
                "label": row["user_name"],
                "group": "User",
                "title": f"User: {row['user_name']}"
            }

        # Project
        pid = f"p_{row['project_id']}"
        if pid not in nodes:
            nodes[pid] = {
                "id": pid,
                "label": row["project_name"],
                "group": "Project",
                "title": f"Project: {row['project_name']}"
            }

        # edges.append({"id": edge_id, "from": uid, "to": pid, "label": "OWNS"})
        add_edge({"id": edge_id, "from": uid, "to": pid, "label": "OWNS"})
        edge_id += 1

        # Submission
        sid = f"s_{row['submission_id']}"
        if sid not in nodes:
            nodes[sid] = {
                "id": sid,
                "label": row["submission_name"] or f"Sub {row['submission_id']}",
                "group": "Submission",
                "title": f"Lang: {row['language']}"
            }

        # edges.append({"id": edge_id, "from": pid, "to": sid, "label": "HAS_SUBMISSION"})
        add_edge({"id": edge_id, "from": pid, "to": sid, "label": "HAS_SUBMISSION"})
        edge_id += 1

        # Optimization
        if row.get("profile_name"):
            oid = f"op_{row['profile_name']}"

            if oid not in nodes:
                nodes[oid] = {
                    "id": oid,
                    "label": row["compiler_flags"],
                    "group": "OptimizationProfile",
                    "title": f"{row['profile_name']}\n{row['compiler_flags']}"
                }

            # edges.append({"id": edge_id, "from": sid, "to": oid, "label": "RAN_WITH"})
            add_edge({"id": edge_id, "from": sid, "to": oid, "label": "RAN_WITH"})
            edge_id += 1
    return jsonify({
        "nodes": list(nodes.values()),
        "edges": edges
    })

# ------------------------------------------------------
# /compare/<submission_id>
#   Shows all optimization runs for a submission side by side
# ------------------------------------------------------
@app.route("/compare/<int:submission_id>")
def compare(submission_id):
    if "user_id" not in session:
        return redirect("/login")

    runs       = neo4j_get_submission_runs(submission_id)
    submission = mysql_get_submission(submission_id)

    return render_template("compare.html",
                           submission=submission,
                           submission_id=submission_id,
                           runs=runs)



# ======================================================
# CRUD UI ROUTES
# ======================================================

# ── User Profile: READ + UPDATE + DELETE ─────────────

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")
 
    error      = None
    success    = None
    pw_error   = None
    pw_success = None
 
    if request.method == "POST":
        action = request.form.get("action")
 
        # ── Update name / email ──────────────────────────────────────────
        if action == "update":
            name  = request.form["name"].strip()
            email = request.form["email"].strip()
 
            existing = mysql_get_user_by_email(email)
            if existing and existing["user_id"] != session["user_id"]:
                error = "That email is already in use."
            else:
                mysql_update_user(session["user_id"], name, email)
                session["user_name"] = name
                neo4j_update_user(session["user_id"], name, email)
                success = "Profile updated successfully."
 
        # ── Change password ──────────────────────────────────────────────
        elif action == "change_password":
            current_password  = request.form.get("current_password", "")
            new_password      = request.form.get("new_password", "")
            confirm_password  = request.form.get("confirm_password", "")
 
            user = mysql_get_user_by_id(session["user_id"])
 
            if not check_password_hash(user["password_hash"], current_password):
                pw_error = "Current password is incorrect."
 
            elif len(new_password) < 6:
                pw_error = "New password must be at least 6 characters."
 
            elif new_password != confirm_password:
                pw_error = "New passwords do not match."
 
            else:
                new_hash = generate_password_hash(new_password)
                mysql_update_password(session["user_id"], new_hash)
                pw_success = "Password changed successfully."
 
        # ── Delete account ───────────────────────────────────────────────
        elif action == "delete":
            mysql_delete_user(session["user_id"])
            neo4j_delete_user(session["user_id"])
            session.clear()
            return redirect("/")
 
    user = mysql_get_user_by_id(session["user_id"])
    return render_template("profile.html",
                           user=user,
                           error=error,
                           success=success,
                           pw_error=pw_error,
                           pw_success=pw_success)
 
# ── Project: UPDATE name ─────────────────────────────
@app.route("/projects/<int:project_id>/edit", methods=["POST"])
def edit_project(project_id):
    if "user_id" not in session:
        return redirect("/login")

    new_name = request.form.get("project_name", "").strip()
    if new_name:
        # MySQL: UPDATE project name
        mysql_update_project(project_id, session["user_id"], new_name)

        # Neo4j: UPDATE Project node
        neo4j_update_project(project_id, new_name)

    return redirect("/projects")


# ── Project: DELETE ──────────────────────────────────
@app.route("/projects/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    if "user_id" not in session:
        return redirect("/login")

    # MySQL: DELETE project (cascades to submissions + opt runs)
    mysql_delete_project(project_id, session["user_id"])

    # Neo4j: DETACH DELETE project node
    neo4j_delete_project(project_id)

    return redirect("/projects")


# ── Submission: DELETE ───────────────────────────────
@app.route("/submissions/<int:project_id>/delete/<int:submission_id>", methods=["POST"])
def delete_submission(project_id, submission_id):
    if "user_id" not in session:
        return redirect("/login")

    # MySQL: DELETE submission (cascades to opt runs)
    mysql_delete_submission(submission_id, project_id)

    # MongoDB: DELETE all logs for this submission
    mongo_delete_execution_logs_for_submission(submission_id)
    mongo_delete_optimization_logs_for_submission(submission_id)

    # Neo4j: DETACH DELETE submission node
    neo4j_delete_submission(submission_id)

    return redirect(f"/submissions/{project_id}")


# ── Execution Logs: DELETE from MongoDB ──────────────
@app.route("/logs/<int:submission_id>/delete", methods=["POST"])
def delete_logs(submission_id):
    if "user_id" not in session:
        return redirect("/login")

    log_type = request.form.get("log_type", "all")

    if log_type in ("exec", "all"):
        mongo_delete_execution_logs_for_submission(submission_id)
    if log_type in ("opt", "all"):
        mongo_delete_optimization_logs_for_submission(submission_id)

    return redirect(f"/logs/{submission_id}")


# ======================================================
# NEO4J ADVANCED FEATURE ROUTES
# ======================================================

# ── Feature 1: Best Optimization Finder ──────────────
@app.route("/best_opt/<int:submission_id>")
def best_opt(submission_id):
    if "user_id" not in session:
        return redirect("/login")
    submission = mysql_get_submission(submission_id)
    if not submission:
        return "Submission not found", 404

    project = mysql_get_project(submission["project_id"], session["user_id"])
    
    runs       = neo4j_get_best_opt(submission_id)
    best       = runs[0] if runs else None

    return render_template("best_opt.html",
                           submission=submission,
                           runs=runs,
                           best=best,
                           project=project)


@app.route("/best_opt/project/<int:project_id>")
def best_opt_project(project_id):
    if "user_id" not in session:
        return redirect("/login")

    project = mysql_get_project(project_id, session["user_id"])
    summary = neo4j_get_best_opt_across_project(project_id)

    return render_template("best_opt_project.html",
                           project=project,
                           summary=summary)


# ── Feature 2: Graph Analytics ───────────────────────
@app.route("/graph/analytics")
def graph_analytics():
    if "user_id" not in session:
        return redirect("/login")

    analytics = neo4j_get_graph_analytics()    
    popular = neo4j_get_popular_profiles_globally()

    return render_template("graph_analytics.html",
                           analytics=analytics,
                           popular=popular)


# ── Feature 3: Similar Submissions ───────────────────
@app.route("/similar/<int:submission_id>")
def similar(submission_id):
    if "user_id" not in session:
        return redirect("/login")

    submission = mysql_get_submission(submission_id)
    similars   = neo4j_get_similar_submissions(submission_id)

    return render_template("similar.html",
                           submission=submission,
                           similars=similars)


# ── Feature 4: Evolution Tracking ────────────────────
@app.route("/evolution/<int:project_id>")
def evolution(project_id):
    if "user_id" not in session:
        return redirect("/login")

    project = mysql_get_project(project_id, session["user_id"])
    path    = neo4j_get_evolution_path(project_id)

    return render_template("evolution.html",
                           project=project,
                           path=path)
 
if __name__ == "__main__":
    app.run(debug=True)