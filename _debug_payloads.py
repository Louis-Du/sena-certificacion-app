import sys, json
sys.path.insert(0, '.')
from app.database import SessionLocal, init_db
from app.models import ImportedRecord
from sqlalchemy import select, func
init_db()
session = SessionLocal()
df14a = session.scalars(
    select(ImportedRecord)
    .where(func.lower(ImportedRecord.information_type)=='df14a')
    .order_by(ImportedRecord.id.asc())
).all()
print('Total DF14A:', len(df14a))
print()
print('===== Muestra de payloads desde el #1 hasta #40 para ver dónde empiezan los datos reales =====')
for i, r in enumerate(df14a[:40], 1):
    payload = json.loads(r.payload)
    keys = list(payload.keys())
    values = list(payload.values())
    keys_preview = keys[:6]
    if len(keys) > 6:
        keys_preview_str = f"{keys_preview}..."
    else:
        keys_preview_str = f"{keys_preview}"
    values_preview = [str(v)[:40] for v in values[:3]]
    print(f"#{i:3d} row={r.row_number:3d} nkeys={len(keys):3d}  keys={keys_preview_str}  values={values_preview}")
print()
print('===== Primeros payloads que PARECEN aprendices (>=4 columnas y un valor numerico largo) =====')
found = 0
for i, r in enumerate(df14a, 1):
    payload = json.loads(r.payload)
    numeric_values = [
        str(v) for v in payload.values()
        if isinstance(v, (int, float, str)) and str(v).strip().isdigit() and len(str(v).strip()) >= 6
    ]
    if len(payload) >= 4 and numeric_values:
        print(f"#{i:3d} row={r.row_number:3d} (candidato) columnas:")
        for k, v in payload.items():
            print(f"     {k!r:60s} = {v!r}")
        print()
        found += 1
        if found >= 5:
            break

print('===== Todas las KEYS distintas (nombres de columnas) en los primeros 60 payloads =====')
all_keys = set()
for r in df14a[:60]:
    payload = json.loads(r.payload)
    for k in payload.keys():
        all_keys.add(k)
for k in sorted(all_keys):
    print(f"  - {k!r}")
