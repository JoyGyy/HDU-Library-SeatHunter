"""方案路由：增删查预约方案。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from seathunter.models.plan import Plan, SeatInfo
from server.models.schemas import (
    AddPlanRequest,
    MessageResponse,
    PlanListResponse,
    PlanSchema,
    SeatInfoSchema,
)

router = APIRouter()


def _get_state(request: Request):
    """从 app.state 获取全局 AppState 实例。"""
    return request.app.state.seathunter


def _plan_to_schema(plan: Plan) -> PlanSchema:
    """将 Plan dataclass 转为 PlanSchema Pydantic 模型。"""
    return PlanSchema(
        id=plan.id,
        name=plan.name,
        room_name=plan.room_name,
        floor_name=plan.floor_name,
        begin_time=plan.begin_time,
        duration_hours=plan.duration_hours,
        seats=[
            SeatInfoSchema(
                seat_id=s.seat_id,
                seat_num=s.seat_num,
                booker_uid=s.booker_uid,
            )
            for s in plan.seats
        ],
        target_date=plan.target_date,
        booking_id=plan.booking_id,
    )


@router.get("", response_model=PlanListResponse)
def list_plans(request: Request):
    """获取所有方案列表。"""
    state = _get_state(request)
    plans = state.config.get_plans()
    return PlanListResponse(
        success=True,
        plans=[_plan_to_schema(p) for p in plans],
    )


@router.post("", response_model=MessageResponse)
def add_plan(body: AddPlanRequest, request: Request):
    """添加新方案。"""
    state = _get_state(request)

    # 检查 ID 是否重复
    existing = state.config.get_plan_by_id(body.id)
    if existing:
        raise HTTPException(status_code=400, detail=f"方案 ID '{body.id}' 已存在")

    seats = [
        SeatInfo(
            seat_id=s.seat_id,
            seat_num=s.seat_num,
            booker_uid=s.booker_uid,
        )
        for s in body.seats
    ]

    plan = Plan(
        id=body.id,
        room_name=body.room_name,
        floor_name=body.floor_name,
        begin_time=body.begin_time,
        duration_hours=body.duration_hours,
        seats=seats,
        name=body.name,
        target_date=body.target_date,
    )

    state.config.add_plan(plan)
    return MessageResponse(success=True, message=f"方案 '{plan.id}' 已添加")


@router.delete("/{plan_id}", response_model=MessageResponse)
def delete_plan(plan_id: str, request: Request):
    """删除指定方案。"""
    state = _get_state(request)
    deleted = state.config.delete_plan(plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"方案 '{plan_id}' 不存在")
    return MessageResponse(success=True, message=f"方案 '{plan_id}' 已删除")
