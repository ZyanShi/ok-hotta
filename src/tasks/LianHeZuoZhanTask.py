import time
import threading
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask
from src.config import key_config_option


class LianHeZuoZhanTask(BaseQRSLTask):
    """联合作战自动化任务"""

    CHEST_NAMES = ['chest1', 'chest2', 'chest3', 'chest4', 'chest5']
    CHEST_THRESHOLDS = {
        'chest1': 0.8, 'chest2': 0.8, 'chest3': 0.8, 'chest4': 0.8, 'chest5': 0.8,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "联合作战"
        self.description = "矿砂"
        self.group_name = "精炼强化"
        self.group_icon = FluentIcon.UP
        self.icon = FluentIcon.PEOPLE

        turn_options = ['左转', '右转', '不转向']
        battle_options = ['自动战斗', '孟章（前台）']

        self.default_config.update({
            '循环次数': 10000,
            '战斗方式': '自动战斗',
            '宝箱等待超时': 180,
            '启用前进': False,
            '前进时间': 9,
            '启用转向': '不转向',
            '转向时间': 5,
            '活力开箱': False,
        })

        self.config_description = {
            '循环次数': '执行副本的次数',
            '战斗方式': '选择副本内战斗方式',
            '宝箱等待超时': '等待宝箱超时（秒）',
            '启用前进': '是否前进',
            '前进时间': '前进时长（秒）',
            '启用转向': '前进后转向',
            '转向时间': '转向时长（秒）',
            '活力开箱': '关闭自动战斗开箱时开启',
        }

        self.config_type['启用转向'] = {'type': "drop_down", 'options': turn_options}
        self.config_type['战斗方式'] = {'type': "drop_down", 'options': battle_options}

    # ---------- 源器键 ----------

    def _get_source_key(self):
        try:
            return self.get_global_config(key_config_option).get('源器键1', 'x')
        except Exception:
            self.log_debug("读取源器键1失败，使用默认 'x'")
            return 'x'

    @property
    def _source_key(self):
        return self._get_source_key()

    def _get_source_key2(self):
        try:
            return self.get_global_config(key_config_option).get('源器键2', 'c')
        except Exception:
            self.log_debug("读取源器键2失败，使用默认 'c'")
            return 'c'

    # ---------- 通用 ----------

    def _sleep_with_check(self, seconds, interval=0.2):
        elapsed = 0
        while elapsed < seconds:
            self._check_stopped()
            remaining = min(interval, seconds - elapsed)
            self.sleep(remaining)
            elapsed += remaining

    # ---------- 宝箱检测 ----------

    def _find_chest_stable(self, confirm_gap=0.3, max_attempts=3):
        """连续两帧检测到同一位置（±80px）才算有效。返回 (name, box) 或 (None, None)。"""
        for _ in range(max_attempts):
            self._check_stopped()
            frame = self.frame
            if frame is None:
                self.sleep(0.2)
                continue
            height, width = frame.shape[:2]
            full_box = Box(0, 0, width, height)

            for name in self.CHEST_NAMES:
                threshold = self.CHEST_THRESHOLDS.get(name, 0.8)
                result = self.find_feature(name, box=full_box, threshold=threshold)
                if not result:
                    continue

                first_box = result[0]
                first_center = first_box.center()
                self.sleep(confirm_gap)

                frame2 = self.frame
                if frame2 is None:
                    break
                result2 = self.find_feature(name, box=full_box, threshold=threshold)
                if not result2:
                    self.log_debug(f"宝箱 {name} 二次确认失败，判定误检")
                    break

                second_box = result2[0] if len(result2) == 1 else self._get_closest_box(result2, first_box)
                second_center = second_box.center()

                dx = abs(first_center[0] - second_center[0])
                dy = abs(first_center[1] - second_center[1])
                if dx < 80 and dy < 80:
                    return name, second_box

                self.log_info(f"宝箱 {name} 两次位置偏移过大，判定误检")
                break

            self.sleep(0.5)

        return None, None

    def _find_any_chest_once(self):
        """单帧检测任一宝箱图标，返回 (name, box) 或 (None, None)。"""
        frame = self.frame
        if frame is None:
            return None, None
        h, w = frame.shape[:2]
        full_box = Box(0, 0, w, h)
        for name in self.CHEST_NAMES:
            results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLDS.get(name, 0.8))
            if results:
                return name, results[0]
        return None, None

    def _is_opened_chest_visible(self):
        return self.find_one('opened chest', threshold=0.7) is not None

    # ---------- 活力开箱：OCR检测"开启"字 ----------

    def _approach_chest_with_ocr(self, max_walk_time=60):
        target_chest = self.wait_any_chest(time_out=30)
        if target_chest is None:
            self.log_error("无法获取宝箱")
            return False

        start_time = time.time()
        chest_disappear_count = 0
        last_key_press_time = 0
        key_press_interval = 0.15
        locked_chest_type = None
        last_ocr_time = 0

        x1, y1 = self._get_scaled_coordinates(1110, 520)
        x2, y2 = self._get_scaled_coordinates(1280, 575)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)

        try:
            while time.time() - start_time < max_walk_time:
                self._check_stopped()
                current_time = time.time()

                if current_time - last_ocr_time >= 0.5:
                    try:
                        ocr_results = self.ocr(box=ocr_box, target_height=540)
                        if ocr_results:
                            for box in ocr_results:
                                if '开启' in box.name.strip():
                                    self.log_info(f"检测到'开启'文字: {box.name.strip()}")
                                    return True
                    except Exception as e:
                        self.log_debug(f"OCR检测异常: {e}")
                    last_ocr_time = current_time

                if current_time - last_key_press_time < key_press_interval:
                    self.sleep(0.05)
                    continue

                frame = self.frame
                if frame is None:
                    continue

                height, width = frame.shape[:2]
                full_box = Box(0, 0, width, height)
                screen_center_x = width // 2

                current_chest = None
                if locked_chest_type:
                    results = self.find_feature(locked_chest_type, box=full_box, threshold=0.8)
                    if results:
                        current_chest = results[0] if len(results) == 1 else self._get_closest_box(results, target_chest)

                if current_chest is None:
                    for name in self.CHEST_NAMES:
                        results = self.find_feature(name, box=full_box, threshold=0.6)
                        if results:
                            locked_chest_type = name
                            current_chest = results[0] if len(results) == 1 else self._get_closest_box(results, target_chest)
                            break

                if current_chest is None:
                    chest_disappear_count += 1
                    if chest_disappear_count >= 5:
                        current_chest = self._reacquire_chest()
                        if current_chest is None:
                            self.log_error("无法重新获取宝箱")
                            return False
                else:
                    chest_disappear_count = 0

                target_chest = current_chest
                chest_x, chest_y = target_chest.center()
                if not self._adjust_position(chest_x, chest_y, screen_center_x, width, height):
                    last_key_press_time = current_time

            self.log_error(f"接近宝箱超时（{max_walk_time}秒）")
            return False
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error(f"接近宝箱(OCR)异常: {e}")
            return False

    # ---------- 孟章（前台）线程 ----------

    def _mengzhang_front_combat_loop(self, stop_event):
        """线程启动后先单击左键一次（无延迟），
        然后循环：源器1 → 等3s → 长按左键60s → 源器2 → 等13s。"""
        frame = self.frame
        if frame is None:
            self.log_error("孟章（前台）：无法获取屏幕帧")
            return
        h, w = frame.shape[:2]
        center_x = w // 2
        center_y = h // 2
        self.log_info(f"孟章（前台）：线程启动，中心坐标 ({center_x}, {center_y})")

        try:
            # 先单击左键一次（无延迟）
            self.log_info("孟章（前台）：单击左键一次")
            try:
                self.mouse_down(center_x, center_y, key='left')
                self.mouse_up(key='left')
            except Exception:
                try:
                    self.mouse_up(key='left')
                except Exception:
                    pass
                raise

            while not stop_event.is_set():
                source1_key = self._source_key
                self.log_info(f"孟章（前台）：按源器1 [{source1_key}]")
                self.send_key(source1_key)

                start = time.time()
                while time.time() - start < 3:
                    if stop_event.is_set():
                        break
                    self._sleep_with_check(0.2, interval=0.2)
                if stop_event.is_set():
                    break

                self.log_info("孟章（前台）：长按左键60秒开始")
                try:
                    self.mouse_down(center_x, center_y, key='left')
                    start = time.time()
                    while time.time() - start < 60:
                        if stop_event.is_set():
                            break
                        self._sleep_with_check(1.0, interval=1.0)
                    self.mouse_up(key='left')
                    self.log_info("孟章（前台）：长按左键60秒结束")
                except TaskDisabledException:
                    try:
                        self.mouse_up(key='left')
                    except Exception:
                        pass
                    raise
                except Exception as e:
                    self.log_error(f"孟章（前台）：长按异常: {e}")
                    try:
                        self.mouse_up(key='left')
                    except Exception:
                        pass
                    raise
                if stop_event.is_set():
                    break

                source2_key = self._get_source_key2()
                self.log_info(f"孟章（前台）：按源器2 [{source2_key}]")
                self.send_key(source2_key)

                start = time.time()
                while time.time() - start < 13:
                    if stop_event.is_set():
                        break
                    self._sleep_with_check(1.0, interval=1.0)

        except TaskDisabledException:
            self.log_info("孟章（前台）：收到停止信号")
        except Exception as e:
            self.log_error(f"孟章（前台）：循环异常: {e}")
        finally:
            try:
                self.mouse_up(key='left')
            except Exception:
                pass
            self.log_info("孟章（前台）：线程结束")

    # ---------- 孟章：开自动战斗后快速确认宝箱状态 ----------

    def _check_chest_after_auto_combat(self, chest_name, chest_box):
        """自动战斗开箱是瞬间的，sleep(1) 后快速确认一次。
        返回 (still_unopened, chest_name, chest_box)
        """
        # 1) 优先看 opened chest 图标
        if self._is_opened_chest_visible():
            self.log_info("孟章（前台）：检测到宝箱已打开")
            return False, chest_name, chest_box

        # 2) 看原宝箱图标是否还在
        name_now, box_now = self._find_any_chest_once()
        if name_now is not None:
            self.log_info(f"孟章（前台）：宝箱 {name_now} 仍在，立即进入接近流程")
            return True, name_now, box_now

        # 3) 图标消失 → 再确认一次，排除单帧遮挡
        self.sleep(0.5)
        if self._is_opened_chest_visible():
            self.log_info("孟章（前台）：宝箱已被自动战斗打开")
            return False, chest_name, chest_box
        name_now2, box_now2 = self._find_any_chest_once()
        if name_now2 is not None:
            self.log_info(f"孟章（前台）：宝箱 {name_now2} 仍在（二次），立即进入接近流程")
            return True, name_now2, box_now2

        self.log_info("孟章（前台）：宝箱图标持续消失，判定已被自动战斗打开")
        return False, chest_name, chest_box

    # ---------- 主流程 ----------

    def run(self):
        try:
            self.log_info("===== 联合作战任务启动 =====", notify=True)

            max_loops = self.config.get('循环次数', 10000)
            chest_timeout = self.config.get('宝箱等待超时', 180)
            enable_forward = self.config.get('启用前进', False)
            forward_time = self.config.get('前进时间', 9)
            enable_turn = self.config.get('启用转向', '不转向')
            turn_time = self.config.get('转向时间', 5)
            combat_mode = self.config.get('战斗方式', '自动战斗')
            use_vitality = self.config.get('活力开箱', False)

            self.log_info(f"配置: 循环={max_loops}, 战斗方式={combat_mode}, 超时={chest_timeout}s, "
                          f"前进={enable_forward}/{forward_time}s, 转向={enable_turn}/{turn_time}s, 活力开箱={use_vitality}")

            loop_count = 0

            while loop_count < max_loops:
                loop_count += 1
                self.log_info(f"--- 第 {loop_count}/{max_loops} 次循环 ---")

                if not self.is_main_page():
                    self.log_error("无法进入游戏主页面，跳过本次循环")
                    self.sleep(5)
                    continue

                if not self.enter_dungeon():
                    self.log_error("进入副本失败，跳过本次循环")
                    self.sleep(5)
                    continue

                if enable_forward:
                    self.log_info(f"前进 {forward_time} 秒...")
                    self.send_key_safe('w', down_time=forward_time)
                else:
                    self.log_info("跳过前进")

                if enable_turn == '左转':
                    self.log_info(f"左转 {turn_time} 秒...")
                    self.send_key_safe('a', down_time=turn_time)
                elif enable_turn == '右转':
                    self.log_info(f"右转 {turn_time} 秒...")
                    self.send_key_safe('d', down_time=turn_time)
                else:
                    self.log_info("跳过转向")

                # 战斗
                combat_stop = None
                combat_thread = None

                if combat_mode == '自动战斗':
                    self.log_info("开启自动战斗")
                    self.start_auto_combat()
                    self.sleep(2)
                elif combat_mode == '孟章（前台）':
                    self.log_info("启动孟章（前台）战斗线程")
                    combat_stop = threading.Event()
                    combat_thread = threading.Thread(
                        target=self._mengzhang_front_combat_loop,
                        args=(combat_stop,),
                        daemon=True,
                    )
                    combat_thread.start()
                else:
                    self.log_error(f"未知战斗方式: {combat_mode}")

                # 等待宝箱
                self.log_info(f"等待宝箱出现（超时{chest_timeout}s）...")
                start_time = time.time()
                found_opened_chest = False
                found_unopened_chest = False
                chest_box = None
                chest_name = None

                try:
                    while time.time() - start_time < chest_timeout:
                        frame = self.frame
                        if frame is None:
                            self.sleep(0.5)
                            continue

                        opened_box = self.find_one('opened chest', threshold=0.7)
                        if opened_box:
                            self.log_info("检测到已打开的宝箱")
                            found_opened_chest = True
                            break

                        name, box = self._find_chest_stable()
                        if box is not None:
                            chest_name = name
                            chest_box = box
                            self.log_info(f"检测到未打开的宝箱: {name}")
                            found_unopened_chest = True
                            break

                        self.sleep(0.5)
                finally:
                    if combat_stop is not None:
                        combat_stop.set()
                        if combat_thread is not None:
                            combat_thread.join(timeout=3)
                        self.log_info("孟章（前台）：战斗线程已停止")

                # 孟章模式：开自动战斗 → sleep(1) → 快速确认宝箱状态
                if combat_mode == '孟章（前台）' and (found_opened_chest or found_unopened_chest):
                    self.log_info("孟章（前台）：检测到宝箱，开启自动战斗")
                    self.start_auto_combat()
                    self.sleep(1)

                    if found_unopened_chest:
                        still_unopened, chest_name, chest_box = self._check_chest_after_auto_combat(
                            chest_name, chest_box
                        )
                        if still_unopened and chest_box is not None:
                            found_unopened_chest = True
                            found_opened_chest = False
                            self.log_info(f"孟章（前台）：宝箱 {chest_name} 仍存在，继续接近流程")
                        else:
                            found_unopened_chest = False
                            found_opened_chest = True
                            self.log_info("孟章（前台）：宝箱已被自动战斗打开，跳过接近流程")

                # 开箱
                if found_opened_chest:
                    self.log_info("宝箱已打开，直接退出副本")
                elif found_unopened_chest and chest_box:
                    self.log_info(f"尝试接近并打开宝箱({chest_name})")
                    remaining_time = chest_timeout - (time.time() - start_time)

                    if use_vitality:
                        self.log_info("活力开箱模式（OCR检测'开启'）")
                        success = self._approach_chest_with_ocr(max_walk_time=remaining_time)
                        if success:
                            self.send_key_safe('f', down_time=0.1)
                            self.sleep(1)
                            click_x, click_y = self._get_scaled_coordinates(1270, 580)
                            self._click_safe(click_x, click_y, after_sleep=3)
                            self.log_info("开箱完成")
                        else:
                            self.log_error("接近宝箱失败")
                    else:
                        success = self.approach_chest(max_walk_time=remaining_time)
                        if success:
                            self.log_info("成功打开宝箱")
                        else:
                            self.log_error("打开宝箱失败")
                else:
                    self.log_error(f"{chest_timeout}秒内未找到宝箱，退出副本重试")

                self.log_info("退出副本...")
                self.exit_dungeon()
                self.log_info(f"第 {loop_count} 次循环完成")

            self.log_info(f"===== 联合作战任务结束，共完成 {loop_count} 次循环 =====", notify=True)

        except TaskDisabledException:
            self.log_info("联合作战任务被用户手动停止")
        except Exception as e:
            self.log_error(f"任务执行过程中出现异常: {e}", exception=e, notify=True)
            self.screenshot("lianhezuozhan_error")
            raise