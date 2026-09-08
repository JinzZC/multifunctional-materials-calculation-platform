"""Save immutable analysis snapshots; exports recalculate from saved inputs."""

from dataclasses import asdict
import json

from ..config import APP_VERSION
from .core import ALGORITHM_VERSION, Spec, analyze


def save_entries(conn, entries):
    ids = []
    # One batch is atomic; validation or SQL failure must not leave partial saves.
    with conn:
        for entry in entries:
            name = entry["name"].strip()
            if not name:
                raise ValueError("样品名称不能为空")
            result = analyze(entry["x"], entry["force"], entry["spec"])
            dump = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
            cur = conn.execute(
                "INSERT INTO mechanical_curves (sample_name,mode,source,spec_json,points_json,"
                "import_json,result_json,app_version,algorithm_version,remark,test_date) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (name, entry["spec"].mode, entry["spec"].source, dump(asdict(entry["spec"])),
                 dump([list(map(float, entry["x"])), list(map(float, entry["force"]))]),
                 dump(entry.get("import", {})), dump({k: v for k, v in asdict(result).items()
                     if k not in {"strain", "stress_mpa", "fit_indices"}}), APP_VERSION,
                 ALGORITHM_VERSION, entry.get("remark", ""), entry.get("test_date", "")))
            ids.append(cur.lastrowid)
    return ids


def list_entries(conn, keyword=""):
    return [dict(r) for r in conn.execute(
        "SELECT id,sample_name,mode,source,result_json,app_version,algorithm_version,test_date,remark "
        "FROM mechanical_curves WHERE mode='tensile' AND (sample_name LIKE ? OR remark LIKE ?) ORDER BY id DESC",
        (f"%{keyword}%", f"%{keyword}%"))]


def load_entry(conn, record_id):
    row = conn.execute("SELECT * FROM mechanical_curves WHERE id=?", (record_id,)).fetchone()
    if row is None:
        raise ValueError("记录不存在")
    x, force = json.loads(row["points_json"])
    if row["mode"] != "tensile":
        raise ValueError("通用力学曲线仅支持拉伸分析")
    parameters = json.loads(row["spec_json"])
    # Earlier development snapshots included unused geometry fields in tensile records.
    parameters.pop("span_mm", None)
    parameters.pop("load_span_mm", None)
    spec = Spec(**parameters)
    return {"name": row["sample_name"], "spec": spec, "x": x, "force": force,
            "result": analyze(x, force, spec), "import": json.loads(row["import_json"]),
            "remark": row["remark"], "test_date": row["test_date"], "saved_id": row["id"],
            "saved_app_version": row["app_version"], "saved_algorithm_version": row["algorithm_version"]}


def delete_entries(conn, ids):
    with conn:
        conn.executemany("DELETE FROM mechanical_curves WHERE id=?", [(i,) for i in ids])
