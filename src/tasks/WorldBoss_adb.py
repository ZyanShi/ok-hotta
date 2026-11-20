import time
import threading
import adbutils
from ok import Box, TaskDisabledException
from src.tasks.BaseQRSLTask import BaseQRSLTask


class WorldBossAdbTask(BaseQRSLTask):
    """ADB 模拟器世界BOSS任务（包含孟章战斗逻辑）"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_name = "模拟器"
        self.name = "世界BOSS"
        self.description = "ADB版本世界BOSS（含孟章战斗）"

        # ---------- UI 配置 ----------
        self.default_config.update({
            'BOSS选择': '罗贝拉格/朱厌',
            '等待超时': 900,
            '循环次数': 10000,
            '战斗方式': '孟章（前台）',
            '搜索模式': '南音传送',
            '传送至海嘉德': False,
            '提示信息': (
                "建议修改自动战斗索敌范围，文件在C:\\Users\\你的用户名\\AppData（文件夹上方查看，点击隐藏的项目）"
                "\\Local\\Hotta\\Saved\\Config\\WindowsNoEditor，找到GameUserSettings.ini文件，"
                "推荐将AutoCombatSearchRange的值设置为3000。"
                "南音传送需要将锚点锁定"
            ),
        })
        self.config_description = {
            'BOSS选择': '选择不同地图BOSS，请提前切换到对应的地图',
            '等待超时': '神临BOSS后未检测到BOSS的等待时间',
            '循环次数': '任务执行的最大循环次数',
            '战斗方式': '选择战斗模式（自动战斗/孟章前台）',
            '搜索模式': '选择宝箱搜索方式（南音传送/十字搜索）',
            '传送至海嘉德': '仅限亚夏或者维拉boss，每次开始前以前会传送至海嘉德',
            '提示信息': '索敌范围',
        }
        self.config_type['搜索模式'] = {'type': "drop_down", 'options': ['南音传送', '十字搜索']}
        self.config_type['战斗方式'] = {'type': "drop_down", 'options': ['自动战斗', '孟章（前台）']}
        self.config_type['BOSS选择'] = {
            'type': "drop_down",
            'options': [
                '罗贝拉格/朱厌',
                '阿波菲斯',
                '急冻机甲',
                '露琪亚',
                '巴巴罗萨',
                '伦迪尔',
                '幻蝎',
                '地驭',
                '幻蝎&地驭',
                '玛格玛（前台无遮挡）',
                '英招&地驭（格网启动）'
            ]
        }

        # ---------- 其他属性 ----------
        self.boss_image_map = {
            '罗贝拉格/朱厌': None,
            '阿波菲斯': 'Apophis',
            '幻蝎': 'huanxie',
            '急冻机甲': 'CryoLobster',
            '巴巴罗萨': 'Barbarossa',
            '露琪亚': 'Sweetie',
            '地驭': 'diyu',
            '伦迪尔': 'Lundir',
        }
        self.last_shenlin_time = 0
        self._openchest_box = None

    # ---------- ADB 长按方法 ----------
    def _adb_long_press(self, x, y, duration_ms):
        """通过 adbutils 执行 ADB 长按触摸"""
        try:
            adb = adbutils.AdbClient()
            devices = adb.device_list()
            if not devices:
                self.log_error("没有找到 ADB 设备")
                return False
            device = adb.device(devices[0].serial)
            cmd = f"input touchscreen swipe {x} {y} {x} {y} {duration_ms}"
            device.shell(cmd)
            self.log_debug("ADB 长按执行成功")
            return True
        except Exception as e:
            self.log_error(f"ADB 长按失败: {e}")
            return False

    # ---------- ADB 按键及移动方法 ----------
    def _adb_send_key(self, key: str) -> bool:
        key_map = {'f': 34, 'F': 34}
        code = key_map.get(key.lower())
        if code is None:
            self.log_error(f"未知按键: {key}")
            return False
        try:
            adb = adbutils.AdbClient()
            devices = adb.device_list()
            if not devices:
                self.log_error("没有找到 ADB 设备")
                return False
            device = adb.device(devices[0].serial)
            device.shell(f"input keyevent {code}")
            self.log_debug(f"ADB 发送按键: {key} (code {code})")
            return True
        except Exception as e:
            self.log_error(f"ADB 按键失败: {e}")
            return False

    def _send_key_safe(self, key: str, down_time: float = 0.1):
        dir_map = {
            'w': (385, 710),
            's': (385, 865),
            'a': (335, 750),
            'd': (520, 750)
        }
        if key in dir_map:
            ref_x, ref_y = dir_map[key]
            x, y = self._get_scaled_coordinates(ref_x, ref_y)
            self._adb_long_press(int(x), int(y), int(down_time * 1000))
        else:
            self._adb_send_key(key)

    def send_key_safe(self, key: str, down_time: float = 0.1):
        self._send_key_safe(key, down_time)

    # ---------- BOSS 状态检测 ----------
    def _is_boss_spawned(self):
        frame = self.frame
        if frame is None:
            return False
        x1, y1 = self._get_scaled_coordinates(1216, 157)
        x2, y2 = self._get_scaled_coordinates(758, 966)
        x3, y3 = self._get_scaled_coordinates(1260, 155)
        h, w = frame.shape[:2]
        if any([y1 >= h or x1 >= w, y2 >= h or x2 >= w, y3 >= h or x3 >= w]):
            return False
        pixel1 = frame[y1, x1]
        pixel2 = frame[y2, x2]
        pixel3 = frame[y3, x3]
        green1 = (pixel1[0] == 161 and pixel1[1] == 209 and pixel1[2] == 47)
        green3 = (pixel3[0] == 161 and pixel3[1] == 209 and pixel3[2] == 47)
        white2 = (pixel2[0] == 255 and pixel2[1] == 255 and pixel2[2] == 255)
        return green1 and green3 and white2

    def _check_boss_ui_disappeared(self):
        frame = self.frame
        if frame is None:
            return False
        x1, y1 = self._get_scaled_coordinates(1216, 157)
        x2, y2 = self._get_scaled_coordinates(758, 966)
        x3, y3 = self._get_scaled_coordinates(1260, 155)
        h, w = frame.shape[:2]
        if y1 >= h or x1 >= w or y2 >= h or x2 >= w or y3 >= h or x3 >= w:
            return False
        pixel1 = frame[y1, x1]
        pixel2 = frame[y2, x2]
        pixel3 = frame[y3, x3]
        green1 = (pixel1[0] == 161 and pixel1[1] == 209 and pixel1[2] == 47)
        white = (pixel2[0] == 255 and pixel2[1] == 255 and pixel2[2] == 255)
        green3 = (pixel3[0] == 161 and pixel3[1] == 209 and pixel3[2] == 47)
        return not (green1 or white or green3)

    # ---------- 孟章操作循环 ----------
    def _mengzhang_combat_loop(self, stop_event, boss_spawned, boss_dead):
        long_press_x, long_press_y = self._get_scaled_coordinates(1565, 850)
        source1_x, source1_y = self._get_scaled_coordinates(1760, 620)
        source2_x, source2_y = self._get_scaled_coordinates(1760, 485)

        while not stop_event.is_set() and not boss_dead.is_set():
            try:
                self.log_debug("孟章：长按 (1565,850) 50秒")
                self._adb_long_press(int(long_press_x), int(long_press_y), 50000)
                if stop_event.is_set() or boss_dead.is_set():
                    break
                self.log_debug("孟章：点击源器2")
                self.click(source2_x, source2_y, after_sleep=10)
                if stop_event.is_set() or boss_dead.is_set():
                    break
                self.log_debug("孟章：点击源器1")
                self.click(source1_x, source1_y, after_sleep=2)
            except TaskDisabledException:
                self.log_info("孟章操作线程收到禁用信号，退出")
                break
            except Exception as e:
                self.log_error(f"孟章操作循环异常: {e}")
                break
        self.log_info("孟章操作循环结束")

    # ---------- BOSS 状态监测线程 ----------
    def _monitor_boss_status(self, stop_event, boss_spawned, boss_dead, timeout):
        start_time = time.time()
        boss_spawned_occurred = False
        while not stop_event.is_set() and not boss_dead.is_set():
            if not boss_spawned_occurred and (time.time() - start_time > timeout):
                self.log_info(f"监测超时，未检测到BOSS刷新")
                stop_event.set()
                break
            if not boss_spawned_occurred:
                if self._is_boss_spawned():
                    boss_spawned_occurred = True
                    boss_spawned.set()
                    self.log_info("监测到BOSS刷新！")
                else:
                    self.sleep(0.2)
                    continue
            else:
                if self._check_boss_ui_disappeared():
                    boss_dead.set()
                    self.log_info("监测到BOSS死亡！")
                    break
                self.sleep(0.2)
        self.log_info("BOSS状态监测线程结束")

    # ---------- 判断主页面 ----------
    def 判断主页面(self, timeout=60):
        self.log_info(f"等待主页面出现，超时 {timeout} 秒...")
        start_time = time.time()
        target_bgr = (237, 166, 62)
        tolerance = 30
        while time.time() - start_time < timeout:
            self._check_stopped()
            frame = self.frame
            if frame is None:
                self.sleep(0.5)
                continue
            x, y = self._get_scaled_coordinates(80, 72)
            height, width = frame.shape[:2]
            if y >= height or x >= width:
                self.sleep(0.5)
                continue
            pixel_bgr = frame[y, x]
            if self._color_similar(pixel_bgr, target_bgr, tolerance):
                self.log_info("检测到主页面")
                return True
            self.sleep(0.5)
        self.log_error("等待主页面超时")
        return False

    # ---------- 打开地图（使用坐标点击） ----------
    def _open_map_and_enter_boss(self):
        self.log_info("打开地图")
        x1, y1 = self._get_scaled_coordinates(195, 210)
        self._click_safe(x1, y1, after_sleep=3)
        self.log_info("进入世界BOSS页面")
        x2, y2 = self._get_scaled_coordinates(350, 940)
        self._click_safe(x2, y2, after_sleep=2)
        return True

    # ---------- 辅助方法 ----------
    def _wait_and_click_feature(self, feature_name, timeout, after_sleep=0, box=None):
        found_box = self.wait_feature(feature_name, time_out=timeout, raise_if_not_found=False, box=box)
        if found_box:
            self.log_info(f"点击 [{feature_name}]")
            self._click_box_safe(found_box)
            if after_sleep > 0:
                self.sleep(after_sleep)
            return True
        self.log_error(f"等待 [{feature_name}] 超时")
        return False

    def _click_safe(self, x, y, **kwargs):
        return super()._click_safe(x, y, **kwargs)

    # ---------- 选择BOSS ----------
    def _select_boss_by_config(self, boss_choice=None, loop_count=None):
        if boss_choice is None:
            boss_choice = self.config.get('BOSS选择', '罗贝拉格/朱厌')

        if boss_choice == '英招&地驭（格网启动）':
            if loop_count is None:
                loop_count = 1
            if loop_count % 2 == 1:
                x, y = self._get_scaled_coordinates(835, 930)
                self.log_info(f"英招&地驭：奇数循环，点击坐标 ({x}, {y})")
            else:
                x, y = self._get_scaled_coordinates(1810, 925)
                self.log_info(f"英招&地驭：偶数循环，点击坐标 ({x}, {y})")
            self._click_safe(x, y, after_sleep=1)
            return True

        if boss_choice == '玛格玛（前台无遮挡）':
            self.log_info("BOSS选择为 [玛格玛]，执行特殊操作")
            x, y = self._get_scaled_coordinates(1730, 935)
            self.move(x, y)
            self.scroll(x, y, -5)
            self.sleep(0.5)
            self._click_safe(x, y, after_sleep=1)
            return True

        image_name = self.boss_image_map.get(boss_choice)
        if image_name is None:
            self.log_info(f"BOSS选择为 [{boss_choice}]，无需额外操作")
            return True

        self.log_info(f"等待并点击BOSS图标 [{image_name}]")
        frame = self.frame
        if frame is None:
            self.log_error("无法获取屏幕帧")
            return False
        h, w = frame.shape[:2]
        full_box = Box(0, 0, w, h)
        return self._wait_and_click_feature(image_name, timeout=10, after_sleep=1, box=full_box)

    # ---------- 等待返回主页面并激活战斗 ----------
    def _wait_main_page_and_activate(self):
        self.log_info("等待返回游戏主页面...")
        if not self.判断主页面(timeout=60):
            return False

        self.log_info("主页面已返回，等待2秒稳定...")
        self.sleep(2)

        x1, y1 = self._get_scaled_coordinates(1760, 620)
        self.log_info("点击源器键1")
        self._click_safe(x1, y1, after_sleep=0.2)

        x2, y2 = self._get_scaled_coordinates(1460, 990)
        self.log_info("切换武器")
        self._click_safe(x2, y2, after_sleep=0.2)

        x3, y3 = self._get_scaled_coordinates(385, 710)
        self.log_info("长按前进3秒")
        success = self._adb_long_press(int(x3), int(y3), 3000)
        if not success:
            self.log_error("ADB 长按前进失败，继续执行")

        combat_mode = self.config.get('战斗方式', '孟章（前台）')
        if combat_mode == '自动战斗':
            self.log_info("开启自动战斗")
            self.start_auto_combat()
        elif combat_mode == '孟章（前台）':
            self.log_info("孟章（前台）模式，不开启自动战斗")
        else:
            self.log_info("未知战斗方式，跳过开启自动战斗")
        return True

    # ==================== 南音传送及相关方法 ====================
    def _nanyin_teleport_search(self):
        self.log_info("启动南音传送搜索")
        # 打开地图（点击坐标）
        map_x, map_y = self._get_scaled_coordinates(195, 210)
        self._click_safe(map_x, map_y, after_sleep=2)

        # 获取当前屏幕帧并创建全屏 Box
        frame = self.frame
        if frame is None:
            self.log_error("南音传送：无法获取屏幕帧")
            return False
        h, w = frame.shape[:2]
        full_box = Box(0, 0, w, h)

        # 限定 nanyintp 搜索区域
        x1, y1 = self._get_scaled_coordinates(845, 300)
        x2, y2 = self._get_scaled_coordinates(1230, 630)
        search_box = Box(x1, y1, x2 - x1, y2 - y1)

        self.log_info("在限定区域内等待 nanyintp 出现，超时10秒，阈值0.7")
        start_time = time.time()
        nanyin_box = None
        while time.time() - start_time < 10:
            self._check_stopped()
            results = self.find_feature('nanyintp', box=search_box, threshold=0.7)
            if results:
                nanyin_box = results[0]
                break
            self.sleep(0.5)

        if not nanyin_box:
            self.log_info("南音传送：未找到 nanyintp，点击屏幕中心后继续后续步骤")
            self.click(0.5, 0.5)
            self.sleep(1)
        else:
            self._click_box_safe(nanyin_box, after_sleep=1)

        # OCR 识别虚空渊流
        x1, y1 = self._get_scaled_coordinates(1370, 570)
        x2, y2 = self._get_scaled_coordinates(1490, 620)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)
        ocr_results = self.wait_ocr(box=ocr_box, match="虚空渊流", time_out=5, raise_if_not_found=False)
        if not ocr_results:
            self.log_error("南音传送：未找到虚空渊流，继续尝试下一步")
        else:
            self._click_box_safe(ocr_results[0], after_sleep=1)

        # 点击 tp 和 sure（全屏搜索）
        if not self._wait_and_click_feature('tp', timeout=10, after_sleep=1, box=full_box):
            self.log_error("南音传送：未找到 tp 图片")
            return False

        if not self._wait_and_click_feature('sure', timeout=10, after_sleep=8, box=full_box):
            self.log_error("南音传送：未找到 sure 图片")
            return False

        if not self._wait_for_target_text(timeout=60):
            self.log_error("南音传送：超时未检测到目标文字")
            return False

        if not self._phase_chest_pickup(chest_box=None):
            self.log_error("南音传送：宝箱拾取失败")
            return False

        self.log_info("南音传送搜索成功完成")
        return True

    def _wait_for_target_text(self, timeout=60):
        self.log_info(f"等待目标文字出现，超时{timeout}秒")
        x1, y1 = self._get_scaled_coordinates(1110, 520)
        x2, y2 = self._get_scaled_coordinates(1280, 575)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                ocr_results = self.ocr(box=ocr_box, target_height=540)
                if ocr_results:
                    for box in ocr_results:
                        text = box.name.strip()
                        if ('太极匣' in text) or ('高级密码箱' in text):
                            self.log_info(f"检测到目标文字: {text}")
                            return True
            except Exception as e:
                self.log_debug(f"OCR检测异常: {e}")
            self.sleep(0.5)
        return False

    def _phase_chest_pickup(self, chest_box=None):
        self.log_info("进入宝箱拾取阶段")

        if chest_box is None:
            self.log_info("未传入宝箱，尝试自动获取")
            chest_box = self.wait_any_chest(time_out=10)
            if chest_box is None:
                self.log_error("无法获取宝箱")
                return False

        max_retries = 3
        for retry in range(max_retries):
            if not self.approach_bosschest(max_walk_time=60, target_chest=chest_box):
                self.log_error(f"接近宝箱失败 (第{retry + 1}次)")
                return False

            self.sleep(1)
            # 检查目标文字
            x1, y1 = self._get_scaled_coordinates(1110, 520)
            x2, y2 = self._get_scaled_coordinates(1280, 575)
            ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)
            try:
                ocr_results = self.ocr(box=ocr_box, target_height=540)
                text_found = False
                target_box = None
                if ocr_results:
                    for box in ocr_results:
                        text = box.name.strip()
                        if ('太极匣' in text) or ('高级密码箱' in text):
                            text_found = True
                            target_box = box
                            break
                if text_found and target_box:
                    self.log_info("检测到目标文字，点击打开宝箱")
                    self._click_box_safe(target_box, after_sleep=1)
                    self.sleep(1)
                else:
                    self.log_info("目标文字未出现，重新接近宝箱")
                    continue
            except Exception as e:
                self.log_debug(f"OCR确认或点击异常: {e}，继续重试")
                continue

            # 全屏搜索 openchest1/openchest2
            self.log_info("等待并点击 openchest1/openchest2 图片（全屏搜索）")
            frame = self.frame
            if frame is None:
                self.log_error("无法获取屏幕帧，跳过 openchest 点击")
                continue
            h, w = frame.shape[:2]
            full_box = Box(0, 0, w, h)

            start_time = time.time()
            timeout = 5
            clicked_openchest = False
            while time.time() - start_time < timeout:
                for name in ['openchest1', 'openchest2']:
                    boxes = self.find_feature(name, box=full_box, threshold=0.7)
                    if boxes:
                        self.log_info(f"找到 {name} 图片，点击")
                        self._click_box_safe(boxes[0], after_sleep=0.5)
                        clicked_openchest = True
                        break
                if clicked_openchest:
                    break
                self.sleep(0.2)

            if not clicked_openchest:
                self.log_info("未找到 openchest 图片，继续执行下一步（可能宝箱已打开）")  # 原 log_warning 改为 log_info

            # 领取奖励
            self.log_info("点击领取奖励坐标 (1255,575)")
            x, y = self._get_scaled_coordinates(1255, 575)
            self._click_safe(x, y, after_sleep=7)

            self.log_info("宝箱拾取和领取完成")
            return True

        self.log_error("多次尝试后拾取失败")
        return False

    # ---------- approach_bosschest（实时跟踪） ----------
    def approach_bosschest(self, max_walk_time=60, target_chest=None):
        if target_chest is None:
            target_chest = self.wait_any_chest(time_out=30)
            if target_chest is None:
                self.log_error("approach_bosschest: 30秒内未发现任何宝箱")
                return False

        start_time = time.time()
        last_key_press_time = 0
        key_press_interval = 0.15

        x1, y1 = self._get_scaled_coordinates(1110, 520)
        x2, y2 = self._get_scaled_coordinates(1280, 575)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)

        try:
            while time.time() - start_time < max_walk_time:
                current_time = time.time()

                # 检查目标文字
                target_detected = False
                try:
                    ocr_results = self.ocr(box=ocr_box, target_height=540)
                    if ocr_results:
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

                # 搜索所有宝箱
                all_chests = []
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=0.7)
                    if results:
                        all_chests.extend(results)

                current_chest = None
                if all_chests:
                    if target_chest:
                        current_chest = self._get_closest_box(all_chests, target_chest)
                    else:
                        current_chest = all_chests[0]
                    target_chest = current_chest
                else:
                    self.log_debug("未发现宝箱，尝试重新获取")
                    current_chest = self._reacquire_chest()
                    if current_chest is None:
                        self.log_error("approach_bosschest: 无法重新获取宝箱")
                        return False
                    target_chest = current_chest

                chest_x, chest_y = target_chest.center()
                if not self._adjust_position(chest_x, chest_y, screen_center_x, width, height):
                    last_key_press_time = current_time

                self.sleep(0.01)

            self.log_error(f"approach_bosschest: 超时{max_walk_time}秒未检测到目标文字")
            return False

        except TaskDisabledException:
            self.log_info("approach_bosschest 被用户手动停止")
            raise

    def _sleep_with_events(self, seconds, stop_event, found_event):
        interval = 0.2
        elapsed = 0
        while elapsed < seconds:
            if stop_event.is_set() or found_event.is_set():
                break
            self.sleep(min(interval, seconds - elapsed))
            elapsed += interval

    # ==================== 十字搜索（适配 ADB） ====================
    def _cross_search(self):
        """十字搜索（适配 ADB 长按移动）"""
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
                            self.sleep(0.033)
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
                    ('s', 5.0, 0.5),   # 向后5秒
                    ('w', 10.0, 0.5),  # 向前10秒
                    ('s', 5.0, 0.5),   # 向后5秒
                    ('a', 5.0, 0.5),   # 向左5秒
                    ('d', 10.0, 0.5),  # 向右10秒
                ]
                for key, down_time, after_sleep in moves:
                    if stop_event.is_set() or found_event.is_set():
                        break
                    self.log_debug(f"十字移动: 按{key} {down_time}秒")
                    try:
                        self.send_key_safe(key, down_time=down_time)
                    except TaskDisabledException:
                        self.log_debug("十字移动线程检测到任务停止")
                        stop_event.set()
                        break
                    if after_sleep > 0:
                        self._sleep_with_events(after_sleep, stop_event, found_event)
            except Exception as e:
                self.log_error(f"十字移动线程异常: {e}")
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

    # ---------- 统一搜索入口 ----------
    def cross_search(self):
        """
        统一搜索入口 - 支持南音传送和十字搜索
        """
        mode = self.config.get('搜索模式', '南音传送')
        if mode == '南音传送':
            return self._nanyin_teleport_search()
        elif mode == '十字搜索':
            return self._cross_search()
        else:
            self.log_error(f"未知搜索模式: {mode}")
            return None

    # ---------- 宝箱相关辅助 ----------
    def wait_any_chest(self, time_out=30):
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
        for _ in range(10):
            frame = self.frame
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=0.7)
                    if results:
                        return results[0]
            self.sleep(0.5)
        return None

    def _get_closest_box(self, boxes, target_box):
        last_center = target_box.center()
        distances = [abs(r.center()[0] - last_center[0]) + abs(r.center()[1] - last_center[1]) for r in boxes]
        closest_idx = distances.index(min(distances))
        return boxes[closest_idx]

    # ---------- 主逻辑 ----------
    def run(self):
        try:
            max_loops = self.config.get('循环次数', 10000)
            loop_count = 0
            combat_mode = self.config.get('战斗方式', '孟章（前台）')

            while loop_count < max_loops:
                loop_count += 1
                self.log_info(f"--- 第 {loop_count}/{max_loops} 次循环 ---")
                loop_start_time = time.time()

                # ---------- 传送至海嘉德（修改：使用点击地图，替代 send_key('m')） ----------
                if self.config.get('传送至海嘉德', False):
                    self.log_info("执行传送至海嘉德")
                    # 点击地图按钮打开地图（使用与 _open_map_and_enter_boss 相同的坐标）
                    map_x, map_y = self._get_scaled_coordinates(195, 210)
                    self._click_safe(map_x, map_y, after_sleep=2)
                    # 点击传送坐标
                    x, y = self._get_scaled_coordinates(540, 940)
                    self._click_safe(x, y, after_sleep=10)
                    self.log_info("等待传送后回到主页面...")
                    if not self.判断主页面(timeout=30):
                        self.log_error("传送至海嘉德后未回到主页面，跳过本次循环")
                        self.sleep(5)
                        continue
                    self.log_info("已回到主页面，继续执行")
                # ----------------------------------------------------------------

                if not self.判断主页面(timeout=60):
                    self.log_error("未进入主页面，跳过本次循环")
                    self.sleep(2)
                    continue

                if not self._open_map_and_enter_boss():
                    self.log_error("打开地图或进入BOSS失败")
                    self.sleep(2)
                    continue

                boss_choice = self.config.get('BOSS选择', '罗贝拉格/朱厌')
                if boss_choice == '幻蝎&地驭':
                    if loop_count % 2 == 1:
                        current_boss = '幻蝎'
                    else:
                        current_boss = '地驭'
                    self.log_info(f"组合模式，本次选择 [{current_boss}]")
                    if not self._select_boss_by_config(boss_choice=current_boss):
                        self.log_error(f"BOSS [{current_boss}] 选择失败")
                        self.sleep(5)
                        continue
                elif boss_choice == '英招&地驭（格网启动）':
                    if not self._select_boss_by_config(boss_choice, loop_count=loop_count):
                        self.log_error("英招&地驭选择失败")
                        self.sleep(5)
                        continue
                else:
                    if not self._select_boss_by_config():
                        self.log_error("BOSS选择失败")
                        self.sleep(5)
                        continue

                frame = self.frame
                if frame is None:
                    self.log_error("无法获取屏幕帧")
                    self.sleep(5)
                    continue
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                if not self._wait_and_click_feature('gotoboss', timeout=30, after_sleep=0, box=full_box):
                    self.log_error("前往BOSS按钮未出现")
                    self.sleep(5)
                    continue

                if not self._wait_and_click_feature('shenlin', timeout=30, after_sleep=8, box=full_box):
                    self.log_error("神临按钮未出现")
                    self.sleep(5)
                    continue

                if not self._wait_main_page_and_activate():
                    self.log_error("激活战斗失败")
                    self.sleep(5)
                    continue

                self.last_shenlin_time = time.time()

                if combat_mode == '自动战斗':
                    self.log_info("自动战斗模式（暂未实现）")
                    self.sleep(2)

                elif combat_mode == '孟章（前台）':
                    self.log_info("启动孟章战斗模式")
                    stop_event = threading.Event()
                    boss_spawned = threading.Event()
                    boss_dead = threading.Event()

                    t_combat = threading.Thread(
                        target=self._mengzhang_combat_loop,
                        args=(stop_event, boss_spawned, boss_dead),
                        daemon=True
                    )
                    t_combat.start()
                    self.log_info("孟章操作线程已启动，等待5秒后启动监控线程...")
                    self.sleep(5)

                    wait_timeout = self.config.get('等待超时', 900)
                    t_monitor = threading.Thread(
                        target=self._monitor_boss_status,
                        args=(stop_event, boss_spawned, boss_dead, wait_timeout),
                        daemon=True
                    )
                    t_monitor.start()
                    self.log_info("监控线程已启动，两者并行运行")

                    start_monitor = time.time()
                    while not boss_dead.is_set():
                        if not boss_spawned.is_set() and (time.time() - start_monitor > wait_timeout):
                            self.log_info(f"监测超时，未检测到BOSS刷新，终止")
                            stop_event.set()
                            break
                        self.sleep(0.2)

                    stop_event.set()
                    t_combat.join(timeout=1)
                    t_monitor.join(timeout=1)

                    if not boss_dead.is_set():
                        self.log_error("未检测到BOSS死亡，跳过本次循环")
                        self.sleep(5)
                        continue
                    else:
                        self.log_info("BOSS已死亡，进入拾取流程")
                        mode = self.config.get('搜索模式', '南音传送')
                        if mode == '南音传送':
                            success = self._nanyin_teleport_search()
                            if not success:
                                self.log_error("南音传送流程失败，跳过本次循环")
                                self.sleep(5)
                                continue
                        else:
                            # 十字搜索或其它
                            chest = self.wait_any_chest(time_out=5)
                            if not chest:
                                self.log_info("5秒内未找到宝箱，启动搜索")
                                chest = self.cross_search()
                            if not chest:
                                self.log_error("无法找到宝箱，跳过本次循环")
                                self.sleep(5)
                                continue

                            if not self._phase_chest_pickup(chest):
                                self.log_error("宝箱拾取或领取失败")
                                self.sleep(5)
                                continue

                else:
                    self.log_error(f"未知战斗方式: {combat_mode}")
                    self.sleep(5)
                    continue

                elapsed = time.time() - loop_start_time
                self.log_info(f"本次循环耗时 {elapsed:.1f} 秒")
                self.sleep(2)

            self.log_info("===== 世界BOSS（ADB）任务结束 =====", notify=True)

        except TaskDisabledException:
            self.log_info("任务被用户手动停止")
        except Exception as e:
            self.log_error(f"任务异常: {e}", notify=True)
            self.screenshot("worldboss_adb_error")
            raise