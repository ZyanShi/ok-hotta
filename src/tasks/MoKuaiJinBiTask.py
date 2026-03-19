import time
import threading
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask
from src.config import key_config_option


class MoKuaiJinBiTask(BaseQRSLTask):
    """模块金币·世界BOSS自动化任务"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "模块金币"
        self.group_name = "精炼强化"
        self.description = "自动挑战世界BOSS并拾取宝箱"
        self.group_icon = FluentIcon.MARKET
        self.icon = FluentIcon.MARKET

        self.default_config.update({
            'BOSS选择': '罗贝拉格/朱厌',
            '等待超时': 900,
            '循环次数': 10000,
            '搜索模式': '十字搜索',
            '提示信息': (
                "建议修改自动战斗索敌范围，文件在C:\\Users\\你的用户名\\AppData（文件夹上方查看，点击隐藏的项目）"
                "\\Local\\Hotta\\Saved\\Config\\WindowsNoEditor，找到GameUserSettings.ini文件，"
                "推荐将AutoCombatSearchRange的值设置为3000。"
            ),
        })
        self.config_description = {
            'BOSS选择': '选择不同地图BOSS，请提前切换到对应的地图',
            '等待超时': '神临BOSS后未检测到BOSS的等待时间',
            '循环次数': '任务执行的最大循环次数',
            '搜索模式': '选择宝箱搜索方式',
            '提示信息': '索敌范围',
        }
        self.config_type['搜索模式'] = {'type': "drop_down", 'options': ['十字搜索', '米字搜索']}
        self.config_type['BOSS选择'] = {
            'type': "drop_down",
            'options': ['罗贝拉格/朱厌', '阿波菲斯', '幻蝎']
        }
        self._source_key = self._get_source_key()
        self.boss_image_map = {
            '罗贝拉格/朱厌': None,
            '阿波菲斯': 'Apophis',
            # 幻蝎无需图片，直接点击坐标
        }
        self.last_shenlin_time = 0

    def _get_source_key(self):
        try:
            global_config = self.get_global_config(key_config_option)
            return global_config.get('源器键', 'x')
        except Exception:
            self.log_debug("读取全局源器键失败，使用默认值 'x'")
            return 'x'

    def _open_map_and_enter_boss(self):
        self.log_info("按M打开地图")
        self.send_key('m')
        self.sleep(2)
        click_x, click_y = self._get_scaled_coordinates(350, 940)
        self.log_info(f"点击世界BOSS入口，缩放后坐标: ({click_x}, {click_y})")
        self._click_safe(click_x, click_y, after_sleep=2)
        return True

    def _select_boss_by_config(self):
        boss_choice = self.config.get('BOSS选择', '罗贝拉格/朱厌')

        if boss_choice == '幻蝎':
            x, y = self._get_scaled_coordinates(1340, 920)
            self.log_info(f"幻蝎: 点击固定坐标 ({x}, {y})")
            self._click_safe(x, y, after_sleep=1)
            return True

        image_name = self.boss_image_map.get(boss_choice)
        if image_name is None:
            self.log_info(f"BOSS选择为 [{boss_choice}]，无需额外操作")
            return True

        self.log_info(f"BOSS选择为 [{boss_choice}]，等待图片 [{image_name}]")
        return self._wait_and_click_feature(image_name, timeout=10, after_sleep=1)

    def _wait_and_click_feature(self, feature_name, timeout, after_sleep=0):
        box = self.wait_feature(feature_name, time_out=timeout, raise_if_not_found=False)
        if box:
            self.log_info(f"找到并点击 [{feature_name}]")
            self._click_box_safe(box)
            if after_sleep > 0:
                self.sleep(after_sleep)
            return True
        self.log_error(f"等待 [{feature_name}] 超时 ({timeout}秒)")
        return False

    def _wait_main_page_and_activate(self):
        self.log_info("等待返回游戏主页面...")
        if not self.wait_for_main_page_color(timeout=60):
            return False
        self.log_info(f"按源器键 [{self._source_key}]")
        self.send_key_down(self._source_key)
        self.sleep(0.5)
        self.send_key_up(self._source_key)
        self.sleep(0.2)
        self.log_info("前进2.5秒")
        self.send_key_safe('w', down_time=2.5)
        self.log_info("开启自动战斗")
        self.start_auto_combat()
        self.sleep(1)
        return True

    def wait_for_main_page_color(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            if self.check_main_page_color():
                return True
            self.sleep(0.5)
        return False

    def check_main_page_color(self):
        frame = self.frame
        if frame is None:
            return False
        x, y = self._get_scaled_coordinates(*self.MAIN_PAGE_COORDS)
        if y >= frame.shape[0] or x >= frame.shape[1]:
            return False
        pixel = frame[y, x]
        return self._color_similar(pixel, self.TARGET_COLOR_BGR, tolerance=30)

    def _monitor_boss_spawn_only(self, timeout):
        """仅监测首领刷新提示，不识别宝箱。返回 'boss_found' 或 'timeout'"""
        self.log_info(f"进入BOSS刷新监测阶段，超时{timeout}秒")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._is_boss_spawned():
                self.log_info("检测到首领刷新！")
                return 'boss_found'
            self.sleep(2)
        self.log_info("BOSS刷新监测阶段超时")
        return 'timeout'

    def _is_boss_spawned(self):
        frame = self.frame
        if frame is None:
            return False
        x1, y1 = self._get_scaled_coordinates(1216, 157)
        x2, y2 = self._get_scaled_coordinates(22, 410)
        h, w = frame.shape[:2]
        if y1 >= h or x1 >= w or y2 >= h or x2 >= w:
            return False
        pixel1 = frame[y1, x1]
        pixel2 = frame[y2, x2]
        color1_match = (pixel1[0] == 161 and pixel1[1] == 209 and pixel1[2] == 47)
        color2_match = (pixel2[0] == 237 and pixel2[1] == 166 and pixel2[2] == 62)
        return color1_match and color2_match

    def _phase_b_wait_boss_ui_disappear(self, timeout=600):
        self.log_info(f"等待首领提示消失，超时{timeout}秒（单次判定，双点检测）...")
        start = time.time()
        while time.time() - start < timeout:
            frame = self.frame
            if frame is None:
                self.sleep(0.5)
                continue
            x1, y1 = self._get_scaled_coordinates(1216, 157)
            x2, y2 = self._get_scaled_coordinates(22, 410)
            h, w = frame.shape[:2]
            if y1 < h and x1 < w and y2 < h and x2 < w:
                pixel1 = frame[y1, x1]
                pixel2 = frame[y2, x2]

                spawned1 = (pixel1[0] == 161 and pixel1[1] == 209 and pixel1[2] == 47)
                spawned2 = (pixel2[0] == 237 and pixel2[1] == 166 and pixel2[2] == 62)

                if not (spawned1 or spawned2):
                    self.log_info("检测到两个点均不匹配存在色，首领提示已消失")
                    return True
                else:
                    self.log_debug("至少一个点仍匹配存在色，继续等待")
            self.sleep(2)

        self.log_error(f"等待首领提示消失超时（{timeout}秒）")
        return False

    def wait_any_chest(self, time_out=30):
        self.log_debug(f"等待任意宝箱出现，超时{time_out}秒，阈值0.6")
        start = time.time()
        while time.time() - start < time_out:
            frame = self.frame
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=0.6)
                    if results:
                        self.log_debug(f"找到宝箱: {name}")
                        return results[0]
            self.sleep(0.5)
        return None

    def _reacquire_chest(self):
        for _ in range(10):
            frame = self.frame
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=0.6)
                    if results:
                        return results[0]
            self.sleep(0.5)
        return None

    # ==================== 修改后的十字搜索 ====================
    def _cross_search(self):
        self.log_info("启动十字搜索，宝箱阈值0.6")
        found_event = threading.Event()
        stop_event = threading.Event()
        chest_box = [None]

        def searcher():
            try:
                while not stop_event.is_set() and not found_event.is_set():
                    try:
                        frame = self.frame
                        if frame is not None:
                            h, w = frame.shape[:2]
                            full_box = Box(0, 0, w, h)
                            for name in self.CHEST_NAMES:
                                results = self.find_feature(name, box=full_box, threshold=0.6)
                                if results:
                                    chest_box[0] = results[0]
                                    self.log_info(f"十字搜索找到宝箱: {name}")
                                    found_event.set()
                                    break
                        # 每次循环后 sleep 一小段时间，sleep 会检查任务是否被停止
                        for _ in range(3):
                            if stop_event.is_set():
                                break
                            self.sleep(0.033)   # 可能抛出 TaskDisabledException
                    except TaskDisabledException:
                        # 任务被停止，设置停止事件并退出线程
                        self.log_debug("十字搜索线程检测到任务停止")
                        stop_event.set()
                        break
            except Exception as e:
                self.log_error(f"十字搜索线程异常: {e}")
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
                            self.sleep(0.05)   # 可能抛出 TaskDisabledException
                    except TaskDisabledException:
                        self.log_debug("十字移动线程检测到任务停止")
                        stop_event.set()
                        break
                    finally:
                        self.send_key_up(key)
                    if after_sleep > 0:
                        self._sleep_with_events(after_sleep, stop_event, found_event)
            except Exception as e:
                self.log_error(f"十字移动线程异常: {e}")
                stop_event.set()
            finally:
                stop_event.set()   # 移动序列结束，通知搜索线程停止

        t1 = threading.Thread(target=searcher, daemon=True)
        t2 = threading.Thread(target=mover, daemon=True)
        t1.start()
        t2.start()

        try:
            # 主线程循环等待，定期检查停止信号
            while t1.is_alive() or t2.is_alive():
                self.sleep(0.1)   # 关键：这里会抛出 TaskDisabledException
                if found_event.is_set():
                    # 找到宝箱，提前停止移动线程
                    stop_event.set()
        except TaskDisabledException:
            self.log_info("十字搜索被用户手动停止")
            stop_event.set()
            # 等待线程结束，但不再阻塞响应
            t1.join(timeout=1)
            t2.join(timeout=1)
            raise   # 重新抛出异常，让上层捕获

        # 确保线程完全结束
        t1.join()
        t2.join()

        if found_event.is_set():
            self.log_info("十字搜索成功找到宝箱")
            return chest_box[0]
        self.log_info("十字移动序列结束，未找到宝箱")
        return None

    # ==================== 修改后的米字搜索 ====================
    def _mi_search(self):
        self.log_info("启动米字搜索，宝箱阈值0.6，执行完整移动序列")
        found_event = threading.Event()
        stop_event = threading.Event()
        chest_box = [None]

        def searcher():
            try:
                while not stop_event.is_set() and not found_event.is_set():
                    try:
                        frame = self.frame
                        if frame is not None:
                            h, w = frame.shape[:2]
                            full_box = Box(0, 0, w, h)
                            for name in self.CHEST_NAMES:
                                results = self.find_feature(name, box=full_box, threshold=0.6)
                                if results:
                                    chest_box[0] = results[0]
                                    self.log_info(f"米字搜索找到宝箱: {name}")
                                    found_event.set()
                                    break
                        for _ in range(3):
                            if stop_event.is_set():
                                break
                            self.sleep(0.033)
                    except TaskDisabledException:
                        self.log_debug("米字搜索线程检测到任务停止")
                        stop_event.set()
                        break
            except Exception as e:
                self.log_error(f"米字搜索线程异常: {e}")
                stop_event.set()

        def mover():
            try:
                moves = [
                    ('w', 5.0, 0.5),
                    ('s', 10.0, 0.5),
                    ('w', 5.0, 0.5),
                    ('a', 5.0, 0.5),
                    ('d', 10.0, 0.5),
                    ('a', 5.0, 0.5),
                    ('a', 'w', 5.0, 0.5),
                    ('s', 'd', 10.0, 0.5),
                    ('a', 'w', 5.0, 0.5),
                    ('w', 'd', 5.0, 0.5),
                    ('a', 's', 10.0, 0.5),
                ]
                for move in moves:
                    if stop_event.is_set() or found_event.is_set():
                        break
                    if len(move) == 3:
                        key, down_time, after_sleep = move
                        self.log_debug(f"米字移动: 按{key} {down_time}秒")
                        try:
                            self.send_key_down(key)
                            press_start = time.time()
                            while time.time() - press_start < down_time:
                                if stop_event.is_set() or found_event.is_set():
                                    break
                                self.sleep(0.05)
                        except TaskDisabledException:
                            self.log_debug("米字移动线程检测到任务停止")
                            stop_event.set()
                            break
                        finally:
                            self.send_key_up(key)
                        if after_sleep > 0:
                            self._sleep_with_events(after_sleep, stop_event, found_event)
                    elif len(move) == 4:
                        key1, key2, down_time, after_sleep = move
                        self.log_debug(f"米字移动: 同时按{key1}+{key2} {down_time}秒")
                        try:
                            self.send_key_down(key1)
                            self.send_key_down(key2)
                            press_start = time.time()
                            while time.time() - press_start < down_time:
                                if stop_event.is_set() or found_event.is_set():
                                    break
                                self.sleep(0.05)
                        except TaskDisabledException:
                            self.log_debug("米字移动线程检测到任务停止")
                            stop_event.set()
                            break
                        finally:
                            self.send_key_up(key1)
                            self.send_key_up(key2)
                        if after_sleep > 0:
                            self._sleep_with_events(after_sleep, stop_event, found_event)
            except Exception as e:
                self.log_error(f"米字移动线程异常: {e}")
                stop_event.set()
            finally:
                stop_event.set()

        t1 = threading.Thread(target=searcher, daemon=True)
        t2 = threading.Thread(target=mover, daemon=True)
        t1.start()
        t2.start()

        try:
            while t1.is_alive() or t2.is_alive():
                self.sleep(0.1)
                if found_event.is_set():
                    stop_event.set()
        except TaskDisabledException:
            self.log_info("米字搜索被用户手动停止")
            stop_event.set()
            t1.join(timeout=1)
            t2.join(timeout=1)
            raise

        t1.join()
        t2.join()

        if found_event.is_set():
            self.log_info("米字搜索成功找到宝箱")
            return chest_box[0]
        self.log_info("米字移动序列结束，未找到宝箱")
        return None

    # ========================================================

    def cross_search(self):
        mode = self.config.get('搜索模式', '十字搜索')
        if mode == '十字搜索':
            return self._cross_search()
        return self._mi_search()

    def _sleep_with_events(self, seconds, stop_event, found_event):
        interval = 0.2
        elapsed = 0
        while elapsed < seconds:
            if stop_event.is_set() or found_event.is_set():
                break
            self.sleep(min(interval, seconds - elapsed))
            elapsed += interval

    def _recover_character_state(self):
        self.log_info("角色状态异常，尝试按S键恢复，超时150秒")
        start_time = time.time()
        timeout = 150
        while time.time() - start_time < timeout:
            if self._is_character_state_normal():
                self.log_info("状态已恢复正常")
                return True
            self.log_debug("按下S键 (0.2秒)")
            self.send_key_safe('s', down_time=0.2)
            self.sleep(0.2)
        self.log_error(f"状态恢复失败，超时{timeout}秒")
        return False

    def _is_character_state_normal(self):
        frame = self.frame
        if frame is None:
            return False
        x, y = self._get_scaled_coordinates(1805, 698)
        h, w = frame.shape[:2]
        if y >= h or x >= w:
            return False
        pixel = frame[y, x]
        target_bgr = (254, 195, 57)
        diff_sum = abs(int(pixel[0]) - target_bgr[0]) + \
                   abs(int(pixel[1]) - target_bgr[1]) + \
                   abs(int(pixel[2]) - target_bgr[2])
        return diff_sum <= 50

    def approach_bosschest(self, max_walk_time=60, target_chest=None):
        locked_chest_type = None
        if target_chest is not None:
            self.log_debug(f"approach_bosschest: 使用已有宝箱 {target_chest.name}")
            locked_chest_type = target_chest.name
        else:
            target_chest = self.wait_any_chest(time_out=30)
            if target_chest is None:
                self.log_error("approach_bosschest: 30秒内未发现任何宝箱")
                return False

        start_time = time.time()
        chest_disappear_count = 0
        last_key_press_time = 0
        key_press_interval = 0.15

        x1, y1 = self._get_scaled_coordinates(1110, 520)
        x2, y2 = self._get_scaled_coordinates(1280, 575)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)

        ocr_confirm_start = None
        STABLE_TIME = 0.3

        try:
            while time.time() - start_time < max_walk_time:
                current_time = time.time()

                target_detected = False
                try:
                    ocr_results = self.ocr(box=ocr_box, target_height=540)
                    if ocr_results:
                        texts = [box.name for box in ocr_results]
                        self.log_debug(f"OCR识别到: {texts}")
                        for box in ocr_results:
                            text = box.name.strip()
                            if ('太极匣' in text) or ('高级密码箱' in text):
                                target_detected = True
                                break
                except Exception as e:
                    self.log_debug(f"OCR检测异常: {e}")

                if target_detected:
                    if ocr_confirm_start is None:
                        ocr_confirm_start = current_time
                        self.log_debug("首次检测到目标文字，开始计时")
                    elif current_time - ocr_confirm_start >= STABLE_TIME:
                        self.log_info(f"目标文字稳定出现{STABLE_TIME}秒，接近成功")
                        return True
                else:
                    if ocr_confirm_start is not None:
                        self.log_debug("目标文字消失，重置计时")
                        ocr_confirm_start = None

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
                    results = self.find_feature(locked_chest_type, box=full_box, threshold=0.6)
                    if results:
                        current_chest = results[0] if len(results) == 1 else self._get_closest_box(results,
                                                                                                   target_chest)

                if current_chest is None:
                    for name in self.CHEST_NAMES:
                        results = self.find_feature(name, box=full_box, threshold=0.6)
                        if results:
                            locked_chest_type = name
                            current_chest = results[0] if len(results) == 1 else self._get_closest_box(results,
                                                                                                       target_chest)
                            break

                if current_chest is None:
                    chest_disappear_count += 1
                    if chest_disappear_count >= 5:
                        current_chest = self._reacquire_chest()
                        if current_chest is None:
                            self.log_error("approach_bosschest: 无法重新获取宝箱")
                            return False
                else:
                    chest_disappear_count = 0

                if current_chest is not None:
                    target_chest = current_chest
                    chest_x, chest_y = target_chest.center()
                    if not self._adjust_position(chest_x, chest_y, screen_center_x, width, height):
                        last_key_press_time = current_time
                else:
                    self.sleep(0.1)

            self.log_error(f"approach_bosschest: 超时{max_walk_time}秒未检测到目标文字")
            return False

        except TaskDisabledException:
            self.log_info("approach_bosschest 被用户手动停止")
            raise

    def _phase_chest_pickup(self, chest_box=None):
        self.log_info("进入宝箱拾取阶段")

        max_retries = 3
        for retry in range(max_retries):
            if not self.approach_bosschest(max_walk_time=60, target_chest=chest_box):
                self.log_error(f"接近宝箱失败 (第{retry + 1}次)")
                return False

            self.sleep(1)
            frame = self.frame
            if frame is None:
                self.log_debug("无法获取画面，继续重试")
                continue

            x1, y1 = self._get_scaled_coordinates(1110, 520)
            x2, y2 = self._get_scaled_coordinates(1280, 575)
            ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)

            try:
                ocr_results = self.ocr(box=ocr_box, target_height=540)
                text_found = False
                if ocr_results:
                    for box in ocr_results:
                        text = box.name.strip()
                        if ('太极匣' in text) or ('高级密码箱' in text):
                            text_found = True
                            break
                if text_found:
                    self.log_info("目标文字仍存在，继续拾取流程")
                    break
                else:
                    self.log_info("目标文字已消失，重新接近宝箱")
            except Exception as e:
                self.log_debug(f"OCR确认异常: {e}，继续重试")
                continue
        else:
            self.log_error("多次接近后文字仍未稳定存在，拾取失败")
            return False

        self.log_info("等待2秒后检测角色状态...")
        self.sleep(2)

        if self._is_character_state_normal():
            self.log_info("角色状态正常，继续拾取")
        else:
            if not self._recover_character_state():
                self.log_error("角色状态恢复失败，放弃本次拾取")
                return False
            self.log_info("状态恢复完成")

        start_time = time.time()
        timeout = 10
        self.log_info("开始连续按F并检测openchest1/2，超时10秒，阈值0.6")

        while time.time() - start_time < timeout:
            self.send_key_safe('f', down_time=0.05)
            frame = self.frame
            if frame is not None:
                for name in ['openchest1', 'openchest2']:
                    boxes = self.find_feature(name, threshold=0.6)
                    if boxes:
                        box = boxes[0]
                        self.log_info(f"检测到 {name} 图片，立即点击")
                        self._click_box_safe(box)
                        self.sleep(1)
                        self._openchest_box = box
                        return True
            self.sleep(0.1)

        self.log_error("拾取超时：10秒内未出现openchest图片")
        return False

    def _claim_reward(self):
        x, y = self._get_scaled_coordinates(1255, 575)
        self.log_info(f"点击奖励坐标 ({x}, {y})")
        self._click_safe(x, y, after_sleep=7)
        return True

    def run(self):
        try:
            self.log_info("===== 模块金币任务启动 =====", notify=True)
            wait_timeout = self.config.get('等待超时', 900)
            max_loops = self.config.get('循环次数', 10000)
            loop_count = 0

            while loop_count < max_loops:
                loop_count += 1
                self.log_info(f"--- 第 {loop_count}/{max_loops} 次循环开始 ---")
                loop_start_time = time.time()

                if loop_count > 1 and self.last_shenlin_time != 0:
                    elapsed = time.time() - self.last_shenlin_time
                    if elapsed < 60:
                        wait_time = 60 - elapsed
                        self.log_info(f"神临冷却中，已过 {elapsed:.1f}秒，需等待 {wait_time:.1f}秒")
                        self.sleep(wait_time)

                if not self.is_main_page():
                    self.log_error("无法进入游戏主页面，跳过本次循环")
                    self.sleep(5)
                    continue

                if not self._open_map_and_enter_boss():
                    self.log_error("进入世界BOSS界面失败")
                    self.sleep(5)
                    continue

                if not self._select_boss_by_config():
                    self.log_error("BOSS选择图片等待超时，跳过本次循环")
                    self.sleep(5)
                    continue

                if not self._wait_and_click_feature('gotoboss', timeout=30, after_sleep=0):
                    self.sleep(5)
                    continue

                if not self._wait_and_click_feature('shenlin', timeout=30, after_sleep=8):
                    self.sleep(5)
                    continue

                if not self._wait_main_page_and_activate():
                    self.log_error("启动战斗流程失败")
                    self.sleep(5)
                    continue

                self.last_shenlin_time = time.time()

                # ===== 新增：自动战斗后立即寻找宝箱5秒 =====
                self.log_info("自动战斗已开启，立即寻找宝箱5秒...")
                chest = self.wait_any_chest(time_out=5)
                if chest:
                    self.log_info("5秒内找到宝箱，关闭自动战斗并直接拾取")
                    # 再次点击自动战斗按钮关闭自动战斗
                    self.start_auto_combat()
                    self.sleep(1)

                    if not self._phase_chest_pickup(chest):
                        self.log_error("宝箱拾取失败，跳过奖励领取")
                    else:
                        if not self._claim_reward():
                            self.log_error("奖励领取失败")
                    # 本次循环结束，直接进入下一次循环
                    elapsed = time.time() - loop_start_time
                    self.log_info(f"本次循环总耗时 {elapsed:.1f}秒")
                    continue  # 跳过后续BOSS监测

                # 没找到宝箱，进入BOSS监测阶段（仅监测BOSS刷新）
                self.log_info("5秒内未找到宝箱，开始监测BOSS刷新")
                monitor_result = self._monitor_boss_spawn_only(wait_timeout)

                if monitor_result == 'boss_found':
                    self.log_info("首领已刷新，进入阶段B")
                    if not self._phase_b_wait_boss_ui_disappear():
                        self.log_error("首领提示未消失，跳过本次循环")
                        self.sleep(5)
                        continue

                    # 重新开启自动战斗（可能被UI打断）
                    self.start_auto_combat()
                    # 先等待5秒看宝箱是否出现
                    chest = self.wait_any_chest(time_out=5)
                    if not chest:
                        self.log_info("5秒内未找到宝箱，启动搜索")
                        chest = self.cross_search()
                    if not chest:
                        self.log_error("无法找到宝箱，跳过本次循环")
                        self.sleep(5)
                        continue

                    if not self._phase_chest_pickup(chest):
                        self.log_error("宝箱拾取失败，跳过奖励领取")
                        self.sleep(5)
                        continue

                    if not self._claim_reward():
                        self.log_error("奖励领取失败")
                        self.sleep(5)

                elif monitor_result == 'timeout':
                    self.log_error("BOSS刷新监测超时，跳过本次循环")
                    self.sleep(5)
                    continue

                elapsed = time.time() - loop_start_time
                self.log_info(f"本次循环总耗时 {elapsed:.1f}秒")

            self.log_info(f"===== 模块金币任务结束，共完成 {loop_count} 次循环 =====", notify=True)

        except TaskDisabledException:
            self.log_info("模块金币任务被用户手动停止")
        except Exception as e:
            self.log_error(f"模块金币任务异常: {e}", notify=True)
            self.screenshot("mokuai_jinbi_error")
            raise