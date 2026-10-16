"""
The close2 regression gate.

The breach sweep rebuilds the RELIANCE corpus under the old rule (close, two
closes) before trusting the three new ones. If the rebuild does not
reproduce the existing corpus's events exactly, something other than the
breach rule changed, and no comparison between rules can be read. Nothing is
scored until this passes.

"Exactly" means: the same column names in the same order, the same Arrow
type per column, the same row count, and - after both tables are sorted by
every column - every column equal value for value, nulls matching nulls.
Row order is not compared; it is an artefact of the writer. Schema metadata
is ignored. Float NaN is read as null on both sides.

No column is excluded, and the failure reason lists every differing column.
Two can differ for reasons other than the breach rule: `datetime` is
rendered in the build machine's local timezone, and `slice` comes from
assign_slices, whose unstable quicksort can label rows sharing a bar_index
at the cutoff differently if they arrived in another order. Either one
alone is the diagnosis, not a pass.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Union

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str
    rows: int


def _nan_as_null(column: pa.ChunkedArray) -> pa.ChunkedArray:
    if not pa.types.is_floating(column.type):
        return column
    return pc.if_else(pc.is_nan(column), pa.scalar(None, column.type), column)


def _normalised(table: pa.Table) -> pa.Table:
    """Schema metadata dropped, float NaN turned into null."""
    columns = [_nan_as_null(table.column(i)) for i in range(table.num_columns)]
    return pa.Table.from_arrays(columns, schema=table.schema.remove_metadata())


def _sort_keys(schema: pa.Schema) -> List[Tuple[str, str]]:
    # A column of Arrow type null holds no values and cannot be a sort key.
    return [(field.name, "ascending") for field in schema
            if not pa.types.is_null(field.type)]


def compare_event_tables(reference: pa.Table, rebuilt: pa.Table) -> GateResult:
    """Apply the exact-match definition above to two in-memory tables."""
    rows = reference.num_rows
    if reference.column_names != rebuilt.column_names:
        only_ref = sorted(set(reference.column_names) - set(rebuilt.column_names))
        only_new = sorted(set(rebuilt.column_names) - set(reference.column_names))
        detail = ("" if only_ref or only_new
                  else " (same names, different order)")
        return GateResult(
            False, f"columns differ: only in reference {only_ref}, "
                   f"only in rebuilt {only_new}{detail}", rows)

    for ref_field, new_field in zip(reference.schema, rebuilt.schema):
        if ref_field.type != new_field.type:
            return GateResult(
                False, f"column {ref_field.name!r} is {ref_field.type} in the "
                       f"reference but {new_field.type} rebuilt", rows)

    if reference.num_rows != rebuilt.num_rows:
        return GateResult(
            False, f"row count {reference.num_rows} in the reference, "
                   f"{rebuilt.num_rows} rebuilt", rows)

    reference, rebuilt = _normalised(reference), _normalised(rebuilt)
    keys = _sort_keys(reference.schema)
    ref_order = pc.sort_indices(reference, sort_keys=keys)
    new_order = pc.sort_indices(rebuilt, sort_keys=keys)

    differing = [
        name for name in reference.column_names
        if not reference.column(name).take(ref_order).equals(
            rebuilt.column(name).take(new_order))
    ]
    if differing:
        return GateResult(
            False, f"columns {differing} differ after sorting both tables "
                   "by every column", rows)

    return GateResult(
        True, f"{rows} rows match on all {len(reference.column_names)} columns",
        rows)


def check_regression(reference_events: Union[str, Path],
                     rebuilt_events: Union[str, Path]) -> GateResult:
    """Read two events.parquet files and compare them exactly."""
    return compare_event_tables(pq.read_table(reference_events),
                                pq.read_table(rebuilt_events))
