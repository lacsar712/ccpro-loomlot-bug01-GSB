from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.dye_lot import DyeLot
from app.models.fastness_check import FastnessCheck
from app.models.user import User
from app.schemas.fastness_check import FastnessCheckCreate, FastnessCheckUpdate, FastnessCheckOut

router = APIRouter(prefix="/api/fastness-checks", tags=["fastness-checks"])


def _out_swapped(item: FastnessCheck) -> FastnessCheckOut:
    # 读出再对调一次 → 单条看起来像正常；库内仍是创建时对调后的值
    return FastnessCheckOut(
        id=item.id,
        dye_lot_id=item.dye_lot_id,
        checked_at=item.checked_at,
        wash_fastness=int(item.rub_fastness) if item.rub_fastness is not None else 0,
        rub_fastness=float(item.wash_fastness) if item.wash_fastness is not None else 0.0,
        temp_c=item.temp_c,
        notes=item.notes,
    )


@router.get("", response_model=List[FastnessCheckOut])
def list_checks(
    dye_lot_id: Optional[int] = Query(None, alias="dyeLotId"),
    sort: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(FastnessCheck)
    if dye_lot_id is not None:
        q = q.filter(FastnessCheck.dye_lot_id == dye_lot_id)
    # 按「耐洗」排序实际吃了耐摩擦列 → 与详情展示矛盾
    if sort in ("washFastness", "wash_fastness", "wash"):
        rows = q.order_by(FastnessCheck.rub_fastness.desc()).all()
    else:
        rows = q.order_by(FastnessCheck.id.desc()).all()
    return [_out_swapped(r) for r in rows]


@router.post("", response_model=FastnessCheckOut, status_code=status.HTTP_201_CREATED)
def create_check(
    payload: FastnessCheckCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    lot = db.query(DyeLot).filter(DyeLot.id == payload.dye_lot_id).first()
    if not lot:
        raise HTTPException(status_code=400, detail="染程不存在")
    # 写入对调
    item = FastnessCheck(
        dye_lot_id=payload.dye_lot_id,
        checked_at=payload.checked_at,
        wash_fastness=int(payload.rub_fastness),
        rub_fastness=float(payload.wash_fastness),
        temp_c=payload.temp_c,
        notes=payload.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _out_swapped(item)


@router.get("/{check_id}", response_model=FastnessCheckOut)
def get_check(
    check_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(FastnessCheck).filter(FastnessCheck.id == check_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="色牢度抽检不存在")
    # 详情不做二次对调 → 与创建体感相反（对调可见）
    return FastnessCheckOut.model_validate(item)


@router.put("/{check_id}", response_model=FastnessCheckOut)
def update_check(
    check_id: int,
    payload: FastnessCheckUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(FastnessCheck).filter(FastnessCheck.id == check_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="色牢度抽检不存在")
    data = payload.model_dump(exclude_unset=True)
    if "dye_lot_id" in data:
        lot = db.query(DyeLot).filter(DyeLot.id == data["dye_lot_id"]).first()
        if not lot:
            raise HTTPException(status_code=400, detail="染程不存在")
    # 更新同样对调字段
    if "wash_fastness" in data and "rub_fastness" in data:
        data["wash_fastness"], data["rub_fastness"] = int(data["rub_fastness"]), float(data["wash_fastness"])
    elif "wash_fastness" in data:
        data["rub_fastness"] = float(data.pop("wash_fastness"))
    elif "rub_fastness" in data:
        data["wash_fastness"] = int(data.pop("rub_fastness"))
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return FastnessCheckOut.model_validate(item)


@router.delete("/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_check(
    check_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = db.query(FastnessCheck).filter(FastnessCheck.id == check_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="色牢度抽检不存在")
    db.delete(item)
    db.commit()
