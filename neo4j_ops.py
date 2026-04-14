# ============================================================
#  neo4j_ops.py
#  All Neo4j graph operations for CodeOpt
#  Each function opens a session, runs its query, and closes.
# ============================================================

from db import get_neo4j_driver
from datetime import datetime

# ────────────────────────────────────────────────────────────
# 1. CREATE User node
#    Called after successful registration
# ────────────────────────────────────────────────────────────
def neo4j_create_user(user_id, name, email):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MERGE (u:User {user_id: $user_id})
            SET u.name  = $name,
                u.email = $email
        """, user_id=user_id, name=name, email=email)
    driver.close()


# ────────────────────────────────────────────────────────────
# 2. CREATE Project node + (User)-[:OWNS]->(Project)
#    Called after project is inserted into MySQL
# ────────────────────────────────────────────────────────────
def neo4j_create_project(user_id, project_id, project_name, created_at=None):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MERGE (u:User {user_id: $user_id})

            MERGE (p:Project {project_id: $project_id})
            SET p.project_name = $project_name

            MERGE (u)-[r:OWNS]->(p)
            SET r.created_at = $created_at
        """,
        user_id=user_id,
        project_id=project_id,
        project_name=project_name,
        created_at=str(created_at or datetime.utcnow()))
    driver.close()


# ────────────────────────────────────────────────────────────
# 3. CREATE Submission node + (Project)-[:HAS_SUBMISSION]->(Submission)
#    Called after submission is inserted into MySQL
# ────────────────────────────────────────────────────────────
def neo4j_create_submission(project_id, submission_id,
                             submission_name, language, submitted_at=None):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MERGE (p:Project {project_id: $project_id})

            MERGE (s:Submission {submission_id: $submission_id})
            SET s.submission_name = $submission_name,
                s.language        = $language

            MERGE (p)-[r:HAS_SUBMISSION]->(s)
            SET r.submitted_at = $submitted_at
        """,
        project_id=project_id,
        submission_id=submission_id,
        submission_name=submission_name,
        language=language,
        submitted_at=str(submitted_at or datetime.utcnow()))
    driver.close()


# ────────────────────────────────────────────────────────────
# 4. CREATE OptimizationProfile node + (Submission)-[:RAN_WITH]->(Profile)
#    Called after every optimized run
# ────────────────────────────────────────────────────────────
def neo4j_create_opt_run(submission_id, profile_id,
                          profile_name, compiler_flags,
                          exec_time_ms, file_size_kb, return_code):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MERGE (s:Submission {submission_id: $submission_id})

            MERGE (op:OptimizationProfile {profile_id: $profile_id})
            SET op.profile_name    = $profile_name,
                op.compiler_flags  = $compiler_flags

            CREATE (s)-[r:RAN_WITH]->(op)
            SET r.exec_time_ms  = $exec_time_ms,
                r.file_size_kb  = $file_size_kb,
                r.return_code   = $return_code,
                r.ran_at        = $ran_at
        """,
        submission_id=submission_id,
        profile_id=profile_id,
        profile_name=profile_name,
        compiler_flags=compiler_flags,
        exec_time_ms=exec_time_ms,
        file_size_kb=file_size_kb,
        return_code=return_code,
        ran_at=str(datetime.utcnow()))
    driver.close()


# ────────────────────────────────────────────────────────────
# 5. QUERY full graph for a user
#    Returns list of paths: user → project → submission → profile
# ────────────────────────────────────────────────────────────
def neo4j_get_user_graph(user_id):
    driver = get_neo4j_driver()
    results = []

    with driver.session() as session:
        records = session.run("""
            MATCH (u:User {user_id: $user_id})-[:OWNS]->(p:Project)
                  -[:HAS_SUBMISSION]->(s:Submission)
            OPTIONAL MATCH (s)-[r:RAN_WITH]->(op:OptimizationProfile)
            RETURN
                u.user_id       AS user_id,
                u.name          AS user_name,
                p.project_id    AS project_id,
                p.project_name  AS project_name,
                s.submission_id AS submission_id,
                s.submission_name AS submission_name,
                s.language      AS language,
                op.profile_name AS profile_name,
                op.compiler_flags AS compiler_flags,
                r.exec_time_ms  AS exec_time_ms,
                r.file_size_kb  AS file_size_kb,
                r.ran_at        AS ran_at
            ORDER BY p.project_id, s.submission_id
        """, user_id=user_id)

        for rec in records:
            results.append(dict(rec))

    driver.close()
    return results


# ────────────────────────────────────────────────────────────
# 6. QUERY — get all optimization runs for a submission
#    Used to compare -O0 vs -O1 vs -O2 vs -O3 side by side
# ────────────────────────────────────────────────────────────
def neo4j_get_submission_runs(submission_id):
    driver = get_neo4j_driver()
    results = []

    with driver.session() as session:
        records = session.run("""
            MATCH (s:Submission {submission_id: $submission_id})
                  -[r:RAN_WITH]->(op:OptimizationProfile)
            RETURN
                op.profile_name   AS profile_name,
                op.compiler_flags AS compiler_flags,
                r.exec_time_ms    AS exec_time_ms,
                r.file_size_kb    AS file_size_kb,
                r.return_code     AS return_code,
                r.ran_at          AS ran_at
            ORDER BY r.ran_at DESC
        """, submission_id=submission_id)

        for rec in records:
            results.append(dict(rec))

    driver.close()
    return results


# ────────────────────────────────────────────────────────────
# 7. UPDATE User node properties
# ────────────────────────────────────────────────────────────
def neo4j_update_user(user_id, name, email):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MATCH (u:User {user_id: $user_id})
            SET u.name  = $name,
                u.email = $email
        """, user_id=user_id, name=name, email=email)
    driver.close()


# ────────────────────────────────────────────────────────────
# 8. UPDATE Project node name
# ────────────────────────────────────────────────────────────
def neo4j_update_project(project_id, new_name):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MATCH (p:Project {project_id: $project_id})
            SET p.project_name = $new_name
        """, project_id=project_id, new_name=new_name)
    driver.close()


# ────────────────────────────────────────────────────────────
# 9. UPDATE Submission node name/language
# ────────────────────────────────────────────────────────────
def neo4j_update_submission(submission_id, submission_name, language):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MATCH (s:Submission {submission_id: $submission_id})
            SET s.submission_name = $submission_name,
                s.language        = $language
        """, submission_id=submission_id,
             submission_name=submission_name,
             language=language)
    driver.close()


# ────────────────────────────────────────────────────────────
# 10. DELETE User node + all connected relationships
# ────────────────────────────────────────────────────────────
def neo4j_delete_user(user_id):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MATCH (u:User {user_id: $user_id})
            DETACH DELETE u
        """, user_id=user_id)
    driver.close()


# ────────────────────────────────────────────────────────────
# 11. DELETE Project node + all connected relationships
# ────────────────────────────────────────────────────────────
def neo4j_delete_project(project_id):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MATCH (p:Project {project_id: $project_id})
            DETACH DELETE p
        """, project_id=project_id)
    driver.close()


# ────────────────────────────────────────────────────────────
# 12. DELETE Submission node + all its RAN_WITH relationships
# ────────────────────────────────────────────────────────────
def neo4j_delete_submission(submission_id):
    driver = get_neo4j_driver()
    with driver.session() as session:
        session.run("""
            MATCH (s:Submission {submission_id: $submission_id})
            DETACH DELETE s
        """, submission_id=submission_id)
    driver.close()


# ============================================================
# FEATURE 1 — BEST OPTIMIZATION FINDER
# ============================================================

def neo4j_get_best_opt(submission_id):
    """
    Query RAN_WITH relationships for a submission and return
    the optimization profile with the lowest exec_time_ms.
    Also returns all runs ranked by time for comparison.
    """
    driver = get_neo4j_driver()
    results = []
    with driver.session() as s:
        records = s.run("""
            MATCH (sub:Submission {submission_id: $sid})-[r:RAN_WITH]->(op:OptimizationProfile)
            WHERE r.exec_time_ms IS NOT NULL AND r.exec_time_ms > 0
            RETURN
                op.profile_name   AS profile_name,
                op.compiler_flags AS compiler_flags,
                r.exec_time_ms    AS exec_time_ms,
                r.file_size_kb    AS file_size_kb,
                r.return_code     AS return_code,
                r.ran_at          AS ran_at
            ORDER BY r.exec_time_ms ASC
        """, sid=submission_id)
        for rec in records:
            results.append(dict(rec))
    driver.close()
    return results


def neo4j_get_best_opt_across_project(project_id):
    """
    For each submission in a project, find the best optimization flag.
    Returns per-submission best flag summary.
    """
    driver = get_neo4j_driver()
    results = []
    with driver.session() as s:
        records = s.run("""
            MATCH (p:Project {project_id: $pid})-[:HAS_SUBMISSION]->(sub:Submission)
                  -[r:RAN_WITH]->(op:OptimizationProfile)
            WHERE r.exec_time_ms IS NOT NULL AND r.exec_time_ms > 0
            WITH sub, op, r
            ORDER BY r.exec_time_ms ASC
            WITH sub, collect({
                flag:  op.compiler_flags,
                name:  op.profile_name,
                time:  r.exec_time_ms,
                size:  r.file_size_kb
            })[0] AS best
            RETURN
                sub.submission_id   AS submission_id,
                sub.submission_name AS submission_name,
                sub.language        AS language,
                best.flag           AS best_flag,
                best.name           AS best_profile,
                best.time           AS best_time_ms,
                best.size           AS best_size_kb
            ORDER BY sub.submission_id
        """, pid=project_id)
        for rec in records:
            results.append(dict(rec))
    driver.close()
    return results


# ============================================================
# FEATURE 2 — GRAPH-BASED ANALYTICS
# ============================================================

def neo4j_get_graph_analytics():
    """
    Multi-level aggregation across all users and submissions:
    - Avg exec time per optimization profile (global)
    - Which profile is most popular across users
    - Language distribution across all submissions
    - Most active users by submission count
    - Users sharing similar submissions (cross-user links)
    """
    driver  = get_neo4j_driver()
    results = {}

    with driver.session() as s:

        # 1. Avg exec time per opt profile (global, across all users)
        r1 = s.run("""
            MATCH ()-[r:RAN_WITH]->(op:OptimizationProfile)
            WHERE r.exec_time_ms IS NOT NULL AND r.exec_time_ms > 0
            RETURN
                op.compiler_flags AS flag,
                op.profile_name   AS profile_name,
                avg(r.exec_time_ms)  AS avg_time_ms,
                avg(r.file_size_kb)  AS avg_size_kb,
                count(r)             AS total_runs
            ORDER BY avg_time_ms ASC
        """)
        results["opt_performance"] = [dict(rec) for rec in r1]

        # 2. Most popular opt profiles (by user count)
        r2 = s.run("""
            MATCH (u:User)-[r:USED]->(op:OptimizationProfile)
            RETURN
                op.compiler_flags AS flag,
                op.profile_name   AS profile_name,
                count(DISTINCT u) AS user_count,
                sum(r.use_count)  AS total_uses
            ORDER BY total_uses DESC
        """)
        results["popular_profiles"] = [dict(rec) for rec in r2]

        # 3. Language distribution across ALL submissions
        r3 = s.run("""
            MATCH (s:Submission)
            WHERE s.language IS NOT NULL
            RETURN s.language AS language, count(s) AS count
            ORDER BY count DESC
        """)
        results["language_dist"] = [dict(rec) for rec in r3]

        # 4. Most active users (by submission count)
        r4 = s.run("""
            MATCH (u:User)-[:OWNS]->(:Project)-[:HAS_SUBMISSION]->(s:Submission)
            RETURN
                u.user_id AS user_id,
                u.name    AS name,
                count(s)  AS submission_count
            ORDER BY submission_count DESC
            LIMIT 10
        """)
        results["active_users"] = [dict(rec) for rec in r4]

        # 5. Cross-user similarity connections
        r5 = s.run("""
            MATCH (u1:User)-[:OWNS]->(:Project)-[:HAS_SUBMISSION]->
                  (s1:Submission)-[sim:SIMILAR_TO]->(s2:Submission)
                  <-[:HAS_SUBMISSION]-(:Project)<-[:OWNS]-(u2:User)
            WHERE u1.user_id <> u2.user_id
            RETURN
                u1.name AS user1,
                u2.name AS user2,
                count(sim) AS shared_similar_submissions,
                avg(sim.score) AS avg_similarity
            ORDER BY shared_similar_submissions DESC
            LIMIT 10
        """)
        results["user_connections"] = [dict(rec) for rec in r5]

    driver.close()
    return results

def neo4j_record_user_used_profile(user_id, profile_id,
                                    profile_name, compiler_flags):
    """
    CREATE/MERGE (User)-[:USED]->(OptimizationProfile)
    Called after every optimized run.
    Increments use_count on the relationship.
    """
    driver = get_neo4j_driver()
    with driver.session() as s:
        s.run("""
            MERGE (u:User {user_id: $uid})
            MERGE (op:OptimizationProfile {profile_id: $pid})
            SET op.profile_name   = $pname,
                op.compiler_flags = $flags

            MERGE (u)-[r:USED]->(op)
            ON CREATE SET r.use_count = 1,
                          r.first_used = $now
            ON MATCH  SET r.use_count = r.use_count + 1
            SET r.last_used = $now
        """,
        uid=user_id, pid=profile_id,
        pname=profile_name, flags=compiler_flags,
        now=str(datetime.utcnow()))
    driver.close()

def neo4j_get_popular_profiles_globally():
    """
    Fallback: most used profiles across ALL users.
    Shown when no similar submissions exist yet.
    """
    driver = get_neo4j_driver()
    results = []
    with driver.session() as s:
        records = s.run("""
            MATCH (u:User)-[r:USED]->(op:OptimizationProfile)
            RETURN
                op.profile_name   AS profile_name,
                op.compiler_flags AS compiler_flags,
                count(DISTINCT u) AS user_count,
                sum(r.use_count)  AS total_uses
            ORDER BY total_uses DESC
            LIMIT 5
        """)
        for rec in records:
            results.append(dict(rec))
    driver.close()
    return results


# ============================================================
# FEATURE 3 — SIMILAR SUBMISSIONS DETECTION
# ============================================================

def neo4j_create_similar_link(submission_id_1, submission_id_2,
                               score, reason):
    """
    MERGE (s1)-[:SIMILAR_TO {score, reason}]->(s2)
    score: float 0.0 - 1.0
    reason: e.g. 'same_language+similar_output'
    """
    driver = get_neo4j_driver()
    with driver.session() as s:
        s.run("""
            MATCH (s1:Submission {submission_id: $sid1})
            MATCH (s2:Submission {submission_id: $sid2})
            MERGE (s1)-[r:SIMILAR_TO]->(s2)
            SET r.score  = $score,
                r.reason = $reason,
                r.linked_at = $now
        """,
        sid1=submission_id_1, sid2=submission_id_2,
        score=score, reason=reason,
        now=str(datetime.utcnow()))
    driver.close()


def neo4j_get_similar_submissions(submission_id):
    """
    Find all submissions SIMILAR_TO the given one,
    including who owns them — cross-user view.
    """
    driver = get_neo4j_driver()
    results = []
    with driver.session() as s:
        records = s.run("""
            MATCH (s:Submission {submission_id: $sid})
                  -[r:SIMILAR_TO]->(other:Submission)
                  <-[:HAS_SUBMISSION]-(:Project)<-[:OWNS]-(owner:User)
            RETURN
                other.submission_id   AS submission_id,
                other.submission_name AS submission_name,
                other.language        AS language,
                owner.name            AS owner_name,
                r.score               AS similarity_score,
                r.reason              AS reason
            ORDER BY r.score DESC
        """, sid=submission_id)
        for rec in records:
            results.append(dict(rec))
    driver.close()
    return results


def neo4j_detect_and_link_similar(new_submission_id,
                                   new_language, new_output,
                                   new_exec_time):
    """
    After a submission is run, compare it to all other submissions
    in Neo4j. If similarity score > 0.5 → create SIMILAR_TO link.

    Similarity scored on:
      - same language:         +0.4
      - similar output length: +0.3 (within 20%)
      - similar exec time:     +0.3 (within 30%)
    """
    driver = get_neo4j_driver()
    candidates = []

    with driver.session() as s:
        # Fetch all other submissions with run data
        records = s.run("""
            MATCH (s:Submission)
            WHERE s.submission_id <> $sid
            AND   s.language IS NOT NULL
            RETURN s.submission_id AS sid,
                   s.language      AS language,
                   s.last_output   AS last_output,
                   s.last_exec_ms  AS last_exec_ms
        """, sid=new_submission_id)
        for rec in records:
            candidates.append(dict(rec))

    links_created = 0
    new_out_len   = len(new_output or "")

    for c in candidates:
        score  = 0.0
        reasons = []

        # Language match
        if c["language"] == new_language:
            score += 0.4
            reasons.append("same_language")

        # Output length similarity
        c_out_len = len(c.get("last_output") or "")
        if new_out_len > 0 and c_out_len > 0:
            ratio = min(new_out_len, c_out_len) / max(new_out_len, c_out_len)
            if ratio >= 0.8:
                score += 0.3
                reasons.append("similar_output")

        # Exec time similarity
        c_time = c.get("last_exec_ms") or 0
        if new_exec_time and new_exec_time > 0 and c_time > 0:
            t_ratio = min(new_exec_time, c_time) / max(new_exec_time, c_time)
            if t_ratio >= 0.7:
                score += 0.3
                reasons.append("similar_runtime")

        if score >= 0.5:
            neo4j_create_similar_link(
                new_submission_id, c["sid"],
                round(score, 2), "+".join(reasons)
            )
            links_created += 1

    driver.close()
    return links_created


def neo4j_update_submission_run_stats(submission_id, output, exec_time_ms):
    """
    Store last_output and last_exec_ms on Submission node
    so similarity detection can use them.
    """
    driver = get_neo4j_driver()
    with driver.session() as s:
        s.run("""
            MATCH (s:Submission {submission_id: $sid})
            SET s.last_output  = $output,
                s.last_exec_ms = $exec_ms
        """, sid=submission_id, output=output, exec_ms=exec_time_ms)
    driver.close()


# ============================================================
# FEATURE 4 — PERFORMANCE EVOLUTION TRACKING
# ============================================================

def neo4j_create_evolution_link(from_submission_id, to_submission_id,
                                 improvement_ms=None):
    """
    CREATE (s1)-[:EVOLVED_TO {improvement_ms, linked_at}]->(s2)
    Called when a new submission is added to a project that
    already has submissions (same language).
    improvement_ms: positive = got faster, negative = got slower
    """
    driver = get_neo4j_driver()
    with driver.session() as s:
        s.run("""
            MATCH (s1:Submission {submission_id: $sid1})
            MATCH (s2:Submission {submission_id: $sid2})
            MERGE (s1)-[r:EVOLVED_TO]->(s2)
            SET r.improvement_ms = $improvement,
                r.linked_at      = $now
        """,
        sid1=from_submission_id, sid2=to_submission_id,
        improvement=improvement_ms,
        now=str(datetime.utcnow()))
    driver.close()


def neo4j_get_evolution_path(project_id, language=None):
    """
    Trace the full EVOLVED_TO chain for a project.
    Optionally filter by language.
    Returns ordered list of submissions with improvement deltas.
    """
    driver = get_neo4j_driver()
    results = []
    with driver.session() as s:
        query = """
            MATCH path = (start:Submission)-[:EVOLVED_TO*]->(end:Submission)
            WHERE (start:Submission)<-[:HAS_SUBMISSION]-(:Project {project_id: $pid})
            AND NOT ()-[:EVOLVED_TO]->(start)
        """
        if language:
            query += " AND start.language = $lang "
        query += """
            WITH nodes(path) AS submissions, relationships(path) AS evolutions
            UNWIND range(0, size(submissions)-1) AS i
            RETURN
                submissions[i].submission_id   AS submission_id,
                submissions[i].submission_name AS submission_name,
                submissions[i].language        AS language,
                submissions[i].last_exec_ms    AS exec_ms,
                CASE WHEN i < size(evolutions)
                     THEN evolutions[i].improvement_ms
                     ELSE null END             AS improvement_ms
            ORDER BY i
        """
        params = {"pid": project_id}
        if language:
            params["lang"] = language
        records = s.run(query, **params)
        for rec in records:
            results.append(dict(rec))
    driver.close()
    return results


def neo4j_link_evolution_on_new_submission(project_id, new_submission_id,
                                            language, new_exec_ms):
    """
    When a new submission is created, find the most recent previous
    submission in the same project with the same language and
    create an EVOLVED_TO link with the improvement delta.
    """
    driver = get_neo4j_driver()
    prev = None

    with driver.session() as s:
        record = s.run("""
            MATCH (p:Project {project_id: $pid})
                  -[:HAS_SUBMISSION]->(s:Submission)
            WHERE s.language = $lang
            AND   s.submission_id <> $new_sid
            AND   NOT (s)-[:EVOLVED_TO]->(:Submission)
            RETURN s.submission_id AS sid,
                   s.last_exec_ms  AS exec_ms
            ORDER BY s.submission_id DESC
            LIMIT 1
        """, pid=project_id, lang=language, new_sid=new_submission_id)
        row = record.single()
        if row:
            prev = dict(row)

    driver.close()

    if prev:
        prev_ms = prev.get("exec_ms") or 0
        improvement = (prev_ms - (new_exec_ms or 0)) if prev_ms and new_exec_ms else None
        neo4j_create_evolution_link(prev["sid"], new_submission_id, improvement)
        return prev["sid"]

    return None