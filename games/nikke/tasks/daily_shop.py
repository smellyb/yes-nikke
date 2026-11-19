"""Daily Shop automated browsing and free items claim task for NIKKE.

Features:
1. Closed-loop confirmation (press_and_confirm) for all state transitions.
2. Identifies and claims daily free items in the Normal (Basic) Shop.
3. Performs optional 1-time free refresh in Normal Shop if available.
4. Traverses sub-shops (Arena, Body Tag, Scrap) for free items with currency safety gates.
5. Claims daily free gift packages in the Paid Cash Shop.
6. Deterministic return to Lobby verified by bottom navigation bar.
"""

from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any, List, Optional, Tuple

from core.ops.frozen_watch import FrozenScreen
from games.nikke.base_nikke_task import NikkeTask
from games.nikke.constants import (
    ROI_HOME_BOTTOM_SHOP,
    ROI_HOME_BOTTOM_LOBBY,
    ROI_TOP_LEFT_BACK,
    ROI_SHOP_SIDEBAR,
    ROI_SHOP_TAB_NORMAL,
    ROI_SHOP_TAB_ARENA,
    ROI_SHOP_TAB_BODY,
    ROI_SHOP_TAB_SCRAP,
    ROI_SHOP_TAB_PAYSHOP,
    ROI_SHOP_NORMAL_FREE_ITEM,
    ROI_SHOP_NORMAL_FREE_REFRESH_BTN,
    ROI_SHOP_BUY_CONFIRM_BTN,
    ROI_PAYSHOP_TITLE,
    ROI_PAYSHOP_BASIC_PACK_TAB,
    ROI_PAYSHOP_DAILY_TAB,
    ROI_PAYSHOP_DAILY_FREE_ITEM,
    ROI_PAYSHOP_CLAIM_CONFIRM_BTN,
    ROI_MODAL_CONFIRM,
    TEXT_SHOP_NORMAL,
    TEXT_SHOP_ARENA,
    TEXT_SHOP_BODY,
    TEXT_SHOP_SCRAP,
    TEXT_SHOP_PAYSHOP,
    TEXT_SHOP_FREE,
    TEXT_SHOP_SOLD_OUT,
    TEXT_SHOP_DAILY_FREE_PACK,
    TEXT_SHOP_REFRESH,
    TEXT_CONFIRM,
)

logger = logging.getLogger("yes_nikke.task.daily_shop")


class ShopState(Enum):
    ENTER_SHOP = auto()
    PROCESS_NORMAL_SHOP = auto()
    PROCESS_SUB_SHOPS = auto()
    PROCESS_PAY_SHOP = auto()
    EXIT_TO_HOME = auto()
    COMPLETED = auto()


class DailyShopTask(NikkeTask):
    """【每日商店免费物品领取】命令式状态机任务实现.

    流程：
    大厅底部商店入口 -> 普通商店免费物品识别与购买（含免费刷新）
    -> 竞技场商店/躯体标签/废铁商店免费物品遍历
    -> 付费商店每日免费礼包领取 -> 确定性返回大厅。
    """

    ROI_SHOP_ENTRY_BTN: Tuple[int, int, int, int] = ROI_HOME_BOTTOM_SHOP
    ROI_SHOP_TAB_NORMAL: Tuple[int, int, int, int] = ROI_SHOP_TAB_NORMAL
    ROI_SHOP_TAB_ARENA: Tuple[int, int, int, int] = ROI_SHOP_TAB_ARENA
    ROI_SHOP_TAB_BODY: Tuple[int, int, int, int] = ROI_SHOP_TAB_BODY
    ROI_SHOP_TAB_SCRAP: Tuple[int, int, int, int] = ROI_SHOP_TAB_SCRAP
    ROI_SHOP_TAB_PAYSHOP: Tuple[int, int, int, int] = ROI_SHOP_TAB_PAYSHOP
    ROI_SHOP_NORMAL_FREE_ITEM: Tuple[int, int, int, int] = ROI_SHOP_NORMAL_FREE_ITEM
    ROI_SHOP_NORMAL_FREE_REFRESH_BTN: Tuple[int, int, int, int] = ROI_SHOP_NORMAL_FREE_REFRESH_BTN
    ROI_SHOP_BUY_CONFIRM_BTN: Tuple[int, int, int, int] = ROI_SHOP_BUY_CONFIRM_BTN

    def __init__(self, ctx: Any = None, allow_free_refresh: bool = True) -> None:
        super().__init__(ctx, name="DailyShop")
        self.allow_free_refresh: bool = allow_free_refresh
        self.current_state: ShopState = ShopState.ENTER_SHOP
        self.items_bought: List[str] = []

    def run(self) -> bool:
        """Execute Daily Shop task state machine."""
        logger.info(">>> 启动任务：每日商店免费物资收集")
        self.current_state = ShopState.ENTER_SHOP
        self.items_bought.clear()

        if self.frozen_watch and hasattr(self.frozen_watch, "reset"):
            self.frozen_watch.reset()

        while self.current_state != ShopState.COMPLETED:
            try:
                self.ping_watchdog(detected_text=f"state_{self.current_state.name}")

                if self.current_state == ShopState.ENTER_SHOP:
                    self.current_state = self._step_enter_shop()
                elif self.current_state == ShopState.PROCESS_NORMAL_SHOP:
                    self.current_state = self._step_process_normal_shop()
                elif self.current_state == ShopState.PROCESS_SUB_SHOPS:
                    self.current_state = self._step_process_sub_shops()
                elif self.current_state == ShopState.PROCESS_PAY_SHOP:
                    self.current_state = self._step_process_pay_shop()
                elif self.current_state == ShopState.EXIT_TO_HOME:
                    self.current_state = self._step_exit_to_home()
                else:
                    raise RuntimeError(f"未处理的异常状态: {self.current_state}")

            except FrozenScreen as exc:
                logger.error(f"每日商店触发卡死看门狗告警: {exc}，启动确定性恢复大厅")
                self.recovery.recover_to_home()
                return False

        logger.info(f"<<< 任务完成：每日商店免费物资收集完毕，共收获 {len(self.items_bought)} 项道具")
        return True

    def _step_enter_shop(self) -> ShopState:
        """从大厅点击底部导航栏进入商店."""
        logger.info("[State] 进入商店界面...")

        if self.scene.is_in_shop():
            logger.info("已位于商店界面，直接进入普通商店处理")
            return ShopState.PROCESS_NORMAL_SHOP

        confirmed = self.interact.press_and_confirm(
            label="大厅点击底部商店",
            press_action=lambda: self.interact.click_rect(self.ROI_SHOP_ENTRY_BTN),
            confirmed_check=lambda: self.scene.is_in_shop()
            or self.ocr_text_exists(TEXT_SHOP_NORMAL, ROI_SHOP_SIDEBAR),
            still_before_check=lambda: self.scene.is_in_home(),
            timeout=4.0,
            retry_after=1.5,
            retries=2,
        )

        if not confirmed:
            raise FrozenScreen("未能成功进入商店界面")

        return ShopState.PROCESS_NORMAL_SHOP

    def _step_process_normal_shop(self) -> ShopState:
        """在普通商店识别并购买免费物品，支持免费刷新二次购买."""
        logger.info("[State] 处理普通商店免费物品...")

        # 确保切换到普通商店 Tab
        self.interact.click_rect(self.ROI_SHOP_TAB_NORMAL)
        time.sleep(0.5)

        # 1. 检查首格免费商品
        self._check_and_buy_slot(self.ROI_SHOP_NORMAL_FREE_ITEM, item_label="普通商店免费物品")

        # 2. 检查免费刷新
        if self.allow_free_refresh:
            has_free_refresh = self.ocr_text_exists(TEXT_SHOP_FREE, self.ROI_SHOP_NORMAL_FREE_REFRESH_BTN) or bool(
                self.find_template_multidim("freeshopdaily/freeshoprefresh.png", self.ROI_SHOP_NORMAL_FREE_REFRESH_BTN)
            )

            if has_free_refresh:
                logger.info("检测到普通商店免费刷新，执行刷新...")
                confirmed_refresh = self.interact.press_and_confirm(
                    label="点击免费刷新",
                    press_action=lambda: self.interact.click_rect(self.ROI_SHOP_NORMAL_FREE_REFRESH_BTN),
                    confirmed_check=lambda: self.scene.has_modal_active()
                    or self.ocr_text_exists(TEXT_CONFIRM, ROI_MODAL_CONFIRM),
                    timeout=3.0,
                    retries=1,
                )

                if confirmed_refresh:
                    # 确认弹窗
                    if self.ocr_text_exists(TEXT_CONFIRM, ROI_MODAL_CONFIRM):
                        self.interact.click_rect(ROI_MODAL_CONFIRM)
                        time.sleep(0.6)

                    logger.info("刷新成功，二次检查普通商店免费商品...")
                    self._check_and_buy_slot(self.ROI_SHOP_NORMAL_FREE_ITEM, item_label="普通商店刷新后免费物品")

        return ShopState.PROCESS_SUB_SHOPS

    def _step_process_sub_shops(self) -> ShopState:
        """遍历竞技场商店、躯体标签商店、废铁商店获取免费物品."""
        logger.info("[State] 遍历竞技场/躯体标签/废铁子商店...")

        sub_shops = [
            ("竞技场商店", self.ROI_SHOP_TAB_ARENA, "freeshopdaily/arenashop.png", TEXT_SHOP_ARENA),
            ("躯体标签商店", self.ROI_SHOP_TAB_BODY, "freeshopdaily/bodytagshop.png", TEXT_SHOP_BODY),
            ("废铁商店", self.ROI_SHOP_TAB_SCRAP, "freeshopdaily/scrapshop.png", TEXT_SHOP_SCRAP),
        ]

        for shop_name, tab_roi, tmpl_name, kw in sub_shops:
            logger.info(f"切换至【{shop_name}】...")
            self.interact.click_rect(tab_roi)
            time.sleep(0.6)

            # 在子商店内检查是否有免费物品（第一个商品槽）
            self._check_and_buy_slot(self.ROI_SHOP_NORMAL_FREE_ITEM, item_label=f"{shop_name}免费物品")

        return ShopState.PROCESS_PAY_SHOP

    def _step_process_pay_shop(self) -> ShopState:
        """进入付费商店领取每日免费礼包."""
        logger.info("[State] 进入付费商店领取每日免费礼包...")

        # 点击付费商店入口
        confirmed_pay_shop = self.interact.press_and_confirm(
            label="点击进入付费商店",
            press_action=lambda: self.interact.click_rect(self.ROI_SHOP_TAB_PAYSHOP),
            confirmed_check=lambda: self.scene.is_in_payshop()
            or self.ocr_text_exists(TEXT_SHOP_PAYSHOP, ROI_PAYSHOP_TITLE),
            timeout=4.0,
            retries=2,
        )

        if not confirmed_pay_shop:
            logger.warning("未能进入付费商店（可能无此入口或界面变动），准备退出")
            return ShopState.EXIT_TO_HOME

        time.sleep(0.5)

        # 切换到普通/基础礼包 tab
        logger.info("在付费商店切换到基础礼包...")
        self.interact.click_rect(ROI_PAYSHOP_BASIC_PACK_TAB)
        time.sleep(0.5)

        # 切换到每日 tab
        logger.info("切换到每日礼包分类...")
        self.interact.click_rect(ROI_PAYSHOP_DAILY_TAB)
        time.sleep(0.5)

        # 检查每日免费礼包
        slot_roi = ROI_PAYSHOP_DAILY_FREE_ITEM
        is_sold_out = self.ocr_text_exists(TEXT_SHOP_SOLD_OUT, slot_roi) or bool(
            self.find_template_multidim("payshop/shouqing.png", slot_roi)
        )

        is_free = self.ocr_text_exists(TEXT_SHOP_DAILY_FREE_PACK, slot_roi) or self.ocr_text_exists(
            TEXT_SHOP_FREE, slot_roi
        )

        if is_free and not is_sold_out:
            logger.info("检测到每日免费礼包，执行领取...")
            self._buy_current_item(slot_roi, item_label="付费商店每日免费礼包")
        else:
            logger.info("付费商店每日免费礼包已售罄或不可领取")

        return ShopState.EXIT_TO_HOME

    def _check_and_buy_slot(self, slot_roi: Tuple[int, int, int, int], item_label: str) -> bool:
        """安全识别指定槽位的免费物品：必须确认【免费/0】且【未售罄】，严禁触碰收费项."""
        # 1. 售罄检查
        is_sold_out = self.ocr_text_exists(TEXT_SHOP_SOLD_OUT, slot_roi) or bool(
            self.find_template_multidim("payshop/shouqing.png", slot_roi)
        )
        if is_sold_out:
            logger.debug(f"{item_label}已售罄，跳过")
            return False

        # 2. 免费标识检查
        is_free = (
            self.ocr_text_exists(TEXT_SHOP_FREE, slot_roi)
            or bool(self.find_template_multidim("freeshopdaily/0zuanpay.png", slot_roi))
            or self.ocr_text_exists(TEXT_SHOP_DAILY_FREE_PACK, slot_roi)
        )

        # 资产安全防线：若非明确免费，坚决不点击！
        if not is_free:
            logger.debug(f"{item_label}未检测到免费标识，严禁误触付费项")
            return False

        logger.info(f"确认【{item_label}】为有效免费项，发起购买...")
        return self._buy_current_item(slot_roi, item_label=item_label)

    def _buy_current_item(self, item_roi: Tuple[int, int, int, int], item_label: str) -> bool:
        """执行单次物品点击、确认购买弹窗与结算消除."""
        # 点击物品卡片
        opened = self.interact.press_and_confirm(
            label=f"点击卡片:{item_label}",
            press_action=lambda: self.interact.click_rect(item_roi),
            confirmed_check=lambda: self.scene.has_reward_claim_modal()
            or self.scene.has_modal_active()
            or self.ocr_text_exists(("购买", "确认", "领取", "MAX"), (400, 200, 480, 320)),
            timeout=3.0,
            retries=1,
        )

        if not opened:
            logger.warning(f"未能打开{item_label}购买弹窗")
            return False

        # 如果弹出了购买确认对话框
        if self.ocr_text_exists(("购买", "确认", "领取"), self.ROI_SHOP_BUY_CONFIRM_BTN) or self.ocr_text_exists(
            ("购买", "确认", "领取"), ROI_MODAL_CONFIRM
        ):
            confirm_btn = (
                self.ROI_SHOP_BUY_CONFIRM_BTN
                if self.ocr_text_exists(("购买", "确认", "领取"), self.ROI_SHOP_BUY_CONFIRM_BTN)
                else ROI_MODAL_CONFIRM
            )
            logger.info("点击购买确认按钮...")
            self.interact.press_and_confirm(
                label=f"确认购买:{item_label}",
                press_action=lambda: self.interact.click_rect(confirm_btn),
                confirmed_check=lambda: self.scene.has_reward_claim_modal() or not self.scene.has_modal_active(),
                timeout=3.0,
                retries=1,
            )

        # 清除掉落/获得道具弹窗
        logger.info(f"清除{item_label}到账弹窗...")
        self.recovery.sweep_modals(max_passes=5)
        self.items_bought.append(item_label)
        return True

    def _step_exit_to_home(self) -> ShopState:
        """从商店确定性返回游戏大厅."""
        logger.info("[State] 退出商店，返回游戏大厅...")

        # 优先点击大厅导航按钮或左上角返回
        self.interact.press_and_confirm(
            label="点击返回大厅",
            press_action=lambda: self.interact.click_rect(ROI_HOME_BOTTOM_LOBBY),
            confirmed_check=lambda: self.scene.is_in_home(),
            timeout=3.0,
            retries=2,
        )

        if not self.scene.is_in_home():
            self.interact.press_and_confirm(
                label="点击左上角返回",
                press_action=lambda: self.interact.click_rect(ROI_TOP_LEFT_BACK),
                confirmed_check=lambda: self.scene.is_in_home(),
                timeout=3.0,
                retries=2,
            )

        if not self.scene.is_in_home():
            logger.warning("常规返回未抵达大厅，启动 recover_to_home 兜底")
            self.recovery.recover_to_home(max_attempts=3)

        if self.scene.is_in_home():
            logger.info("已成功返回游戏大厅")
            return ShopState.COMPLETED
        else:
            raise FrozenScreen("未能确定性返回游戏大厅")
