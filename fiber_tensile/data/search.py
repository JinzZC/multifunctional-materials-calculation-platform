"""跨功能域只读搜索。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    module: str
    title: str
    detail: str
    created_at: str
    module_index: int
    record_id: int


_QUERIES = (
    ("纤维拉伸强度", 0,
     "SELECT id, batch_name title, "
     "COALESCE(fiber_type,'') || CASE WHEN remark IS NULL OR remark='' THEN '' ELSE '；' || remark END detail, "
     "created_at FROM batches WHERE batch_name LIKE ? OR fiber_type LIKE ? OR remark LIKE ?"),
    ("接触角表面能", 1,
     "SELECT id, sample_name title, method || CASE WHEN remark IS NULL OR remark='' THEN '' ELSE '；' || remark END detail, "
     "created_at FROM se_measurements WHERE sample_name LIKE ? OR method LIKE ? OR remark LIKE ?"),
    ("单丝曲线", 0,
     "SELECT id, sample_name title, '曲线分析' || CASE WHEN remark IS NULL OR remark='' THEN '' ELSE '；' || remark END detail, "
     "created_at FROM fiber_curves WHERE sample_name LIKE ? OR remark LIKE ? OR test_date LIKE ?"),
    ("复合材料", 2,
     "SELECT id, sample_name title, calc_type || CASE WHEN remark IS NULL OR remark='' THEN '' ELSE '；' || remark END detail, "
     "created_at FROM cm_calcs WHERE sample_name LIKE ? OR calc_type LIKE ? OR remark LIKE ?"),
)


def search_all(conn: sqlite3.Connection, keyword: str, limit: int = 200) -> list[SearchResult]:
    """搜索四个数据库功能域，按创建时间倒序合并。"""
    text = keyword.strip()
    if not text:
        return []
    pattern = f"%{text}%"
    results: list[SearchResult] = []
    per_query = max(1, int(limit))
    for module, module_index, sql in _QUERIES:
        for row in conn.execute(sql + " ORDER BY created_at DESC LIMIT ?",
                                (pattern, pattern, pattern, per_query)):
            results.append(SearchResult(
                module, str(row["title"] or ""), str(row["detail"] or ""),
                str(row["created_at"] or ""), module_index, int(row["id"])))
    results.sort(key=lambda item: item.created_at, reverse=True)
    return results[:per_query]
