"""Write database.mmd from the Unigreen database schema, so the diagram follows the real tables.

Reads information_schema from the staging database through the Unigreen compose project.
Design output only. Run: python gen_er.py --unigreen /path/to/Unigreen
"""

import argparse
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = ("select table_name, column_name, data_type, is_nullable from information_schema.columns "
           "where table_schema='public' and table_name <> 'alembic_version' order by table_name, ordinal_position")
FOREIGN_KEYS = ("select tc.table_name, ccu.table_name from information_schema.table_constraints tc "
                "join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name "
                "where tc.constraint_type='FOREIGN KEY' and tc.table_schema='public'")


def psql(unigreen, sql):
    result = subprocess.run(
        ["docker", "compose", "-f", str(Path(unigreen) / "compose.yaml"), "exec", "-T", "db",
         "psql", "-U", "unigreen", "-d", "unigreen", "-tAF", "|", "-c", sql],
        capture_output=True, text=True, check=True)
    return [line.split("|") for line in result.stdout.splitlines() if line.strip()]


def mermaid_type(sql_type):
    return re.sub(r"[^a-z0-9]", "", sql_type.lower().replace("character varying", "varchar")
                  .replace("timestamp with time zone", "timestamp").replace("timestamp without time zone", "timestamp")
                  .replace("double precision", "float").replace("integer", "int")) or "text"


def render(columns, foreign_keys):
    lines = ["%% status: generated from the Unigreen database schema (staging)", "erDiagram"]
    tables = {}
    for table, column, dtype, nullable in columns:
        tables.setdefault(table, []).append((column, mermaid_type(dtype), nullable == "NO"))
    for table in sorted(tables):
        lines.append(f"  {table} {{")
        for column, dtype, required in tables[table]:
            lines.append(f"    {dtype} {column}{' PK' if column == 'id' else ''}")
        lines.append("  }")
    for child, parent in sorted(set(foreign_keys)):
        lines.append(f'  {parent} ||--o{{ {child} : "references"')
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the Unigreen database diagram")
    parser.add_argument("--unigreen", required=True, type=Path)
    args = parser.parse_args(argv)
    columns = [tuple(r) for r in psql(args.unigreen, COLUMNS)]
    foreign = [tuple(r) for r in psql(args.unigreen, FOREIGN_KEYS)]
    (HERE / "src" / "database.mmd").write_text(render(columns, foreign), encoding="utf-8")
    print(f"wrote src/database.mmd: {len(set(c[0] for c in columns))} tables, {len(set(foreign))} relationships")


if __name__ == "__main__":
    main()
