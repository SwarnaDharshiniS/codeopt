# ============================================================
#  mongodb_ops.py
#  All MongoDB operations for CodeOpt
#  Collections: execution_logs, optimization_logs
# ============================================================

from db import get_execution_logs_collection, get_optimization_logs_collection
from datetime import datetime
from bson import ObjectId

# ============================================================
# EXECUTION LOGS  (normal runs)
# ============================================================

def mongo_insert_execution_log(submission_id, project_id, language,
                                source_code, output, exec_time_ms,
                                file_size_kb, return_code):
    """CREATE — insert a normal execution log document."""
    doc = {
        "submission_id": submission_id,
        "project_id":    project_id,
        "language":      language,
        "source_code":   source_code,
        "output":        output,
        "exec_time_ms":  exec_time_ms,
        "file_size_kb":  file_size_kb,
        "return_code":   return_code,
        "ran_at":        datetime.utcnow()
    }
    result = get_execution_logs_collection().insert_one(doc)
    return str(result.inserted_id)


def mongo_get_execution_logs(submission_id):
    """READ — all execution logs for a submission, newest first."""
    return list(
        get_execution_logs_collection()
        .find({"submission_id": submission_id}, {"_id": 0})
        .sort("ran_at", -1)
    )

def mongo_delete_execution_logs_for_submission(submission_id):
    """DELETE — all execution logs for a submission."""
    result = get_execution_logs_collection().delete_many(
        {"submission_id": submission_id}
    )
    return result.deleted_count


# ============================================================
# OPTIMIZATION LOGS  (optimized runs)
# ============================================================

def mongo_insert_optimization_log(submission_id, project_id, profile_id,
                                   optimization_flag, language, source_code,
                                   output, compiler_diagnostics,
                                   exec_time_ms, file_size_kb, return_code):
    """CREATE — insert an optimization run log document."""
    doc = {
        "submission_id":        submission_id,
        "project_id":           project_id,
        "profile_id":           profile_id,
        "optimization_flag":    optimization_flag,
        "language":             language,
        "source_code":          source_code,
        "output":               output,
        "compiler_diagnostics": compiler_diagnostics,
        "exec_time_ms":         exec_time_ms,
        "file_size_kb":         file_size_kb,
        "return_code":          return_code,
        "ran_at":               datetime.utcnow()
    }
    result = get_optimization_logs_collection().insert_one(doc)
    return str(result.inserted_id)


def mongo_get_optimization_logs(submission_id):
    """READ — all optimization logs for a submission, newest first."""
    return list(
        get_optimization_logs_collection()
        .find({"submission_id": submission_id}, {"_id": 0})
        .sort("ran_at", -1)
    )

def mongo_delete_optimization_logs_for_submission(submission_id):
    """DELETE — all optimization logs for a submission."""
    result = get_optimization_logs_collection().delete_many(
        {"submission_id": submission_id}
    )
    return result.deleted_count

# ============================================================
# AGGREGATIONS  (analytics)
# ============================================================

def mongo_avg_exec_time_by_language():
    """READ — avg execution time per language from normal runs."""
    pipeline = [
        {"$group": {
            "_id":         "$language",
            "avg_time_ms": {"$avg": "$exec_time_ms"},
            "total_runs":  {"$sum": 1}
        }},
        {"$sort": {"avg_time_ms": 1}}
    ]
    return list(get_execution_logs_collection().aggregate(pipeline))


def mongo_avg_metrics_by_opt_flag():
    """READ — avg exec time and binary size per optimization flag."""
    pipeline = [
        {"$group": {
            "_id":         "$optimization_flag",
            "avg_time_ms": {"$avg": "$exec_time_ms"},
            "avg_size_kb": {"$avg": "$file_size_kb"},
            "total_runs":  {"$sum": 1}
        }},
        {"$sort": {"avg_time_ms": 1}}
    ]
    return list(get_optimization_logs_collection().aggregate(pipeline))


def mongo_total_execution_logs():
    """READ — total count of normal run logs."""
    return get_execution_logs_collection().count_documents({})


def mongo_total_optimization_logs():
    """READ — total count of optimization run logs."""
    return get_optimization_logs_collection().count_documents({})
 
def mongo_avg_exec_time_by_language_for_projects(project_ids):
    """READ — avg exec time per language, scoped to a list of project_ids."""
    pipeline = [
        {"$match": {"project_id": {"$in": project_ids}}},
        {"$group": {
            "_id":         "$language",
            "avg_time_ms": {"$avg": "$exec_time_ms"},
            "total_runs":  {"$sum": 1}
        }},
        {"$sort": {"avg_time_ms": 1}}
    ]
    return list(get_execution_logs_collection().aggregate(pipeline))
 
 
def mongo_avg_metrics_by_opt_flag_for_projects(project_ids):
    """READ — avg exec time + size per opt flag, scoped to a list of project_ids."""
    pipeline = [
        {"$match": {"project_id": {"$in": project_ids}}},
        {"$group": {
            "_id":         "$optimization_flag",
            "avg_time_ms": {"$avg": "$exec_time_ms"},
            "avg_size_kb": {"$avg": "$file_size_kb"},
            "total_runs":  {"$sum": 1}
        }},
        {"$sort": {"avg_time_ms": 1}}
    ]
    return list(get_optimization_logs_collection().aggregate(pipeline))
 
 
def mongo_total_execution_logs_for_projects(project_ids):
    """READ — total execution log count scoped to project_ids."""
    return get_execution_logs_collection().count_documents(
        {"project_id": {"$in": project_ids}}
    )
 
 
def mongo_total_optimization_logs_for_projects(project_ids):
    """READ — total optimization log count scoped to project_ids."""
    return get_optimization_logs_collection().count_documents(
        {"project_id": {"$in": project_ids}}
    )
 