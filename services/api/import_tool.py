"""CSV import helpers for the admin panel."""
from __future__ import annotations

import csv
import io
import json
import tempfile
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, Numeric, String, Table, Text, inspect, select
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.db import Base

IMPORT_DIR = Path(tempfile.gettempdir()) / "beacon_csv_imports"
IMPORT_DIR.mkdir(parents=True, exist_ok=True)

BLANK_MARKERS = {"", "null", "none", "n/a", "na", "-", "—"}
DELIMITER_CANDIDATES = [",", ";", "\t", "|"]
PREVIEW_SAMPLE_ROWS = 20
IMPORT_LOG_LIMIT = 250


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
def build_import_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for table in Base.metadata.sorted_tables:
        if table.name == "alembic_version":
            continue
        catalog.append(_table_descriptor(table))
    return catalog


def _table_descriptor(table: Table) -> dict[str, Any]:
    pk_cols = [col.name for col in table.primary_key.columns]
    unique_constraints = [
        [col.name for col in constraint.columns]
        for constraint in table.constraints
        if getattr(constraint, "columns", None) and len(getattr(constraint, "columns", [])) > 0 and getattr(constraint, "__class__", None).__name__ == "UniqueConstraint"
    ]
    columns = [
        {
            "name": col.name,
            "type": str(col.type),
            "nullable": bool(col.nullable),
            "primary_key": bool(col.primary_key),
            "unique": bool(col.unique),
            "foreign_key": next(iter(col.foreign_keys)).target_fullname if col.foreign_keys else None,
            "default": _describe_default(col),
        }
        for col in table.columns
    ]
    suggested_match_columns = _suggest_match_columns(table, pk_cols, unique_constraints)
    return {
        "name": table.name,
        "label": table.name.replace("_", " ").title(),
        "primary_key": pk_cols,
        "unique_constraints": unique_constraints,
        "suggested_match_columns": suggested_match_columns,
        "columns": columns,
    }


def _suggest_match_columns(table: Table, pk_cols: list[str], unique_constraints: list[list[str]]) -> list[str]:
    if pk_cols:
        return pk_cols
    for cols in unique_constraints:
        if cols:
            return cols
    # If no PK/unique exists, pick common identifiers when possible.
    candidates = [c.name for c in table.columns if c.name in {"id", "ticker", "email", "name", "code"}]
    return candidates[:1]


def _describe_default(col) -> Optional[str]:
    default = col.default
    if default is None:
        return None
    try:
        if default.is_scalar:
            return repr(default.arg)
        if default.is_callable:
            return getattr(default.arg, "__name__", str(default.arg))
    except Exception:
        pass
    return str(default)


# ---------------------------------------------------------------------------
# Preview persistence
# ---------------------------------------------------------------------------
def save_upload_preview(upload: UploadFile) -> dict[str, Any]:
    import_id = uuid.uuid4().hex
    path = IMPORT_DIR / f"{import_id}.csv"
    raw = upload.file.read()
    path.write_bytes(raw)
    return {
        "import_id": import_id,
        "filename": upload.filename or "upload.csv",
        "path": str(path),
        "size_bytes": len(raw),
        "created_at": datetime.utcnow().isoformat(),
    }


def build_preview(import_id: str, *, sample_rows: int = PREVIEW_SAMPLE_ROWS) -> dict[str, Any]:
    path = _import_path(import_id)
    text, encoding = _decode_file(path)
    delimiter = _detect_delimiter(text)
    rows, headers, row_count = _read_csv_preview(text, delimiter, sample_rows)
    return {
        "import_id": import_id,
        "filename": path.name,
        "encoding": encoding,
        "delimiter": delimiter,
        "row_count": row_count,
        "headers": headers,
        "sample_rows": rows,
    }


def _import_path(import_id: str) -> Path:
    path = IMPORT_DIR / f"{import_id}.csv"
    if not path.exists():
        raise HTTPException(404, "Import file not found or expired")
    return path


def _decode_file(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace"), "latin-1"


def _detect_delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=DELIMITER_CANDIDATES)
        return dialect.delimiter
    except Exception:
        return ","


def _read_csv_preview(text: str, delimiter: str, sample_rows: int) -> tuple[list[dict[str, Any]], list[str], int]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, skipinitialspace=True)
    headers = reader.fieldnames or []
    sample: list[dict[str, Any]] = []
    total = 0
    for line_no, row in enumerate(reader, start=2):
        if not _row_has_content(row):
            continue
        total += 1
        if len(sample) < sample_rows:
            sample.append({"row_number": line_no, "values": {h: row.get(h) for h in headers}})
    return sample, headers, total


def _row_has_content(row: dict[str, Any]) -> bool:
    for value in row.values():
        if value is not None and str(value).strip() != "":
            return True
    return False


# ---------------------------------------------------------------------------
# Import execution
# ---------------------------------------------------------------------------
def execute_import(
    db: Session,
    *,
    import_id: str,
    table_name: str,
    mode: str,
    column_mapping: dict[str, str],
    match_columns: list[str],
    ignore_blank_values: bool = True,
) -> dict[str, Any]:
    path = _import_path(import_id)
    table = _resolve_table(table_name)
    text, encoding = _decode_file(path)
    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, skipinitialspace=True)

    headers = reader.fieldnames or []
    _validate_mapping(table, headers, column_mapping)
    resolved_match_columns = _resolve_match_columns(table, match_columns)

    processed = inserted = updated = skipped = errors = 0
    row_logs: list[dict[str, Any]] = []

    with db.begin():
        for row_number, row in enumerate(reader, start=2):
            if not _row_has_content(row):
                continue
            processed += 1
            try:
                with db.begin_nested():
                    outcome = _apply_row(
                        db,
                        table,
                        row_number=row_number,
                        row=row,
                        mode=mode,
                        column_mapping=column_mapping,
                        match_columns=resolved_match_columns,
                        ignore_blank_values=ignore_blank_values,
                    )
                if outcome == "inserted":
                    inserted += 1
                    message = "Inserted"
                elif outcome == "updated":
                    updated += 1
                    message = "Updated"
                else:
                    skipped += 1
                    message = "Skipped"
                _append_log(row_logs, row_number, outcome, message)
            except Exception as exc:
                errors += 1
                _append_log(row_logs, row_number, "error", str(exc))
                if len(row_logs) >= IMPORT_LOG_LIMIT:
                    continue

    return {
        "import_id": import_id,
        "table_name": table_name,
        "mode": mode,
        "encoding": encoding,
        "delimiter": delimiter,
        "processed": processed,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "row_logs": row_logs[:IMPORT_LOG_LIMIT],
        "finished_at": datetime.utcnow(),
    }


def _append_log(logs: list[dict[str, Any]], row_number: int, action: str, message: str) -> None:
    if len(logs) >= IMPORT_LOG_LIMIT:
        return
    logs.append({"row_number": row_number, "action": action, "message": message})


def _resolve_table(table_name: str) -> Table:
    table = Base.metadata.tables.get(table_name)
    if table is None:
        raise HTTPException(404, f"Unknown table: {table_name}")
    return table


def _validate_mapping(table: Table, headers: list[str], column_mapping: dict[str, str]) -> None:
    if not column_mapping:
        raise HTTPException(400, "No column mapping provided")
    header_set = set(headers)
    table_columns = set(table.columns.keys())
    seen_db_cols: set[str] = set()
    for csv_col, db_col in column_mapping.items():
        if csv_col not in header_set:
            raise HTTPException(400, f"CSV column not found in file: {csv_col}")
        if db_col not in table_columns:
            raise HTTPException(400, f"Unknown table column: {db_col}")
        if db_col in seen_db_cols:
            raise HTTPException(400, f"Database column mapped more than once: {db_col}")
        seen_db_cols.add(db_col)


def _resolve_match_columns(table: Table, match_columns: list[str]) -> list[str]:
    table_columns = set(table.columns.keys())
    if match_columns:
        invalid = [c for c in match_columns if c not in table_columns]
        if invalid:
            raise HTTPException(400, f"Unknown match columns: {', '.join(invalid)}")
        return match_columns

    pk_cols = [col.name for col in table.primary_key.columns]
    if pk_cols:
        return pk_cols

    for constraint in table.constraints:
        if constraint.__class__.__name__ == "UniqueConstraint":
            cols = [col.name for col in constraint.columns]
            if cols:
                return cols

    raise HTTPException(
        400,
        "Update mode requires match columns. Pick the primary key or a unique column set.",
    )


def _apply_row(
    db: Session,
    table: Table,
    *,
    row_number: int,
    row: dict[str, Any],
    mode: str,
    column_mapping: dict[str, str],
    match_columns: list[str],
    ignore_blank_values: bool,
) -> str:
    values: dict[str, Any] = {}
    match_values: dict[str, Any] = {}

    reverse_mapping = {db_col: csv_col for csv_col, db_col in column_mapping.items()}

    for csv_col, db_col in column_mapping.items():
        raw = row.get(csv_col)
        if _is_blank(raw):
            if ignore_blank_values:
                continue
            value = None
        else:
            value = _coerce_value(raw, table.c[db_col].type)
        values[db_col] = value
        if db_col in match_columns:
            match_values[db_col] = value

    if mode == "insert":
        if not values:
            return "skipped"
        db.execute(pg_insert(table).values(**values))
        return "inserted"

    # UPDATE mode = upsert by key
    if match_columns:
        for key in match_columns:
            if key not in reverse_mapping:
                raise HTTPException(400, f"Match column '{key}' must also be mapped from CSV")
            raw_key = row.get(reverse_mapping[key])
            if _is_blank(raw_key):
                raise HTTPException(400, f"Match column '{key}' is blank in row {row_number}")
            match_values[key] = _coerce_value(raw_key, table.c[key].type)

    if not match_values:
        raise HTTPException(400, f"Unable to determine match columns for row {row_number}")

    criteria = [table.c[col] == val for col, val in match_values.items()]
    existing = db.execute(select(table).where(*criteria)).first()

    if existing:
        if values:
            db.execute(table.update().where(*criteria).values(**values))
            return "updated"
        return "skipped"

    payload = {**match_values, **values}
    db.execute(pg_insert(table).values(**payload))
    return "inserted"


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in BLANK_MARKERS


def _coerce_value(raw: Any, column_type: Any) -> Any:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in BLANK_MARKERS:
        return None

    if isinstance(column_type, (Integer, BigInteger)):
        return int(_parse_decimal(text))
    if isinstance(column_type, Numeric):
        return _parse_decimal(text)
    if isinstance(column_type, Float):
        return float(_parse_decimal(text))
    if isinstance(column_type, Boolean):
        return _parse_bool(text)
    if isinstance(column_type, Date):
        return _parse_date(text)
    if isinstance(column_type, DateTime):
        return _parse_datetime(text)
    if isinstance(column_type, (JSONB,)):
        return _parse_json(text)
    if isinstance(column_type, String) or isinstance(column_type, Text):
        return text
    return text


def _parse_decimal(text: str) -> Decimal:
    cleaned = text.replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid number: {text}") from exc


def _parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean: {text}")


def _parse_date(text: str) -> date:
    formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d-%b-%Y",
        "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid date: {text}") from exc


def _parse_datetime(text: str) -> datetime:
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime: {text}") from exc


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
