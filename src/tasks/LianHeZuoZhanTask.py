import time
import threading
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.config import chest_threshold_option
from src.tasks.BaseQRSLTask import BaseQRSLTask


class LianHeZuoZhanTask(BaseQRSLTask):
    """联合作战自动化任务"""

    # chest1~chest5 是真正的宝箱，阈值统一由 BaseQRSLTask.CHEST_THRESHOLD 提供（默认 0.75）
    CHEST_NAMES = ['chest1', 'chest2', 'chest3', 'chest4', 'chest5']

    # 自动战斗模式下，源器1+源器2 同时按的间隔（秒）
    AUTO_COMBAT_SOURCE_INTERVAL = 30.5

    # 'opened chest' 模板只有 25x19 像素且只有 1 个标注样本，原来硬编码 0.7 太松：
    # 画面里形状/明暗相近的暗色块就能过线，导致“发现宝箱”其实不是宝箱。
    # 这里改走全局“宝箱阈值”配置，并强制不低于该下限。
    OPENED_CHEST_MIN_THRESHOLD = 0.85

    # 操作选项 -> 按键映射
    OPERATION_KEYS = {
        '前进': 'w',
        '左转': 'a',
        '右转': 'd',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "联合作战"
        self.description = "矿砂"
        self.group_name = "精炼强化"
        self.group_icon = FluentIcon.UP
        self.icon = FluentIcon.PEOPLE

        operation_options = ['前进', '左转', '右转', '不操作']
        battle_options = ['自动战斗', '孟章（前台）']

        self.default_config.update({
            '循环次数': 10000,
            '战斗方式': '自动战斗',
            '宝箱等待超时': 180,
            '操作1': '前进',
            '操作1时间(ms)': 9000,
            '操作2': '不操作',
            '操作2时间(ms)': 5000,
            '十字搜索': True,
            '活力开箱': False,
        })

        self.config_description = {
            '循环次数': '执行副本的次数',
            '战斗方式': '选择副本内战斗方式',
            '宝箱等待超时': '等待宝箱超时（秒）',
            '操作1': '进副本后执行的第一个操作',
            '操作1时间(ms)': '操作1的持续时间（毫秒）',
            '操作2': '操作1之后执行的第二个操作',
            '操作2时间(ms)': '操作2的持续时间（毫秒）',
            '十字搜索': '宝箱等待超时后、退出副本前，执行一次十字搜索寻找宝箱',
            '活力开箱': '关闭自动战斗开箱时开启',
        }

        self.config_type['操作1'] = {'type': "drop_down", 'options': operation_options}
        self.config_type['操作2'] = {'type': "drop_down", 'options': operation_options}
        self.config_type['战斗方式'] = {'type': "drop_down", 'options': battle_options}

    # ---------- 操作 ----------

    def _do_operation(self, operation, duration_ms, label='操作'):
        """按配置执行操作1/操作2，'不操作' 直接跳过。duration_ms 单位为毫秒。"""
        key = self.OPERATION_KEYS.get(operation)
        if key is None:
            self.log_info(f"{label}：不操作")
            return
        duration = max(duration_ms, 0) / 1000.0
        self.log_info(f"{label}：{operation} {duration_ms} ms")
        self.send_key_safe(key, down_time=duration)

    def _press_source_1_and_2(self):
        """释放源器1和源器2。"""
        source1_key = self._source_key
        source2_key = self._get_source_key2()
        self.log_info("释放源器")
        try:
            self.send_key_down(source1_key)
            self.send_key_down(source2_key)
            self._sleep_with_check(0.1, interval=0.05)
            self.send_key_up(source2_key)
            self.send_key_up(source1_key)
        except TaskDisabledException:
            try:
                self.send_key_up(source2_key)
            except Exception:
                pass
            try:
                self.send_key_up(source1_key)
            except Exception:
                pass
            raise
        except Exception as e:
            self.log_error(f"释放源器异常：{e}")
            try:
                self.send_key_up(source2_key)
            except Exception:
                pass
            try:
                self.send_key_up(source1_key)
            except Exception:
                pass

    # ---------- 宝箱检测 ----------

    @property
    def OPENED_CHEST_THRESHOLD(self):
        """'opened chest' 的识别阈值：读全局“宝箱阈值”，但不低于 OPENED_CHEST_MIN_THRESHOLD。"""
        try:
            cfg = self.get_global_config(chest_threshold_option)
            return max(float(cfg.get('宝箱阈值', 0.75)), self.OPENED_CHEST_MIN_THRESHOLD)
        except Exception:
            return self.OPENED_CHEST_MIN_THRESHOLD

    def _find_chest_stable(self, confirm_gap=0.3, max_attempts=3):
        """连续两帧检测到同一位置（±80px）才算有效。返回 (name, box) 或 (None, None)。"""
        for _ in range(max_attempts):
            self._check_stopped()
            frame = self.next_frame()
            if frame is None:
                self.sleep(0.2)
                continue
            height, width = frame.shape[:2]
            full_box = Box(0, 0, width, height)

            for name in self.CHEST_NAMES:
                threshold = self.CHEST_THRESHOLD
                result = self.find_feature(name, box=full_box, threshold=threshold)
                if not result:
                    continue

                first_box = result[0]
                first_center = first_box.center()
                self.sleep(confirm_gap)

                frame2 = self.next_frame()
                if frame2 is None:
                    break
                result2 = self.find_feature(name, box=full_box, threshold=threshold)
                if not result2:
                    self.log_debug(f"宝箱 {name} 二次确认失败")
                    break

                second_box = result2[0] if len(result2) == 1 else self._get_closest_box(result2, first_box)
                second_center = second_box.center()

                dx = abs(first_center[0] - second_center[0])
                dy = abs(first_center[1] - second_center[1])
                if dx < 80 and dy < 80:
                    return name, second_box

                self.log_info(f"宝箱 {name} 两次位置偏移过大")
                break

            self.sleep(0.5)

        return None, None

    def _find_any_chest_once(self):
        """单帧检测任一宝箱图标，返回 (name, box) 或 (None, None)。"""
        frame = self.next_frame()
        if frame is None:
            return None, None
        h, w = frame.shape[:2]
        full_box = Box(0, 0, w, h)
        for name in self.CHEST_NAMES:
            results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
            if results:
                return name, results[0]
        return None, None

    def _is_opened_chest_visible(self):
        return self.find_one('opened chest', threshold=self.OPENED_CHEST_THRESHOLD) is not None

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
                                    self.log_info(f"检测到开启文字：{box.name.strip()}")
                                    return True
                    except Exception as e:
                        self.log_debug(f"OCR检测异常: {e}")
                    last_ocr_time = current_time

                if current_time - last_key_press_time < key_press_interval:
                    self.sleep(0.05)
                    continue

                frame = self.next_frame()
                if frame is None:
                    continue

                height, width = frame.shape[:2]
                full_box = Box(0, 0, width, height)
                screen_center_x = width // 2

                current_chest = None
                if locked_chest_type:
                    results = self.find_feature(locked_chest_type, box=full_box, threshold=self.CHEST_THRESHOLD)
                    if results:
                        current_chest = results[0] if len(results) == 1 else self._get_closest_box(results, target_chest)

                if current_chest is None:
                    for name in self.CHEST_NAMES:
                        results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
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

                if current_chest is None:
                    # 这一帧没看到宝箱：先等待，连续 5 帧看不到才重新获取
                    self.sleep(0.1)
                    continue
                target_chest = current_chest
                chest_x, chest_y = target_chest.center()
                if not self._adjust_position(chest_x, chest_y, screen_center_x, width, height):
                    last_key_press_time = current_time

            self.log_error(f"接近宝箱超时，{max_walk_time}秒")
            return False
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error(f"接近宝箱 OCR 异常：{e}")
            return False

    # ---------- 孟章（前台）线程 ----------

    def _mengzhang_front_combat_loop(self, stop_event, center=None):
        """线程启动后先单击左键一次（在循环前面），本线程循环：
        技能键 → 等1.5s → 源器1 → 技能键 → 等3s → 长按左键60s → 源器2 → 等15.2s。

        center 由主线程提前算好传入：新线程自己截图会和主线程的宝箱检测抢资源，
        可能连续失败好几秒（日志里的 got no frame!），导致按 x 前出现明显延迟。
        """
        if center is None:
            center = self._get_screen_center()
        if center is None:
            self.log_error("孟章（前台）：无法获取屏幕帧")
            return
        center_x, center_y = center
        self.log_info(f"孟章（前台）：线程启动，中心坐标 {center_x},{center_y}")

        try:
            # 长按前先点一下，让游戏捕获鼠标，否则长按不生效
            self._click_to_activate(center_x, center_y)
            while not stop_event.is_set():
                skill_key = self._skill_key
                self.log_info(f"孟章（前台）：按技能键 [{skill_key}]，等待1.5秒")
                self.send_key(skill_key)

                start = time.time()
                while time.time() - start < 1.5:
                    if stop_event.is_set():
                        break
                    self._sleep_with_check(0.5, interval=0.2)
                if stop_event.is_set():
                    break

                # 按源器1，紧接着按技能键，然后等 3 秒
                source1_key = self._source_key
                self.log_info(f"孟章（前台）：按源器1 [{source1_key}]")
                self.send_key(source1_key)
                self.log_info(f"孟章（前台）：按技能键 [{skill_key}]，等待3秒")
                self.send_key(skill_key)

                start = time.time()
                while time.time() - start < 3:
                    if stop_event.is_set():
                        break
                    self._sleep_with_check(0.5, interval=0.2)
                if stop_event.is_set():
                    break

                self.log_info("孟章（前台）：长按左键60秒开始")
                try:
                    self.mouse_down(center_x, center_y, key='left')
                    start = time.time()
                    while time.time() - start < 60:
                        if stop_event.is_set():
                            break
                        self._sleep_with_check(1.0, interval=0.2)
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
                while time.time() - start < 15.2:
                    if stop_event.is_set():
                        break
                    self._sleep_with_check(0.2, interval=0.2)

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

    def _check_chest_after_auto_combat(self, chest_name, chest_box, timeout=5.0):
        """开启自动战斗后确认宝箱状态。

        判定只以 opened chest 图片为准：看到才算已打开；看不到就按“未打开”继续接近。
        不再用“宝箱图标消失”推断已打开。
        返回 (still_unopened, chest_name, chest_box)
        """
        start = time.time()
        while time.time() - start < timeout:
            self._check_stopped()
            if self._is_opened_chest_visible():
                self.log_info("孟章（前台）：检测到 opened chest，宝箱已打开")
                return False, chest_name, chest_box

            name_now, box_now = self._find_any_chest_once()
            if name_now is not None and box_now is not None:
                self.log_info(f"孟章（前台）：宝箱 {name_now} 仍在，继续接近流程")
                return True, name_now, box_now

            self.sleep(0.3)

        self.log_info(f"孟章（前台）：{timeout}秒内没看到 opened chest，按未打开处理，继续接近")
        return True, chest_name, chest_box

    # ---------- 十字搜索：寻找宝箱 ----------

    def _cross_search_chest(self):
        """十字移动的同时检测 chest1~chest5，找到就返回 (名称, Box)，否则返回 None。

        移动序列和多世界BOSS的十字搜索一致；检测只看单帧，不做二次确认。
        """
        self.log_info("启动十字搜索，检测 chest1~chest5")
        found_event = threading.Event()
        stop_event = threading.Event()
        found_chest = [None]

        def searcher():
            try:
                while not stop_event.is_set() and not found_event.is_set():
                    try:
                        frame = self.next_frame()
                        if frame is not None:
                            height, width = frame.shape[:2]
                            full_box = Box(0, 0, width, height)
                            for name in self.CHEST_NAMES:
                                results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
                                if results:
                                    found_chest[0] = (name, results[0])
                                    found_event.set()
                                    break
                        self._sleep_with_check(0.1)
                    except TaskDisabledException:
                        stop_event.set()
                        break
            except Exception as e:
                self.log_error(f"十字搜索检测线程异常: {e}")
                stop_event.set()

        def mover():
            try:
                moves = [
                    ('w', 5.0, 0.5),
                    ('s', 10.0, 0.5),
                    ('w', 5.0, 0.5),
                    ('a', 5.0, 0.5),
                    ('d', 10.0, 0.5),
                ]
                for key, down_time, after_sleep in moves:
                    if stop_event.is_set() or found_event.is_set():
                        break
                    self.log_debug(f"十字移动: 按{key} {down_time}秒")
                    try:
                        self.send_key_down(key)
                        press_start = time.time()
                        while time.time() - press_start < down_time:
                            if stop_event.is_set() or found_event.is_set():
                                break
                            self._sleep_with_check(0.05)
                    except TaskDisabledException:
                        stop_event.set()
                        break
                    finally:
                        self.send_key_up(key)
                    if after_sleep > 0:
                        self._sleep_with_check(after_sleep)
            except Exception as e:
                self.log_error(f"十字移动线程异常: {e}")
            finally:
                stop_event.set()

        t_search = threading.Thread(target=searcher, daemon=True, name='LHZZ-search')
        t_move = threading.Thread(target=mover, daemon=True, name='LHZZ-move')
        t_search.start()
        t_move.start()
        try:
            while t_search.is_alive() or t_move.is_alive():
                self._sleep_with_check(0.1)
                if found_event.is_set():
                    stop_event.set()
        finally:
            stop_event.set()
            t_search.join(timeout=3)
            t_move.join(timeout=3)
            if t_search.is_alive() or t_move.is_alive():
                self.log_error("十字搜索线程未能及时退出")

        if found_event.is_set():
            chest_name, chest_box = found_chest[0]
            self.log_info(f"十字搜索发现宝箱：{chest_name}")
            return found_chest[0]
        self.log_info("十字搜索结束，未发现宝箱")
        return None

    # ---------- 主流程 ----------

    def run(self):
        try:
            self.log_info("联合作战任务启动", notify=True)

            max_loops = self.config.get('循环次数', 10000)
            chest_timeout = self.config.get('宝箱等待超时', 180)
            oper1 = self.config.get('操作1', '前进')
            oper1_ms = self.config.get('操作1时间(ms)', 9000)
            oper2 = self.config.get('操作2', '不操作')
            oper2_ms = self.config.get('操作2时间(ms)', 5000)
            combat_mode = self.config.get('战斗方式', '自动战斗')
            use_vitality = self.config.get('活力开箱', False)

            self.log_info(f"配置：循环={max_loops}，战斗方式={combat_mode}，超时={chest_timeout}秒，"
                          f"操作1={oper1}/{oper1_ms}ms，操作2={oper2}/{oper2_ms}ms，活力开箱={use_vitality}，"
                          f"宝箱阈值={self.CHEST_THRESHOLD}")

            loop_count = 0

            while loop_count < max_loops:
                loop_count += 1
                self.log_info(f"第 {loop_count}/{max_loops} 次循环")

                if not self.is_main_page():
                    self.log_error("无法进入游戏主页面，跳过本次循环")
                    self.sleep(5)
                    continue

                if not self.enter_dungeon():
                    self.log_error("进入副本失败，跳过本次循环")
                    self.sleep(5)
                    continue

                # 进副本后画面尺寸已确定：这里先把屏幕中心算好，传给孟章线程。
                # 新线程自己截图会和主线程的宝箱检测抢资源，可能连续失败好几秒。
                dungeon_center = self._get_screen_center()

                # 进副本后依次执行操作1、操作2
                self._do_operation(oper1, oper1_ms, label='操作1')
                self._do_operation(oper2, oper2_ms, label='操作2')

                # 战斗
                combat_stop = None
                combat_thread = None
                next_source_time = None

                if combat_mode == '自动战斗':
                    self.log_info("开启自动战斗")
                    self.start_auto_combat()
                    self.sleep(2)
                    next_source_time = time.time()
                elif combat_mode == '孟章（前台）':
                    self.log_info("启动孟章（前台）战斗线程")
                else:
                    self.log_error(f"未知战斗方式: {combat_mode}")

                # 等待宝箱
                self.log_info(f"等待宝箱出现，超时{chest_timeout}秒")
                start_time = time.time()
                found_opened_chest = False
                found_unopened_chest = False
                chest_box = None
                chest_name = None

                try:
                    # 线程放在 try 内部启动：从启动到收尾之间无论哪一步抛异常，
                    # finally 都会给它发停止信号并 join，不会留下“野线程”。
                    if combat_mode == '孟章（前台）':
                        combat_stop = threading.Event()
                        combat_thread = threading.Thread(
                            target=self._mengzhang_front_combat_loop,
                            args=(combat_stop, dungeon_center),
                            daemon=True,
                            name='LHZZ-combat',
                        )
                        combat_thread.start()
                    while time.time() - start_time < chest_timeout:
                        self._check_stopped()

                        # 自动战斗模式：每 30.5s 释放一次源器
                        if combat_mode == '自动战斗' and next_source_time is not None:
                            if time.time() >= next_source_time:
                                self._press_source_1_and_2()
                                next_source_time = time.time() + self.AUTO_COMBAT_SOURCE_INTERVAL

                        frame = self.next_frame()
                        if frame is None:
                            self._check_stopped()
                            self.sleep(0.5)
                            continue

                        # 1. 已打开的宝箱
                        opened_box = self.find_one('opened chest', threshold=self.OPENED_CHEST_THRESHOLD)
                        if opened_box:
                            self.log_info("检测到已打开的宝箱")
                            found_opened_chest = True
                            break

                        # 2. chest1~chest5
                        name, box = self._find_chest_stable()
                        if box is not None:
                            chest_name = name
                            chest_box = box
                            self.log_info(f"检测到未打开的宝箱：{name}")
                            found_unopened_chest = True
                            break

                        self.sleep(0.5)
                finally:
                    if combat_stop is not None:
                        combat_stop.set()
                        if combat_thread is not None:
                            combat_thread.join(timeout=5)
                            if combat_thread.is_alive():
                                self.log_error("孟章（前台）：战斗线程未能在 5 秒内退出，可能有残留")
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
                        if still_unopened:
                            found_unopened_chest = True
                            found_opened_chest = False
                            self.log_info(f"孟章（前台）：宝箱 {chest_name} 仍未打开，继续接近流程")
                        else:
                            found_unopened_chest = False
                            found_opened_chest = True
                            self.log_info("孟章（前台）：确认宝箱已打开，跳过接近流程")

                # 开箱
                if found_opened_chest:
                    self.log_info("宝箱已打开，直接退出副本")
                elif found_unopened_chest and chest_box:
                    self.log_info(f"尝试接近并打开宝箱 {chest_name}")
                    remaining_time = chest_timeout - (time.time() - start_time)

                    if use_vitality:
                        self.log_info("活力开箱模式，OCR 检测开启")
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
                    self.log_error(f"{chest_timeout}秒内未找到宝箱")
                    # 超时后、退出副本前：可选执行一次十字搜索，找宝箱（chest1~chest5）
                    if self.config.get('十字搜索', True):
                        # 孟章模式是手动战斗，进十字搜索前先开自动战斗；
                        # 自动战斗模式本来就在打，不用再点
                        if combat_mode == '孟章（前台）':
                            self.log_info("孟章（前台）：十字搜索前先开启自动战斗")
                            self.start_auto_combat()
                            self.sleep(1)
                        self.log_info("执行十字搜索，寻找宝箱")
                        found = self._cross_search_chest()
                        if found is not None:
                            found_name, _ = found
                            self.log_info(f"十字搜索发现宝箱 {found_name}，开始接近")
                            # 自动战斗已开启，走近后游戏会自动开箱，这里只需要接近
                            if self.approach_chest(max_walk_time=60):
                                self.log_info("宝箱已打开")
                            else:
                                self.log_error("接近宝箱失败")
                        else:
                            self.log_info("十字搜索未发现宝箱，退出副本重试")
                    else:
                        self.log_info("未开启十字搜索，退出副本重试")

                self.log_info("退出副本")
                self.exit_dungeon()
                self.log_info(f"第 {loop_count} 次循环完成")

            self.log_info(f"联合作战任务结束，共完成 {loop_count} 次循环", notify=True)

        except TaskDisabledException:
            self.log_info("联合作战任务被用户手动停止")
        except Exception as e:
            self.log_error(f"任务执行过程中出现异常: {e}", exception=e, notify=True)
            self.screenshot("lianhezuozhan_error")
            raise