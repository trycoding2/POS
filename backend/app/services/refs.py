"""Reference numbers: SALE-YYYYMMDD-000001 etc. Prefix/format from settings (configurable)."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func, cast, String

from app.models.system import Setting
from app.services.settings_service import get_setting


def next_ref(db: Session, kind: str) -> str:
    """kind in SALE/PUR/PAY/RET/EXP/DST/ADJ/ORD/WDR. Atomic per-day sequence."""
    prefix = get_setting(db, f"ref.{kind}.prefix", kind)
    fmt = get_setting(db, "ref.format", "{prefix}-{yyyymmdd}-{seq:06d}")
    date_key = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq_key = f"ref.seq.{kind}.{date_key}"
    row = db.get(Setting, seq_key)
    nxt = (int(row.value) if row and row.value else 0) + 1
    if row is None:
        row = Setting(key=seq_key, value=str(nxt))
        db.add(row)
    else:
        row.value = str(nxt)
    db.flush()
    return fmt.format(prefix=prefix, yyyymmdd=date_key, seq=nxt,
                      yy=date_key[2:], yyyy=date_key[:4])
