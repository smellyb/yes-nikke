"""Press a game button and only count it once the screen shows it worked.

Lost presses are the most common kind of failure in game automation:
Unity drops a click during GC or transition, the automation moves on as if it
had worked, and flow falls out of sync.

Every press that matters goes through ``press_and_confirm``:
1. press, then wait for ``confirmed()``;
2. not confirmed, and ``still_before()`` is still true: wait ``retry_after`` (1.5 s)
   and press once more;
3. still not confirmed: report as not confirmed without breaking state.

A second press is only made while ``still_before()`` says the screen has not
moved on, so a press that worked late is never repeated.
Presses that spend currency (gems, recruitment, stamina) pass ``retries=0``.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep as _sys_sleep
from typing import Callable, TypeVar, Optional

RETRY_AFTER_SECONDS = 1.5
CONFIRM_TIMEOUT_SECONDS = 3.0
POLL_SECONDS = 0.25

T = TypeVar("T")


def wait_for(
    check: Callable[[], T],
    timeout: float,
    *,
    sleep: Callable[[float], object] = _sys_sleep,
    poll: float = POLL_SECONDS,
    clock: Callable[[], float] = monotonic,
) -> T | None:
    """First truthy ``check()`` within ``timeout`` seconds, else None."""
    end_at = clock() + max(0.0, timeout)
    while True:
        result = check()
        if result:
            return result
        if clock() >= end_at:
            return None
        sleep(poll)


@dataclass(frozen=True)
class PressOutcome:
    confirmed: bool
    presses: int
    # confirmed | confirmed-after-retry | late | moved-on | not-confirmed
    reason: str

    def __bool__(self) -> bool:
        return self.confirmed


def press_and_confirm(
    label: str,
    press: Callable[[], object],
    confirmed: Callable[[], object],
    *,
    still_before: Optional[Callable[[], object]] = None,
    timeout: float = CONFIRM_TIMEOUT_SECONDS,
    retry_after: float = RETRY_AFTER_SECONDS,
    retries: int = 1,
    poll: float = POLL_SECONDS,
    sleep: Callable[[float], object] = _sys_sleep,
    log: Optional[Callable[[str], object]] = None,
    clock: Callable[[], float] = monotonic,
) -> PressOutcome:
    """Press, confirm on screen, re-press once while nothing changed.

    ``still_before`` must verify whether the screen from before the press is
    still shown; without it, no second press is made to avoid blind duplicate clicks.
    """
    logger = log or (lambda msg: None)
    presses = 0

    for attempt in range(max(0, retries) + 1):
        if attempt > 0:
            if still_before is None:
                break
            logger(f"[{label}] 点击未检测到状态迁移，等待 {retry_after:g} 秒后补偿重试...")
            sleep(retry_after)
            # a slow game client may render the state while we waited
            if confirmed():
                return PressOutcome(True, presses, "late")
            if not still_before():
                logger(f"[{label}] 界面已离开初始状态（可能已被其它交互接管），取消重试。")
                return PressOutcome(False, presses, "moved-on")

        press()
        presses += 1

        hit = wait_for(confirmed, timeout, sleep=sleep, poll=poll, clock=clock)
        if hit:
            reason = "confirmed" if attempt == 0 else "confirmed-after-retry"
            return PressOutcome(True, presses, reason)

    return PressOutcome(False, presses, "not-confirmed")
