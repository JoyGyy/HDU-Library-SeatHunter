"""调度路由：增删查调度、启动/停止引擎、查询引擎状态。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from seathunter.models.schedule import DateMapping, Schedule
from server.models.schemas import (
    AddScheduleRequest,
    MessageResponse,
    ScheduleItem,
    ScheduleListResponse,
    SchedulerStatusResponse,
)

router = APIRouter()


def _get_state(request: Request):
    """从 app.state 获取全局 AppState 实例。"""
    return request.app.state.seathunter


def _schedule_to_item(s: Schedule) -> ScheduleItem:
    """将 Schedule dataclass 转为 ScheduleItem Pydantic 模型。"""
    return ScheduleItem(
        mode=s.mode,
        enabled=s.enabled,
        target_weekdays=s.target_weekdays,
        plan_ids=s.plan_ids,
        mappings=[
            {"target_date": m.target_date, "plan_ids": m.plan_ids}
            for m in s.mappings
        ],
    )


@router.get("", response_model=ScheduleListResponse)
def list_schedules(request: Request):
    """获取所有调度列表。"""
    state = _get_state(request)
    schedules = state.config.get_schedules()
    return ScheduleListResponse(
        success=True,
        schedules=[_schedule_to_item(s) for s in schedules],
    )


@router.post("", response_model=MessageResponse)
def add_schedule(body: AddScheduleRequest, request: Request):
    """添加新调度。"""
    state = _get_state(request)

    mappings = [
        DateMapping(target_date=m.target_date, plan_ids=m.plan_ids)
        for m in body.mappings
    ]

    schedule = Schedule(
        mode=body.mode,
        enabled=body.enabled,
        target_weekdays=body.target_weekdays,
        plan_ids=body.plan_ids,
        mappings=mappings,
    )

    # ConfigManager 没有 add_schedule，用 get + append + save 替代
    schedules = state.config.get_schedules()
    schedules.append(schedule)
    state.config.save_schedules(schedules)

    return MessageResponse(success=True, message="调度已添加")


@router.delete("/{schedule_id}", response_model=MessageResponse)
def delete_schedule(schedule_id: str, request: Request):
    """删除指定索引的调度。"""
    state = _get_state(request)
    schedules = state.config.get_schedules()

    idx = int(schedule_id)
    if idx < 0 or idx >= len(schedules):
        raise HTTPException(status_code=404, detail=f"调度索引 {idx} 不存在")

    schedules.pop(idx)
    state.config.save_schedules(schedules)
    return MessageResponse(success=True, message=f"调度 #{idx} 已删除")


@router.post("/start", response_model=MessageResponse)
def start_engine(request: Request):
    """启动调度引擎。"""
    state = _get_state(request)

    if state.engine is None:
        raise HTTPException(status_code=401, detail="尚未登录，请先登录")

    state.engine.start()
    return MessageResponse(success=True, message="调度引擎已启动")


@router.post("/stop", response_model=MessageResponse)
def stop_engine(request: Request):
    """停止调度引擎。"""
    state = _get_state(request)

    if state.engine is None:
        raise HTTPException(status_code=401, detail="尚未登录，请先登录")

    state.engine.stop()
    return MessageResponse(success=True, message="调度引擎已停止")


@router.get("/status", response_model=SchedulerStatusResponse)
def engine_status(request: Request):
    """获取调度引擎状态。"""
    state = _get_state(request)

    if state.engine is None:
        return SchedulerStatusResponse(running=False)

    raw = state.engine.get_status()
    return SchedulerStatusResponse(
        running=raw["running"],
        trigger_time=raw.get("trigger_time"),
        target_date=raw.get("target_date"),
        remaining_seconds=raw.get("remaining_seconds"),
    )
