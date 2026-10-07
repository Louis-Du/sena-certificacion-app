import sys, os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import json
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

print("=== Payload #22 (fila de encabezados reales) ===")
p = json.loads(df14a[21].payload)
for i, (k,v) in enumerate(p.items(), 1):
    print(f"  col{i:02d} [{k!r:55s}] = {v!r}")

print()
print("=== Payload #23 (fila siguiente, encabezado complementario) ===")
p = json.loads(df14a[22].payload)
for i, (k,v) in enumerate(p.items(), 1):
    print(f"  col{i:02d} [{k!r:55s}] = {v!r}")

print()
print("=== Payload #24 (primer aprendiz) ===")
p = json.loads(df14a[23].payload)
for i, (k,v) in enumerate(p.items(), 1):
    print(f"  col{i:02d} [{k!r:55s}] = {v!r}")

print()
print("=== Payload #21 (fila de titulo fusionado) ===")
p = json.loads(df14a[20].payload)
for i, (k,v) in enumerate(p.items(), 1):
    print(f"  col{i:02d} [{k!r:55s}] = {v!r}")
