import time
import threading
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask
from src.config import key_config_option


class WorldBossTask(BaseQRSLTask):
    """世界BOSS自动化任务"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "世界BOSS"
        self.group_name = "精炼强化"
        self.description = "自动挑战世界BOSS并拾取宝箱"
        self.group_icon = FluentIcon.MARKET
        self.icon = FluentIcon.MARKET

        self.default_config.update({
            'BOSS选择': '罗贝拉格/朱厌/伦迪尔',
            '等待超时': 900,
            '循环次数': 10000,
            '搜索模式': '米字搜索',
            '提示信息': (
                "建议修改自动战斗索敌范围，文件在C:\\Users\\你的用户名\\AppData（文件夹上方查看，点击隐藏的项目）"
                "\\Local\\Hotta\\Saved\\Config\\WindowsNoEditor，找到GameUserSettings.ini文件，"
                "推荐将AutoCombatSearchRange的值设置为3000。"
                "南音传送需要将锚点锁定，锁定图标不得与人物图标重叠，不然使用其它搜索模式。"
            ),
        })
        self.config_description = {
            'BOSS选择': '选择不同地图BOSS，请提前切换到对应的地图',
            '等待超时': '神临BOSS后未检测到BOSS的等待时间',
            '循环次数': '任务执行的最大循环次数',
            '搜索模式': '选择宝箱搜索方式',
            '提示信息': '索敌范围',
        }
        self.config_type['搜索模式'] = {'type': "drop_down", 'options': ['米字搜索', '十字搜索', '南音传送']}
        self.config_type['BOSS选择'] = {
            'type': "drop_down",
            'options': ['罗贝拉格/朱厌/伦迪尔', '阿波菲斯', '急冻机甲', '露琪亚', '巴巴罗萨', '幻蝎']
        }
        self._source_key = self._get_source_key()
        self.boss_image_map = {
            '罗贝拉格/朱厌/伦迪尔': None,
            '阿波菲斯': 'Apophis',
            '幻蝎': 'huanxie',
            '急冻机甲': 'CryoLobster',
            '巴巴罗萨': 'Barbarossa',
            '露琪亚': 'Sweetie',
        }
        self.last_shenlin_time = 0

    def _get_source_key(self):
        """获取全局源器键配置"""
        try:
            global_config = self.get_global_config(key_config_option)
            return global_config.get('源器键', 'x')
        except Exception:
            self.log_debug("读取全局源器键失败，使用默认值 'x'")
            return 'x'

    def _open_map_and_enter_boss(self):
        """打开地图并进入世界BOSS界面"""
        self.log_info("按M打开地图")
        self.send_key('m')
        self.sleep(2)
        click_x, click_y = self._get_scaled_coordinates(350, 940)
        self.log_info(f"点击世界BOSS入口，缩放后坐标: ({click_x}, {click_y})")
        self._click_safe(click_x, click_y, after_sleep=2)
        return True

    def _select_boss_by_config(self):
        """根据配置选择对应的BOSS（点击图片或执行特殊操作）"""
        boss_choice = self.config.get('BOSS选择', '罗贝拉格/朱厌/伦迪尔')

        # 普通BOSS：通过图片识别
        image_name = self.boss_image_map.get(boss_choice)
        if image_name is None:
            # 罗贝拉格/朱厌/伦迪尔 无需额外操作
            self.log_info(f"BOSS选择为 [{boss_choice}]，无需额外操作")
            return True

        self.log_info(f"BOSS选择为 [{boss_choice}]，等待图片 [{image_name}]")
        return self._wait_and_click_feature(image_name, timeout=10, after_sleep=1)

    def _wait_and_click_feature(self, feature_name, timeout, after_sleep=0):
        """等待特征图片出现并点击"""
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
        """等待返回主页面并激活自动战斗"""
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
        return True

    def wait_for_main_page_color(self, timeout):
        """等待主页面颜色特征出现"""
        start = time.time()
        while time.time() - start < timeout:
            if self.check_main_page_color():
                return True
            self.sleep(0.5)
        return False

    def check_main_page_color(self):
        """检查主页面颜色点是否匹配"""
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
        """判断首领是否刷新（基于两点颜色检测）"""
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
        """等待首领提示UI消失（双点检测）"""
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
            self.sleep(0.2)

        self.log_error(f"等待首领提示消失超时（{timeout}秒）")
        return False

    def wait_any_chest(self, time_out=30):
        """等待任意宝箱出现，返回第一个找到的宝箱框"""
        self.log_debug(f"等待任意宝箱出现，超时{time_out}秒，阈值0.7")
        start = time.time()
        while time.time() - start < time_out:
            frame = self.frame
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=0.7)
                    if results:
                        self.log_debug(f"找到宝箱: {name}")
                        return results[0]
            self.sleep(0.5)
        return None

    def _reacquire_chest(self):
        """重新获取宝箱（多次尝试）"""
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

    # ==================== 搜索方法 ====================
    def _cross_search(self):
        """十字搜索宝箱（移动+搜索）"""
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
                        for _ in range(3):
                            if stop_event.is_set():
                                break
                            self.sleep(0.033)  # 可能抛出 TaskDisabledException
                    except TaskDisabledException:
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
                            self.sleep(0.05)
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
                stop_event.set()  # 移动序列结束，通知搜索线程停止

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
            self.log_info("十字搜索被用户手动停止")
            stop_event.set()
            t1.join(timeout=1)
            t2.join(timeout=1)
            raise

        t1.join()
        t2.join()

        if found_event.is_set():
            self.log_info("十字搜索成功找到宝箱")
            return chest_box[0]
        self.log_info("十字移动序列结束，未找到宝箱")
        return None

    def _mi_search(self):
        """米字搜索宝箱（更复杂的移动序列）"""
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

    def _nanyin_teleport_search(self):
        """南音传送搜索：使用地图传送直接到达宝箱位置"""
        self.log_info("启动南音传送搜索")

        # 1. 按M打开地图
        self.send_key('m')
        self.sleep(2)

        # 2. 手动循环查找 nanyintp（与 NanyinTestTask 完全一致，阈值0.7，超时15秒）
        self.log_info("等待 nanyintp 出现，超时15秒，阈值0.7")
        start_time = time.time()
        nanyin_box = None
        while time.time() - start_time < 15:
            self._check_stopped()
            frame = self.frame
            if frame is None:
                self.sleep(0.5)
                continue
            h, w = frame.shape[:2]
            full_box = Box(0, 0, w, h)
            results = self.find_feature('nanyintp', box=full_box, threshold=0.7)
            if results:
                nanyin_box = results[0]
                break
            self.sleep(0.5)

        if not nanyin_box:
            self.log_error("南音传送：未找到 nanyintp")
            return None
        self._click_box_safe(nanyin_box, after_sleep=1)

        # 3. 等待并点击 OCR "虚空渊流"（区域固定，需缩放）
        x1, y1 = self._get_scaled_coordinates(1370, 570)
        x2, y2 = self._get_scaled_coordinates(1490, 620)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)
        ocr_results = self.wait_ocr(box=ocr_box, match="虚空渊流", time_out=10, raise_if_not_found=False)
        if not ocr_results:
            self.log_error("南音传送：未找到虚空渊流")
            return None
        self._click_box_safe(ocr_results[0], after_sleep=1)

        # 4. 等待并点击 tp 图片（超时10秒）
        if not self._wait_and_click_feature('tp', timeout=10, after_sleep=1):
            self.log_error("南音传送：未找到 tp 图片")
            return None

        # 5. 等待并点击 sure 图片（超时10秒，点击后等待8秒加载）
        if not self._wait_and_click_feature('sure', timeout=10, after_sleep=8):
            self.log_error("南音传送：未找到 sure 图片")
            return None

        # 6. 传送完成，等待宝箱出现（超时30秒）
        chest = self.wait_any_chest(time_out=30)
        if not chest:
            self.log_error("南音传送：传送后未找到宝箱")
        return chest

    def cross_search(self):
        """根据配置选择搜索方式"""
        mode = self.config.get('搜索模式', '十字搜索')
        if mode == '南音传送':
            return self._nanyin_teleport_search()
        elif mode == '十字搜索':
            return self._cross_search()
        else:  # 米字搜索
            return self._mi_search()

    def _sleep_with_events(self, seconds, stop_event, found_event):
        """可被事件中断的sleep"""
        interval = 0.2
        elapsed = 0
        while elapsed < seconds:
            if stop_event.is_set() or found_event.is_set():
                break
            self.sleep(min(interval, seconds - elapsed))
            elapsed += interval

    def _recover_character_state(self):
        """尝试恢复角色状态（按下S键）"""
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
        """检查角色状态是否正常（通过颜色点）"""
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
        """接近宝箱并检测目标文字"""
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

        try:
            while time.time() - start_time < max_walk_time:
                current_time = time.time()

                # 执行 OCR 检测
                target_detected = False
                try:
                    ocr_results = self.ocr(box=ocr_box, target_height=540)
                    if ocr_results:
                        texts = [box.name.strip() for box in ocr_results]
                        self.log_debug(f"OCR识别到: {texts}")
                        for box in ocr_results:
                            text = box.name.strip()
                            if ('太极匣' in text) or ('高级密码箱' in text):
                                target_detected = True
                                break
                except Exception as e:
                    self.log_debug(f"OCR检测异常: {e}")

                if target_detected:
                    self.log_info("检测到目标文字，接近成功")
                    return True

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
        """拾取宝箱阶段（包含移动）"""
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

        self.log_info("等待1秒后检测角色状态...")
        self.sleep(1)

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

    def _quick_chest_pickup(self):
        """快速拾取宝箱（不移动角色），只按 F 并检测 openchest 图片"""
        self.log_info("快速拾取宝箱（不移动）")
        start_time = time.time()
        timeout = 10  # 超时10秒
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
        self.log_error("快速拾取超时：10秒内未出现openchest图片")
        return False

    def _claim_reward(self):
        """领取奖励"""
        x, y = self._get_scaled_coordinates(1255, 575)
        self.log_info(f"点击奖励坐标 ({x}, {y})")
        self._click_safe(x, y, after_sleep=7)
        return True

    def run(self):
        """任务主循环"""
        try:

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

                # 自动战斗后立即寻找宝箱2秒
                self.log_info("自动战斗已开启，立即寻找宝箱2秒...")
                chest = self.wait_any_chest(time_out=2)
                if chest:
                    self.log_info("2秒内找到宝箱，关闭自动战斗并直接拾取")
                    self.start_auto_combat()

                    if not self._phase_chest_pickup(chest):
                        self.log_error("宝箱拾取失败，跳过奖励领取")
                    else:
                        if not self._claim_reward():
                            self.log_error("奖励领取失败")
                    elapsed = time.time() - loop_start_time
                    self.log_info(f"本次循环总耗时 {elapsed:.1f}秒")
                    continue

                # 没找到宝箱，进入BOSS监测阶段
                self.log_info("5秒内未找到宝箱，开始监测BOSS刷新")
                monitor_result = self._monitor_boss_spawn_only(wait_timeout)

                if monitor_result == 'boss_found':
                    self.log_info("首领已刷新，进入阶段B")
                    if not self._phase_b_wait_boss_ui_disappear():
                        self.log_error("首领提示未消失，跳过本次循环")
                        self.sleep(5)
                        continue

                    self.start_auto_combat()

                    search_mode = self.config.get('搜索模式', '十字搜索')

                    if search_mode == '南音传送':
                        # 南音传送模式：直接执行搜索（内部包含等待宝箱）
                        chest = self.cross_search()
                        if not chest:
                            self.log_error("南音传送未找到宝箱，跳过本次循环")
                            self.sleep(5)
                            continue
                        # 使用快速拾取（不移动）
                        if not self._quick_chest_pickup():
                            self.log_error("快速拾取失败")
                            self.sleep(5)
                            continue
                        # 领取奖励
                        if not self._claim_reward():
                            self.log_error("奖励领取失败")
                            self.sleep(5)
                    else:
                        # 十字或米字搜索：原逻辑
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

                    elapsed = time.time() - loop_start_time
                    self.log_info(f"本次循环总耗时 {elapsed:.1f}秒")
                    continue

                elif monitor_result == 'timeout':
                    self.log_error("BOSS刷新监测超时，跳过本次循环")
                    self.sleep(5)
                    continue

                elapsed = time.time() - loop_start_time
                self.log_info(f"本次循环总耗时 {elapsed:.1f}秒")

            self.log_info(f"===== 世界BOSS任务结束，共完成 {loop_count} 次循环 =====", notify=True)

        except TaskDisabledException:
            self.log_info("世界BOSS任务被用户手动停止")
        except Exception as e:
            self.log_error(f"世界BOSS任务异常: {e}", notify=True)
            self.screenshot("worldboss_error")
            raise