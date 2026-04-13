import subprocess
import tempfile
import time
import os
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

# ── DB operation modules ──
from mysql_ops import (
    mysql_register_user, mysql_get_user_by_email, mysql_get_user_by_id,
    mysql_get_user_id_by_email, mysql_get_dashboard_stats,
    mysql_create_project, mysql_get_projects_by_user, mysql_get_project,
    mysql_create_submission, mysql_get_submissions_by_project,
    mysql_get_submission, mysql_update_last_output,
    mysql_get_optimization_profiles, mysql_get_optimization_profile,
    mysql_save_optimization_run,
    mysql_update_user, mysql_delete_user,
    mysql_update_project, mysql_delete_project,
    mysql_delete_submission,
    mysql_log_execution_error, mysql_get_error_logs,
    ERROR_COMPILE, ERROR_RUNTIME, ERROR_TIMEOUT, EXEC_TIMEOUT_MS
)
from mongodb_ops import (
    mongo_insert_execution_log, mongo_insert_optimization_log,
    mongo_get_execution_logs, mongo_get_optimization_logs,
    mongo_avg_exec_time_by_language, mongo_avg_metrics_by_opt_flag,
    mongo_total_execution_logs, mongo_total_optimization_logs,
    mongo_delete_execution_logs_for_submission,
    mongo_delete_optimization_logs_for_submission
)
from neo4j_ops import (
    # existing
    neo4j_create_user, neo4j_create_project, neo4j_create_submission,
    neo4j_create_opt_run, neo4j_get_user_graph, neo4j_get_submission_runs,
    neo4j_update_user, neo4j_update_project,
    neo4j_delete_user, neo4j_delete_project, neo4j_delete_submission,
    # Feature 1 — Best Opt
    neo4j_get_best_opt, neo4j_get_best_opt_across_project,
    # Feature 2 — Recommendations
    neo4j_record_user_used_profile, neo4j_get_recommendations_for_user,
    neo4j_get_popular_profiles_globally,
    # Feature 3 — Similar Submissions
    neo4j_detect_and_link_similar, neo4j_get_similar_submissions,
    neo4j_update_submission_run_stats,
    # Feature 4 — Evolution
    neo4j_link_evolution_on_new_submission, neo4j_get_evolution_path,
    # Feature 5 — Graph Analytics
    neo4j_get_graph_analytics
)

PYTHON_PATH = r"C:\Users\swarna\AppData\Local\Programs\Python\Python314\python.exe"
GCC_PATH    = r"C:\msys64\ucrt64\bin\gcc.exe"
GPP_PATH    = r"C:\msys64\ucrt64\bin\g++.exe"

# Binary output directory — must be outside AppLocker-blocked temp folders
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
BINARY_PATH = os.path.join(BASE_DIR, "compiled_output.exe")

# ==============================
# 1. NORMAL EXECUTION
# ==============================
def execute_code(language, code):

    with tempfile.TemporaryDirectory() as temp_dir:
        source_file = os.path.join(temp_dir, "code")

        # Choose filename extension
        if language == "c":
            source_file += ".c"
        elif language == "cpp":
            source_file += ".cpp"
        else:
            source_file += ".py"

        # Write code into file
        with open(source_file, "w", encoding="utf-8") as f:
            f.write(code)

        # ================
        # PYTHON EXECUTION
        # ================
        if language == "python":
            start = time.time()

            try:
                proc = subprocess.run(
                    [PYTHON_PATH, source_file],
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

        # ==================
        # C/C++ COMPILATION
        # ==================
        compiler = GCC_PATH if language == "c" else GPP_PATH

        compile_proc = subprocess.run(
            [compiler, source_file, "-o", BINARY_PATH],
            capture_output=True,
            text=True
        )

        # Compilation failed
        if compile_proc.returncode != 0:
            output = compile_proc.stderr
            return output, 0, 0, compile_proc.returncode

        # Compilation success → Run executable
        start = time.time()

        try:
            run_proc = subprocess.run(
                [BINARY_PATH],
                capture_output=True,
                text=True,
                timeout=30
            )
            output = run_proc.stdout + run_proc.stderr

        except subprocess.TimeoutExpired:
            output   = "Execution timed out (30s limit)"
            run_proc = None

        end = time.time()
        exec_time   = round((end - start) * 1000)
        file_size   = round(os.path.getsize(BINARY_PATH) / 1024, 2) if os.path.exists(BINARY_PATH) else 0
        return_code = run_proc.returncode if run_proc else -1

        try: os.remove(BINARY_PATH)
        except: pass

        return output, exec_time, file_size, return_code

# ==============================
# 2. EXECUTION WITH OPTIMIZATION
# ==============================
def execute_code_with_opt(language, code, opt_flag):

    with tempfile.TemporaryDirectory() as temp_dir:
        source_file = os.path.join(temp_dir, f"code.{ 'c' if language=='c' else 'cpp'}")
        # Write code to file
        with open(source_file, "w", encoding="utf-8") as f:
            f.write(code)

        if language == "python":
            return (
                "Optimizations do not apply to Python.",
                0, 0, 0, "N/A"
            )

        # Choose compiler
        compiler = GCC_PATH if language == "c" else GPP_PATH

        # ======================
        # COMPILE WITH OPT FLAG
        # ======================
        compile_proc = subprocess.run(
            [compiler, source_file, opt_flag, "-o", BINARY_PATH],
            capture_output=True,
            text=True
        )

        compiler_output = compile_proc.stdout + compile_proc.stderr

        if compile_proc.returncode != 0:
            return compiler_output, 0, 0, compile_proc.returncode, compiler_output

        # ===============
        # RUN EXECUTABLE
        # ===============

        start = time.time()

        try:
            run_proc = subprocess.run(
                [BINARY_PATH],
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

        return (
            output,
            exec_time,
            file_size,
            return_code,
            compiler_output
        )


app = Flask(__name__)
app.secret_key = "a1f9d2e0c1b4841289abff22f7cab91a3b48bbdd"

@app.route("/")
def index():
    return render_template("home.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        # MySQL: register via stored procedure
        result = mysql_register_user(name, email, hashed_password)

        if result == "EMAIL_EXISTS":
            return "Email already registered!"

        # Neo4j: create User node
        new_user_id = mysql_get_user_id_by_email(email)
        neo4j_create_user(new_user_id, name, email)

        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # MySQL: fetch user by email
        user = mysql_get_user_by_email(email)

        if not user or not check_password_hash(user["password_hash"], password):
            return "Invalid credentials!"

        session["user_id"]   = user["user_id"]
        session["user_name"] = user["name"]
        return redirect("/dashboard")

    return render_template("login.html")

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


@app.route("/submissions/<int:project_id>", methods=["GET", "POST"])
def submissions(project_id):

    if "user_id" not in session:
        return redirect("/login")

    # POST — Create New Submission
    if request.method == "POST":
        sub_name    = request.form.get("submission_name", "").strip() or None
        language    = request.form.get("language")
        if not language:
            return "Language is required!"

        code_file   = request.files.get("code_file")
        code_text   = request.form.get("code_text", "").strip()
        if code_file and code_file.filename != "":
            source_code = code_file.read().decode("utf-8")
        elif code_text:
            source_code = code_text
        else:
            return "You must upload a code file OR paste code."

        input_file  = request.files.get("input_file")
        input_text  = request.form.get("input_text", "").strip()
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

        # Neo4j Feature 4: evolution linking in background
        import threading
        threading.Thread(
            target=neo4j_link_evolution_on_new_submission,
            args=(project_id, new_sid, language),
            kwargs={"exec_time_ms": None},
            daemon=True
        ).start()

        return redirect(f"/submissions/{project_id}")

    # GET — load project, submissions, selected
    project = mysql_get_project(project_id, session["user_id"])
    if not project:
        return "Project not found or access denied."

    submissions = mysql_get_submissions_by_project(project_id)
    selected    = None
    if "view" in request.args:
        selected = mysql_get_submission(request.args.get("view"), project_id)

    return render_template(
        "submissions.html",
        project=project,
        submissions=submissions,
        selected=selected
    )


@app.route("/run/<int:submission_id>")
def run_submission(submission_id):

    submission = mysql_get_submission(submission_id)

    output, exec_time, file_size, return_code = execute_code(
        submission["language"], submission["source_code"]
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
        submission["language"], submission["source_code"], opt_flag
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
@app.route("/logs/<int:submission_id>")
def logs(submission_id):
    if "user_id" not in session:
        return redirect("/login")

    submission = mysql_get_submission(submission_id)
    if not submission:
        return "Submission not found."

    # MongoDB: READ all logs for this submission
    exec_logs  = mongo_get_execution_logs(submission_id)
    opt_logs   = mongo_get_optimization_logs(submission_id)

    # MySQL: READ execution error logs
    error_logs = mysql_get_error_logs(submission_id)

    return render_template("logs.html",
                           submission=submission,
                           exec_logs=exec_logs,
                           opt_logs=opt_logs,
                           error_logs=error_logs)


@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect("/login")

    # MongoDB: READ aggregations
    lang_stats = mongo_avg_exec_time_by_language()
    opt_stats  = mongo_avg_metrics_by_opt_flag()
    best_opt   = opt_stats[0]["_id"] if opt_stats else "N/A"
    total_exec = mongo_total_execution_logs()
    total_opt  = mongo_total_optimization_logs()

    return render_template("analytics.html",
                           lang_stats=lang_stats,
                           opt_stats=opt_stats,
                           best_opt=best_opt,
                           total_exec=total_exec,
                           total_opt=total_opt)


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

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update":
            name  = request.form["name"].strip()
            email = request.form["email"].strip()

            # Check email not taken by another user
            existing = mysql_get_user_by_email(email)
            if existing and existing["user_id"] != session["user_id"]:
                user = mysql_get_user_by_id(session["user_id"])
                return render_template("profile.html", user=user,
                                       error="That email is already in use.")

            # MySQL: UPDATE user
            mysql_update_user(session["user_id"], name, email)
            session["user_name"] = name

            # Neo4j: UPDATE User node
            neo4j_update_user(session["user_id"], name, email)

        elif action == "delete":
            # MySQL: DELETE user (cascades to projects/submissions)
            mysql_delete_user(session["user_id"])

            # Neo4j: DELETE User node + all relationships
            neo4j_delete_user(session["user_id"])

            session.clear()
            return redirect("/")

    user = mysql_get_user_by_id(session["user_id"])
    return render_template("profile.html", user=user, error=None)


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
    runs       = neo4j_get_best_opt(submission_id)
    best       = runs[0] if runs else None

    return render_template("best_opt.html",
                           submission=submission,
                           runs=runs,
                           best=best)


@app.route("/best_opt/project/<int:project_id>")
def best_opt_project(project_id):
    if "user_id" not in session:
        return redirect("/login")

    project = mysql_get_project(project_id, session["user_id"])
    summary = neo4j_get_best_opt_across_project(project_id)

    return render_template("best_opt_project.html",
                           project=project,
                           summary=summary)


# ── Feature 2: Recommendations ───────────────────────
@app.route("/recommendations")
def recommendations():
    if "user_id" not in session:
        return redirect("/login")

    recs    = neo4j_get_recommendations_for_user(session["user_id"])
    popular = neo4j_get_popular_profiles_globally()

    return render_template("recommendations.html",
                           recommendations=recs,
                           popular=popular,
                           user_name=session.get("user_name"))


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


# ── Feature 5: Graph Analytics ───────────────────────
@app.route("/graph/analytics")
def graph_analytics():
    if "user_id" not in session:
        return redirect("/login")

    analytics = neo4j_get_graph_analytics()

    return render_template("graph_analytics.html",
                           analytics=analytics)

if __name__ == "__main__":
    app.run(debug=True)