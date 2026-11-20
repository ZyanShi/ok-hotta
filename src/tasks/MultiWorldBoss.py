import time
import threading
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask


class MultiWorldBossTask(BaseQRSLTask):
    """多世界BOSS自动化任务（支持轮换/专注模式）"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "多世界BOSS"
        self.group_name = "精炼强化"
        self.description = "自动轮换/专注挑战多个世界BOSS并拾取宝箱"
        self.group_icon = FluentIcon.MARKET
        self.icon = FluentIcon.MARKET

        boss_options = [
            '罗贝拉格', '阿波菲斯', '急冻机甲', '露琪亚', '巴巴罗萨',
            '伦迪尔', '玛格玛', '科尔顿', '朱厌', '玄鸦', '饕餮',
            '飞廉', '英招', '阵点球', '幻蝎', '地驭', '捍卫者',
            '皇后虫', '灾厄5号',
        ]
        search_options = ['米字搜索', '十字搜索', '南音传送']
        combat_options = ['自动战斗', '孟章（前台）', '雅诺（前台）', '孟章', '雅诺', '吸血鬼', '地缚灵']
        loop_mode_options = ['专注','轮换']
        teleport_options = ['不传送', '海嘉德', '九域', '格网', '洛克哈特']

        self.default_config.update({
            '循环模式': '专注',
            '前进时间': 2000,
            '等待超时': 60,
            '战斗方式': '自动战斗',
            '武器键': '2',

            'BOSS1选择': '罗贝拉格',
            'BOSS1搜索模式': '十字搜索',
            'BOSS1传送': '不传送',

            '启用BOSS2': False,
            'BOSS2选择': '罗贝拉格',
            'BOSS2搜索模式': '十字搜索',
            'BOSS2传送': '不传送',

            '启用BOSS3': False,
            'BOSS3选择': '罗贝拉格',
            'BOSS3搜索模式': '十字搜索',
            'BOSS3传送': '不传送',

            '提示信息': (
                "建议修改自动战斗索敌范围，文件在C:\\Users\\你的用户名\\AppData"
                "\\Local\\Hotta\\Saved\\Config\\WindowsNoEditor，找到GameUserSettings.ini文件，"
                "推荐将AutoCombatSearchRange的值设置为3000。"
                "南音传送需要将锚点锁定。"
            ),
        })

        self.config_description = {
            '循环模式': '轮换：依次打每个BOSS；专注：当前BOSS等待超时后才切换下一个',
            '前进时间': '进入战斗后按 W 前进的持续时间（毫秒）',
            '等待超时': '等待BOSS刷新的超时时间（秒）',
            '战斗方式': '选择战斗模式',
            '武器键': '切换武器按键',

            'BOSS1选择': '选择第一个BOSS',
            'BOSS1搜索模式': '宝箱搜索方式',
            'BOSS1传送': '选择传送目的地',

            '启用BOSS2': '是否启用第二个BOSS',
            'BOSS2选择': '选择第二个BOSS',
            'BOSS2搜索模式': '宝箱搜索方式',
            'BOSS2传送': '选择传送目的地',

            '启用BOSS3': '是否启用第三个BOSS',
            'BOSS3选择': '选择第三个BOSS',
            'BOSS3搜索模式': '宝箱搜索方式',
            'BOSS3传送': '选择传送目的地',

            '提示信息': '索敌范围',
        }

        self.config_type['循环模式'] = {'type': "drop_down", 'options': loop_mode_options}
        self.config_type['战斗方式'] = {'type': "drop_down", 'options': combat_options}
        for i in [1, 2, 3]:
            self.config_type[f'BOSS{i}选择'] = {'type': "drop_down", 'options': boss_options}
            self.config_type[f'BOSS{i}搜索模式'] = {'type': "drop_down", 'options': search_options}
            self.config_type[f'BOSS{i}传送'] = {'type': "drop_down", 'options': teleport_options}

        self.boss_image_map = {
            '罗贝拉格': None, '阿波菲斯': 'Apophis', '急冻机甲': 'CryoLobster',
            '露琪亚': 'Sweetie', '巴巴罗萨': 'Barbarossa', '伦迪尔': 'Lundir',
            '玛格玛': 'magema', '科尔顿': 'keerdun', '朱厌': 'Zhuyan',
            '玄鸦': 'Xuanya', '饕餮': 'taotie', '飞廉': 'Feilian',
            '英招': 'yingzhao', '阵点球': 'Zhendianqiu', '幻蝎': 'huanxie',
            '地驭': 'diyu', '捍卫者': 'hanweizhe', '皇后虫': 'huanghouchong',
            '灾厄5号': 'zaiewuhao',
        }
        self.last_shenlin_time = 0

        # ---- 工作线程生命周期管理：防止“停止后线程仍在跑 / 重启后双开” ----
        self._worker_lock = threading.Lock()
        self._round_generation = 0
        self._round_stop_event = None
        self._worker_threads = []

    # ---------- 工作线程生命周期 ----------

    def _begin_worker_round(self, stop_event):
        """登记本轮的停止事件，返回本轮代际号（代际号一变，所有旧线程立即失效）。"""
        with self._worker_lock:
            self._round_generation += 1
            self._round_stop_event = stop_event
            self._worker_threads = []
            return self._round_generation

    def _register_worker_thread(self, thread):
        with self._worker_lock:
            self._worker_threads.append(thread)

    def _should_stop(self, *events, generation=None):
        """停止判定：代际过期（任务重启过）或任一事件被 set。

        这里刻意不依赖 self._check_stopped / self.sleep：
        战斗线程必须在 time.sleep 期间也能被唤醒，否则用户停止后会残留。
        """
        if generation is not None and generation != self._round_generation:
            return True
        return any(event is not None and event.is_set() for event in events)

    def _wait_event(self, seconds, *events, interval=0.2, generation=None):
        """可中断等待，返回 True 表示收到停止信号。

        用 time.sleep 而不是 self.sleep，避免 TaskDisabledException 在“左键已按下、
        尚未抬起”的窗口里抛出，从而漏掉 mouse_up。
        """
        deadline = time.time() + seconds
        while True:
            if self._should_stop(*events, generation=generation):
                return True
            remaining = deadline - time.time()
            if remaining <= 0:
                return False
            time.sleep(min(interval, remaining))

    def _release_mouse_safely(self):
        """无条件抬起左键，避免停止后鼠标一直处于按下状态。"""
        try:
            self.mouse_up(key='left')
        except Exception as e:
            self.log_debug(f"释放左键失败: {e}")

    def _request_stop_workers(self):
        """只发停止信号、不阻塞，可从任意线程（含 GUI 线程）调用。

        不在这里抬起鼠标：GUI 线程注入输入有风险（可能落到 ok 自己的窗口上），
        工作线程收到信号后会在 0.2 秒内自己 mouse_up，执行器线程也会兜底抬键。
        """
        with self._worker_lock:
            stop_event = self._round_stop_event
            self._round_generation += 1
        if stop_event is not None:
            stop_event.set()

    def _stop_worker_threads(self, timeout=5.0):
        """发停止信号并等待线程真正退出，只能在执行器线程调用（会阻塞）。"""
        with self._worker_lock:
            stop_event = self._round_stop_event
            threads = list(self._worker_threads)
            self._round_stop_event = None
            self._worker_threads = []
            self._round_generation += 1
        if stop_event is not None:
            stop_event.set()
        self._release_mouse_safely()
        current = threading.current_thread()
        for thread in threads:
            if thread is current or not thread.is_alive():
                continue
            thread.join(timeout=timeout)
            if thread.is_alive():
                self.log_error(f"线程 {thread.name} 未能在 {timeout} 秒内退出")
            else:
                self.log_debug(f"线程 {thread.name} 已退出")

    def disable(self):
        """ok 框架在用户点击“停止”时会调用 disable()。

        这里先通知所有工作线程退出并松开左键，再走框架的停用逻辑，
        保证主线程无论从哪一步被中断，战斗/监控线程都不会残留。
        """
        try:
            self._request_stop_workers()
        except Exception as e:
            self.log_debug(f"停用任务时通知工作线程失败: {e}")
        super().disable()

    def _open_map_and_enter_boss(self):
        self.log_info("按M打开地图")
        self.send_key('m')
        self._sleep_with_check(2)
        click_x, click_y = self._get_scaled_coordinates(350, 940)
        self.log_info(f"点击世界BOSS入口，缩放后坐标: ({click_x}, {click_y})")
        self._click_safe(click_x, click_y, after_sleep=2)
        return True

    def _select_boss_by_config(self, boss_choice=None):
        if boss_choice is None:
            boss_choice = self.config.get('BOSS1选择', '罗贝拉格')

        image_name = self.boss_image_map.get(boss_choice)
        if image_name is None:
            self.log_info(f"BOSS选择为 [{boss_choice}]，无需额外操作")
            return True

        def _make_full_box():
            frame = self.next_frame()
            if frame is None:
                return None
            h, w = frame.shape[:2]
            return Box(0, 0, w, h)

        def _try_find_and_click(tag=""):
            full_box = _make_full_box()
            if full_box is None:
                self.log_error(f"BOSS选择{tag}：无法获取屏幕帧")
                return False
            self.log_info(f"BOSS选择为 [{boss_choice}]，全屏等待图片 [{image_name}]{tag}（超时1秒）")
            found_box = self.wait_feature(image_name, time_out=1, raise_if_not_found=False, box=full_box)
            if found_box:
                self.log_info(f"找到并点击 [{image_name}]{tag}")
                self._click_box_safe(found_box)
                self._sleep_with_check(1)
                return True
            return False

        def _do_scroll(tag=""):
            self.log_info(f"执行翻页{tag}：move(1730,935) + sleep(1) + scroll(-35) + sleep(1)")
            x, y = self._get_scaled_coordinates(1730, 935)
            self.move(x, y)
            self._sleep_with_check(1)
            self.scroll(x, y, -35)
            self._sleep_with_check(1)

        if _try_find_and_click("（第1次）"):
            return True

        for i in range(1, 4):
            _do_scroll(f"（第{i}次）")
            if _try_find_and_click(f"（翻页后第{i}次）"):
                return True

        self.log_error(f"3次翻页后仍未找到 [{image_name}]，跳过本次循环")
        return False

    def _wait_main_page_and_activate(self):
        self.log_info("等待返回游戏主页面...")
        if not self.wait_for_main_page_color(timeout=60):
            return False

        # 回到主页面后再等 0.5 秒，让落地动作稳定，然后直接按 W 前进
        self._sleep_with_check(0.5)

        # 落地后直接按 W 前进（不再先按源器1）
        forward_ms = self.config.get('前进时间', 2000)
        forward_time = forward_ms / 1000.0
        self.log_info(f"前进{forward_ms}毫秒（{forward_time}秒）")
        self.send_key_safe('w', down_time=forward_time)

        # 前进结束后再切武器：按完等 0.5 秒让切换动作生效，然后再启动战斗
        weapon_key = self.config.get('武器键', '2')
        self.log_info(f"切换武器，按武器键 [{weapon_key}]")
        self.send_key(weapon_key)
        self._sleep_with_check(0.5)

        combat_mode = self.config.get('战斗方式', '自动战斗')
        if combat_mode == '自动战斗':
            self.log_info("开启自动战斗")
            self.start_auto_combat()

            self.log_info("首次自动战斗后检测宝箱（持续2秒）...")
            detect_start = time.time()
            while time.time() - detect_start < 2:
                self._check_stopped()
                frame = self.next_frame()
                if frame is not None:
                    h, w = frame.shape[:2]
                    full_box = Box(0, 0, w, h)
                    for name in self.CHEST_NAMES:
                        results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
                        if results:
                            self.log_info(f"2秒内检测到宝箱 [{name}]，跳转至开箱逻辑")
                            return results[0]
                self._sleep_with_check(0.2)
            self.log_info("2秒内未检测到宝箱，继续等待BOSS刷新")
            return True
        else:
            self.log_info(f"{combat_mode}模式：不开启自动战斗，由自定义逻辑控制")
            return True

    def _wait_main_page_vampire(self):
        self.log_info("吸血鬼：等待返回游戏主页面...")
        if not self.wait_for_main_page_color(timeout=60):
            return False
        return True

    def wait_for_main_page_color(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            self._check_stopped()
            if self.check_main_page_color():
                return True
            self._sleep_with_check(0.5)
        return False

    def check_main_page_color(self):
        frame = self.next_frame()
        if frame is None:
            return False
        x, y = self._get_scaled_coordinates(*self.MAIN_PAGE_COORDS)
        if y >= frame.shape[0] or x >= frame.shape[1]:
            return False
        pixel = frame[y, x]
        return self._color_similar(pixel, self.TARGET_COLOR_BGR, tolerance=30)

    def _is_boss_spawned(self):
        frame = self.next_frame()
        if frame is None:
            return False
        x1, y1 = self._get_scaled_coordinates(1295, 155)
        x3, y3 = self._get_scaled_coordinates(1260, 155)
        h, w = frame.shape[:2]
        if any([y1 >= h or x1 >= w, y3 >= h or x3 >= w]):
            return False
        pixel1 = frame[y1, x1]
        pixel3 = frame[y3, x3]
        green1 = (pixel1[0] == 161 and pixel1[1] == 209 and pixel1[2] == 47)
        green3 = (pixel3[0] == 161 and pixel3[1] == 209 and pixel3[2] == 47)
        return green1 and green3

    def _check_boss_ui_disappeared(self):
        frame = self.next_frame()
        if frame is None:
            return False
        x1, y1 = self._get_scaled_coordinates(1295, 155)
        x3, y3 = self._get_scaled_coordinates(1260, 155)
        h, w = frame.shape[:2]
        if y1 >= h or x1 >= w or y3 >= h or x3 >= w:
            return False
        pixel1 = frame[y1, x1]
        pixel3 = frame[y3, x3]
        green1 = (pixel1[0] == 161 and pixel1[1] == 209 and pixel1[2] == 47)
        green3 = (pixel3[0] == 161 and pixel3[1] == 209 and pixel3[2] == 47)
        return not (green1 or green3)

    def _confirm_boss_dead(self):
        self.log_debug("等待1秒进行二次确认...")
        self._sleep_with_check(1)
        return self._check_boss_ui_disappeared()

    def _phase_b_wait_boss_ui_disappear(self, timeout=600):
        self.log_info(f"等待首领提示消失，超时{timeout}秒")
        start = time.time()
        while time.time() - start < timeout:
            self._check_stopped()
            if self._check_boss_ui_disappeared():
                if self._confirm_boss_dead():
                    self.log_info("首领提示已消失（二次确认通过）")
                    return True
                else:
                    self.log_debug("二次确认未通过，继续等待")
            self._sleep_with_check(0.2)
        self.log_error(f"等待首领提示消失超时（{timeout}秒）")
        return False

    # ---------- 战斗线程 ----------

    def _mengzhang_combat_loop(self, stop_event, boss_spawned, boss_dead, generation=None):
        stop_args = (stop_event, boss_dead)
        try:
            if self._get_screen_center() is None:
                self.log_error("孟章：无法获取屏幕帧")
                return
            target_x, target_y = self._get_scaled_coordinates(1815, 900)
            self.log_info(f"孟章：长按坐标 ({target_x}, {target_y})（已适配分辨率）")
            self.log_info("孟章：按 Enter 键（仅一次）")
            self.send_key('enter')
            self._wait_event(0.8, *stop_args, generation=generation)
            while not self._should_stop(*stop_args, generation=generation):
                skill_key = self._skill_key
                self.log_info(f"孟章：按技能键 ({skill_key})，等待1.5秒")
                self.send_key(skill_key)
                if self._wait_event(1.5, *stop_args, generation=generation):
                    break
                source1_key = self._source_key
                self.log_info(f"孟章：按源器1 ({source1_key})")
                self.send_key(source1_key)
                self.log_info(f"孟章：按技能键 ({skill_key})")
                self.send_key(skill_key)
                weapon_key = self.config.get('武器键', '2')
                self.log_info(f"孟章：按武器键 ({weapon_key})，等待3秒")
                self.send_key(weapon_key)
                if self._wait_event(3, *stop_args, generation=generation):
                    break
                self.log_info("孟章：长按坐标 {} 60秒开始".format((target_x, target_y)))
                self.mouse_down(target_x, target_y, key='left')
                try:
                    should_stop = self._wait_event(60, *stop_args, generation=generation)
                finally:
                    self.mouse_up(key='left')
                self.log_debug("孟章：释放左键")
                if should_stop:
                    break
                source2_key = self._get_source_key2()
                self.log_info(f"孟章：按源器2 ({source2_key})，等待15.2秒")
                self.send_key(source2_key)
                if self._wait_event(15.2, *stop_args, generation=generation):
                    break
        except TaskDisabledException:
            self.log_info("孟章操作线程收到禁用信号，退出")
        except Exception as e:
            self.log_error(f"孟章操作循环异常: {e}")
        finally:
            self._release_mouse_safely()
            # 只有正常打完才去点“关闭残留界面”，用户主动停止时不要再往游戏里点
            if not self._should_stop(*stop_args, generation=generation):
                try:
                    time.sleep(1)
                    click_x, click_y = self._get_scaled_coordinates(1025, 560)
                    self.log_info(f"孟章：点击坐标 ({click_x}, {click_y}) 以关闭残留界面")
                    self._click_safe(click_x, click_y, after_sleep=0.5)
                except TaskDisabledException:
                    pass
            self.log_info("孟章操作循环结束")

    def _yanuo_combat_loop(self, stop_event, boss_spawned, boss_dead, generation=None):
        stop_args = (stop_event, boss_dead)
        try:
            if self._get_screen_center() is None:
                self.log_error("雅诺：无法获取屏幕帧")
                return
            target_x, target_y = self._get_scaled_coordinates(1815, 900)
            self.log_info(f"雅诺：长按坐标 ({target_x}, {target_y})（已适配分辨率）")
            self.log_info("雅诺：按 Enter 键")
            self.send_key('enter')
            self._wait_event(0.8, *stop_args, generation=generation)
            self.log_info("雅诺：按下左键，长按开始")
            self.mouse_down(target_x, target_y, key='left')
            try:
                while not self._should_stop(*stop_args, generation=generation):
                    time.sleep(0.2)
            finally:
                self.log_info("雅诺：停止信号或BOSS死亡，释放左键")
                self.mouse_up(key='left')
        except TaskDisabledException:
            self.log_info("雅诺操作线程收到禁用信号，退出")
        except Exception as e:
            self.log_error(f"雅诺操作循环异常: {e}")
        finally:
            self._release_mouse_safely()
            if not self._should_stop(*stop_args, generation=generation):
                try:
                    time.sleep(1)
                    click_x, click_y = self._get_scaled_coordinates(1025, 560)
                    self.log_info(f"雅诺：点击坐标 ({click_x}, {click_y}) 以关闭残留界面")
                    self._click_safe(click_x, click_y, after_sleep=0.5)
                except TaskDisabledException:
                    pass
            self.log_info("雅诺操作循环结束")

    def _mengzhang_front_combat_loop(self, stop_event, boss_spawned, boss_dead, generation=None):
        stop_args = (stop_event, boss_dead)
        try:
            center = self._get_screen_center()
            if center is None:
                self.log_error("孟章（前台）：无法获取屏幕帧")
                return
            center_x, center_y = center
            self.log_info(f"孟章（前台）：屏幕中心坐标 ({center_x}, {center_y})")
            # 传送/切图后窗口可能没在前台，先单击一次激活窗口并让游戏重新捕获鼠标，
            # 否则后面的长按左键不生效
            self.log_debug("孟章（前台）：左键单击一次（初始）")
            self.mouse_down(center_x, center_y, key='left')
            time.sleep(0.05)
            self.mouse_up(key='left')
            self._wait_event(0.1, *stop_args, generation=generation)
            while not self._should_stop(*stop_args, generation=generation):
                skill_key = self._skill_key
                self.log_info(f"孟章（前台）：按技能键 ({skill_key})，等待1.5秒")
                self.send_key(skill_key)
                if self._wait_event(1.5, *stop_args, generation=generation):
                    break
                source1_key = self._source_key
                self.log_info(f"孟章（前台）：按源器1 ({source1_key})")
                self.send_key(source1_key)
                self.log_info(f"孟章（前台）：按技能键 ({skill_key})")
                self.send_key(skill_key)
                weapon_key = self.config.get('武器键', '2')
                self.log_info(f"孟章（前台）：按武器键 ({weapon_key})，等待3秒")
                self.send_key(weapon_key)
                if self._wait_event(3, *stop_args, generation=generation):
                    break
                self.log_info("孟章（前台）：长按左键60秒开始")
                self.mouse_down(center_x, center_y, key='left')
                try:
                    should_stop = self._wait_event(60, *stop_args, generation=generation)
                finally:
                    self.mouse_up(key='left')
                self.log_debug("孟章（前台）：释放左键")
                if should_stop:
                    break
                source2_key = self._get_source_key2()
                self.log_info(f"孟章（前台）：按源器2 ({source2_key})，等待15.2秒")
                self.send_key(source2_key)
                if self._wait_event(15.2, *stop_args, generation=generation):
                    break
        except TaskDisabledException:
            self.log_info("孟章（前台）操作线程收到禁用信号，退出")
        except Exception as e:
            self.log_error(f"孟章（前台）操作循环异常: {e}")
        finally:
            self._release_mouse_safely()
            self.log_info("孟章（前台）操作循环结束")

    def _yanuo_front_combat_loop(self, stop_event, boss_spawned, boss_dead, generation=None):
        stop_args = (stop_event, boss_dead)
        try:
            center = self._get_screen_center()
            if center is None:
                self.log_error("雅诺（前台）：无法获取屏幕帧")
                return
            center_x, center_y = center
            self.log_info(f"雅诺（前台）：屏幕中心坐标 ({center_x}, {center_y})")
            self.mouse_down(center_x, center_y, key='left')
            time.sleep(0.05)
            self.mouse_up(key='left')
            self._wait_event(0.1, *stop_args, generation=generation)
            self.log_info("雅诺（前台）：长按左键开始（将持续至BOSS死亡或超时），2秒后发送一次反引号键")
            self.mouse_down(center_x, center_y, key='left')
            start_time = time.time()
            key_sent = False
            try:
                while not self._should_stop(*stop_args, generation=generation):
                    now = time.time()
                    if not key_sent and (now - start_time >= 2.0):
                        self.send_key('`')
                        self.log_debug("雅诺（前台）：长按2秒后发送反引号键")
                        key_sent = True
                    time.sleep(0.2)
            finally:
                self.log_info("雅诺（前台）：释放左键")
                self.mouse_up(key='left')
        except TaskDisabledException:
            self.log_info("雅诺（前台）操作线程收到禁用信号，退出")
        except Exception as e:
            self.log_error(f"雅诺（前台）操作循环异常: {e}")
        finally:
            self._release_mouse_safely()
            self.log_info("雅诺（前台）操作线程结束")

    # ---------- 监控线程 ----------

    def _monitor_boss_status(self, stop_event, boss_spawned, boss_dead, timeout, generation=None):
        stop_args = (stop_event, boss_dead)
        try:
            start_time = time.time()
            boss_spawned_occurred = False
            while not self._should_stop(*stop_args, generation=generation):
                if not boss_spawned_occurred and (time.time() - start_time > timeout):
                    self.log_info(f"BOSS刷新监测超时（{timeout}秒），未检测到BOSS刷新")
                    stop_event.set()
                    break
                if not boss_spawned_occurred:
                    if self._is_boss_spawned():
                        boss_spawned_occurred = True
                        boss_spawned.set()
                        self.log_info("监测到BOSS刷新！")
                    else:
                        self._wait_event(1, *stop_args, generation=generation)
                        continue
                else:
                    if self._check_boss_ui_disappeared():
                        if self._confirm_boss_dead():
                            boss_dead.set()
                            self.log_info("监测到BOSS死亡（二次确认通过）！")
                            break
                        else:
                            self.log_debug("二次确认未通过，继续监控")
                    self._wait_event(1, *stop_args, generation=generation)
        except TaskDisabledException:
            self.log_info("BOSS状态监测线程收到禁用信号，退出")
        except Exception as e:
            self.log_error(f"BOSS状态监测线程异常: {e}")
        finally:
            self.log_info("BOSS状态监测线程结束")

    def _monitor_boss_spawn_only(self, timeout):
        self.log_info(f"等待BOSS刷新，超时{timeout}秒...")
        start = time.time()
        while time.time() - start < timeout:
            self._check_stopped()
            if self._is_boss_spawned():
                self.log_info("检测到BOSS刷新！")
                return 'boss_found'
            self._sleep_with_check(2, interval=0.5)
        self.log_info(f"BOSS刷新超时（{timeout}秒）")
        return 'timeout'

    # ---------- 宝箱 ----------

    def wait_any_chest(self, time_out=30, threshold=None):
        if threshold is None:
            threshold = self.CHEST_THRESHOLD
        self.log_debug(f"等待任意宝箱出现，超时{time_out}秒，阈值{threshold}")
        start = time.time()
        while time.time() - start < time_out:
            self._check_stopped()
            frame = self.next_frame()
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=threshold)
                    if results:
                        self.log_debug(f"找到宝箱: {name}")
                        return results[0]
            self._sleep_with_check(0.5)
        return None

    def _reacquire_chest(self):
        for _ in range(10):
            self._check_stopped()
            frame = self.next_frame()
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in self.CHEST_NAMES:
                    results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
                    if results:
                        return results[0]
            self._sleep_with_check(0.5)
        return None

    def _cross_search(self):
        self.log_info(f"启动十字搜索，宝箱阈值{self.CHEST_THRESHOLD}")
        found_event = threading.Event()
        stop_event = threading.Event()
        chest_box = [None]

        def searcher():
            try:
                while not stop_event.is_set() and not found_event.is_set():
                    try:
                        frame = self.next_frame()
                        if frame is not None:
                            h, w = frame.shape[:2]
                            full_box = Box(0, 0, w, h)
                            for name in self.CHEST_NAMES:
                                results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
                                if results:
                                    chest_box[0] = results[0]
                                    self.log_info(f"十字搜索找到宝箱: {name}")
                                    found_event.set()
                                    break
                        for _ in range(3):
                            if stop_event.is_set():
                                break
                            self._sleep_with_check(0.033)
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
                            self._sleep_with_check(0.05)
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
                stop_event.set()

        t1 = threading.Thread(target=searcher, daemon=True)
        t2 = threading.Thread(target=mover, daemon=True)
        t1.start()
        t2.start()
        try:
            while t1.is_alive() or t2.is_alive():
                self._sleep_with_check(0.1)
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
        self.log_info(f"启动米字搜索，宝箱阈值{self.CHEST_THRESHOLD}，执行完整移动序列")
        found_event = threading.Event()
        stop_event = threading.Event()
        chest_box = [None]

        def searcher():
            try:
                while not stop_event.is_set() and not found_event.is_set():
                    try:
                        frame = self.next_frame()
                        if frame is not None:
                            h, w = frame.shape[:2]
                            full_box = Box(0, 0, w, h)
                            for name in self.CHEST_NAMES:
                                results = self.find_feature(name, box=full_box, threshold=self.CHEST_THRESHOLD)
                                if results:
                                    chest_box[0] = results[0]
                                    self.log_info(f"米字搜索找到宝箱: {name}")
                                    found_event.set()
                                    break
                        for _ in range(3):
                            if stop_event.is_set():
                                break
                            self._sleep_with_check(0.033)
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
                                self._sleep_with_check(0.05)
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
                                self._sleep_with_check(0.05)
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
                self._sleep_with_check(0.1)
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

    def _nanyin_teleport_to_main_page(self, press_source_key=False):
        self.send_key('m')
        self._sleep_with_check(2)

        self.log_info("等待地图标记，超时2秒，阈值0.75")
        start_time = time.time()
        nanyin_box = None
        while time.time() - start_time < 2:
            self._check_stopped()
            frame = self.next_frame()
            if frame is None:
                self._sleep_with_check(0.5)
                continue
            h, w = frame.shape[:2]
            full_box = Box(0, 0, w, h)
            results = self.find_feature('nanyintp', box=full_box, threshold=0.75)
            if results:
                nanyin_box = results[0]
                break
            self._sleep_with_check(0.5)

        if not nanyin_box:
            self.log_info("南音传送：地图标记未就绪，点击屏幕中心后继续")
            self.click(0.5, 0.5)
            self._sleep_with_check(1)
        else:
            self._click_box_safe(nanyin_box, after_sleep=1)

        frame = self.next_frame()
        if frame is None:
            self.log_error("南音传送：无法获取屏幕帧")
            return False
        h, w = frame.shape[:2]
        full_box = Box(0, 0, w, h)
        ocr_results = self.wait_ocr(box=full_box, match="虚空渊流", time_out=5, raise_if_not_found=False)

        if not ocr_results:
            self.log_error("南音传送：目标地名未识别，继续尝试下一步")
        else:
            self._click_box_safe(ocr_results[0], after_sleep=1)

        if not self._wait_and_click_feature('tp', timeout=3, after_sleep=1):
            self.log_error("南音传送：tp 未找到")
            return False

        sure_box = self.wait_feature('sure', time_out=10, raise_if_not_found=False)
        if not sure_box:
            self.log_error("南音传送：sure 未找到")
            return False
        self._click_box_safe(sure_box)
        if press_source_key:
            self.log_info("吸血鬼：执行传送后附加操作")
            self.send_key_down(self._source_key)
            self._sleep_with_check(0.5)
            self.send_key_up(self._source_key)
            self._sleep_with_check(7.5)
        else:
            self._sleep_with_check(8)

        self.log_info("南音传送：等待传送后回到主页面...")
        if not self.wait_for_main_page_color(timeout=30):
            self.log_error("南音传送：未检测到主页面，但继续尝试下一步")

        return True

    def _nanyin_teleport_search(self):
        self.log_info("启动南音传送搜索")
        if not self._nanyin_teleport_to_main_page():
            return False

        if not self._wait_for_target_text(timeout=10):
            self.log_info("南音传送：超时未检测到目标文字，继续尝试拾取")

        if not self._phase_chest_pickup(chest_box=None):
            self.log_error("南音传送：宝箱拾取失败")
            return False

        if not self._claim_reward():
            self.log_error("南音传送：奖励领取失败")
            return False

        self.log_info("南音传送搜索成功完成")
        return True

    def _vampire_search(self, timeout):
        self.log_info("吸血鬼：启动南音传送")
        if not self._nanyin_teleport_to_main_page(press_source_key=True):
            self.log_error("吸血鬼：南音传送失败")
            return False

        self.log_info(f"吸血鬼：等待宝箱图标出现，超时{timeout}秒，阈值{self.CHEST_THRESHOLD}...")
        chest = self.wait_any_chest(time_out=timeout)
        if not chest:
            self.log_error(f"吸血鬼：{timeout}秒内未发现宝箱图标")
            return False

        self.log_info(f"吸血鬼：找到宝箱 [{chest.name}]，进入拾取阶段")
        if not self._phase_chest_pickup(chest_box=chest):
            self.log_error("吸血鬼：宝箱拾取失败")
            return False

        if not self._claim_reward():
            self.log_error("吸血鬼：奖励领取失败")
            return False

        self.log_info("吸血鬼流程成功完成")
        return True

    def _dibuling_round(self, wait_timeout):
        self.log_info(f"地缚灵：原地寻找宝箱，超时{wait_timeout}秒，阈值{self.CHEST_THRESHOLD}...")
        chest = self.wait_any_chest(time_out=wait_timeout)
        if not chest:
            self.log_error(f"地缚灵：{wait_timeout}秒内未发现宝箱")
            return 'fail'

        self.log_info(f"地缚灵：找到宝箱 [{chest.name}]，交给拾取阶段（接近+二次OCR确认+重试）")
        if not self._phase_chest_pickup(chest_box=chest):
            self.log_error("地缚灵：宝箱拾取失败")
            return 'fail'

        if not self._claim_reward():
            self.log_error("地缚灵：奖励领取失败")
            return 'fail'

        self.log_info("地缚灵：本次循环成功完成")
        return 'success'

    def _wait_for_target_text(self, timeout=60):
        self.log_info(f"等待目标文字出现，超时{timeout}秒")
        x1, y1 = self._get_scaled_coordinates(1110, 520)
        x2, y2 = self._get_scaled_coordinates(1280, 575)
        ocr_box = Box(x1, y1, width=x2 - x1, height=y2 - y1)
        start_time = time.time()
        while time.time() - start_time < timeout:
            self._check_stopped()
            try:
                ocr_results = self.ocr(box=ocr_box, target_height=540)
                if ocr_results:
                    for box in ocr_results:
                        text = box.name.strip()
                        if ('太极匣' in text) or ('高级密码箱' in text) or ('机密魔方' in text):
                            self.log_info(f"检测到目标文字: {text}")
                            return True
            except Exception as e:
                self.log_debug(f"OCR检测异常: {e}")
            self._sleep_with_check(0.5)
        return False

    def cross_search(self, search_mode):
        if search_mode == '南音传送':
            return self._nanyin_teleport_search()
        elif search_mode == '十字搜索':
            return self._cross_search()
        else:
            return self._mi_search()

    def _sleep_with_events(self, seconds, stop_event, found_event):
        interval = 0.2
        elapsed = 0
        while elapsed < seconds:
            if stop_event.is_set() or found_event.is_set():
                break
            self._sleep_with_check(min(interval, seconds - elapsed))
            elapsed += interval

    def _recover_character_state(self):
        self.log_info("角色状态异常，尝试按S键恢复，超时150秒")
        start_time = time.time()
        timeout = 150
        while time.time() - start_time < timeout:
            self._check_stopped()
            if self._is_character_state_normal():
                self.log_info("状态已恢复正常")
                return True
            self.log_debug("按下S键 (0.2秒)")
            self.send_key_safe('s', down_time=0.2)
            self._sleep_with_check(0.2)
        self.log_error(f"状态恢复失败，超时{timeout}秒")
        return False

    def _is_character_state_normal(self):
        frame = self.next_frame()
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

        try:
            while time.time() - start_time < max_walk_time:
                self._check_stopped()
                current_time = time.time()
                target_detected = False
                try:
                    ocr_results = self.ocr(box=ocr_box, target_height=540)
                    if ocr_results:
                        texts = [box.name.strip() for box in ocr_results]
                        self.log_debug(f"OCR识别到: {texts}")
                        for box in ocr_results:
                            text = box.name.strip()
                            if ('太极匣' in text) or ('高级密码箱' in text) or ('机密魔方' in text):
                                target_detected = True
                                break
                except Exception as e:
                    self.log_debug(f"OCR检测异常: {e}")

                if target_detected:
                    self.log_info("检测到目标文字，接近成功")
                    return True

                if current_time - last_key_press_time < key_press_interval:
                    self._sleep_with_check(0.05)
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
                    self._sleep_with_check(0.1)

            self.log_error(f"approach_bosschest: 超时{max_walk_time}秒未检测到目标文字")
            return False

        except TaskDisabledException:
            self.log_info("approach_bosschest 被用户手动停止")
            raise

    def _phase_chest_pickup(self, chest_box=None):
        self.log_info("进入宝箱拾取阶段")

        if chest_box is None:
            self.log_info("未传入宝箱，跳过宝箱图标查找，直接进入开箱流程")
        else:
            max_retries = 3
            for retry in range(max_retries):
                if not self.approach_bosschest(max_walk_time=60, target_chest=chest_box):
                    self.log_error(f"接近宝箱失败 (第{retry + 1}次)")
                    return False

                self._sleep_with_check(1)
                frame = self.next_frame()
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
                            if ('太极匣' in text) or ('高级密码箱' in text) or ('机密魔方' in text):
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
        self._sleep_with_check(1)

        if self._is_character_state_normal():
            self.log_info("角色状态正常，继续拾取")
        else:
            if not self._recover_character_state():
                self.log_error("角色状态恢复失败，放弃本次拾取")
                return False
            self.log_info("状态恢复完成")

        start_time = time.time()
        timeout = 10
        self.log_info("开始连续按F并检测openchest1/2，超时10秒，阈值0.8")

        while time.time() - start_time < timeout:
            self._check_stopped()
            self.send_key_safe('f', down_time=0.05)
            frame = self.next_frame()
            if frame is not None:
                h, w = frame.shape[:2]
                full_box = Box(0, 0, w, h)
                for name in ['openchest1', 'openchest2']:
                    boxes = self.find_feature(name, box=full_box, threshold=0.8)
                    if boxes:
                        box = boxes[0]
                        self.log_info(f"检测到 {name} 图片，立即点击")
                        self._click_box_safe(box)
                        self._sleep_with_check(1)
                        self._openchest_box = box
                        return True
            self._sleep_with_check(0.1)

        self.log_error("拾取超时：10秒内未出现openchest图片")
        return False

    def _claim_reward(self):
        x, y = self._get_scaled_coordinates(1255, 575)
        self.log_info(f"点击奖励坐标 ({x}, {y})")
        self._click_safe(x, y, after_sleep=7)
        return True

    def _teleport_to_haijiade(self):
        self.log_info("执行传送至海嘉德")
        self.send_key('m')
        self._sleep_with_check(1)
        x, y = self._get_scaled_coordinates(540, 940)
        self.log_info(f"点击传送坐标 ({x}, {y})")
        self._click_safe(x, y, after_sleep=10)
        self.log_info("等待传送后回到主页面...")
        if not self.wait_for_main_page_color(timeout=30):
            self.log_error("传送至海嘉德后未回到主页面")
            return False
        self.log_info("已回到主页面")
        return True

    def _teleport_to_jiuyu(self):
        self.log_info("执行传送至九域")
        self.log_info("按下 Alt + 3")
        self.send_key_down('alt')
        self.send_key_down('3')
        self._sleep_with_check(0.1)
        self.send_key_up('3')
        self.send_key_up('alt')
        self._sleep_with_check(2)
        click_points = [
            (130, 615, 1),
            (520, 725, 1),
            (1265, 580, 0),
        ]
        for x, y, after in click_points:
            cx, cy = self._get_scaled_coordinates(x, y)
            self.log_info(f"点击坐标 ({cx}, {cy})")
            self._click_safe(cx, cy, after_sleep=after)
        self._sleep_with_check(10)
        self.log_info("等待传送后回到主页面...")
        if not self.wait_for_main_page_color(timeout=30):
            self.log_error("传送至九域后未回到主页面")
            return False
        self.log_info("已回到主页面")
        return True

    def _teleport_to_grid(self):
        self.log_info("执行传送至格网")
        self.log_info("按下 Alt + 3")
        self.send_key_down('alt')
        self.send_key_down('3')
        self._sleep_with_check(0.1)
        self.send_key_up('3')
        self.send_key_up('alt')
        self._sleep_with_check(2)
        click_points = [
            (130, 615, 1),
            (1030, 725, 1),
            (1265, 580, 0),
        ]
        for x, y, after in click_points:
            cx, cy = self._get_scaled_coordinates(x, y)
            self.log_info(f"点击坐标 ({cx}, {cy})")
            self._click_safe(cx, cy, after_sleep=after)
        self._sleep_with_check(10)
        self.log_info("等待传送后回到主页面...")
        if not self.wait_for_main_page_color(timeout=30):
            self.log_error("传送至格网后未回到主页面")
            return False
        self.log_info("已回到主页面")
        return True

    def _teleport_to_lockhart(self):
        self.log_info("执行传送至洛克哈特")
        self.log_info("按下 Alt + 3")
        self.send_key_down('alt')
        self.send_key_down('3')
        self._sleep_with_check(0.1)
        self.send_key_up('3')
        self.send_key_up('alt')
        self._sleep_with_check(2)
        click_points = [
            (130, 615, 1),
            (530, 940, 1),
            (250, 395, 1),
            (1265, 580, 0),
        ]
        for x, y, after in click_points:
            cx, cy = self._get_scaled_coordinates(x, y)
            self.log_info(f"点击坐标 ({cx}, {cy})")
            self._click_safe(cx, cy, after_sleep=after)
        self._sleep_with_check(10)
        self.log_info("等待传送后回到主页面...")
        if not self.wait_for_main_page_color(timeout=30):
            self.log_error("传送至洛克哈特后未回到主页面")
            return False
        self.log_info("已回到主页面")
        return True

    def _search_and_pickup(self, search_mode):
        if search_mode == '南音传送':
            success = self._nanyin_teleport_search()
            if not success:
                self.log_error("南音传送流程失败")
                return 'fail'
            return 'success'
        else:
            chest = self.wait_any_chest(time_out=5)
            if not chest:
                self.log_info("5秒内未找到宝箱，启动搜索")
                chest = self.cross_search(search_mode)
            if not chest:
                self.log_error("无法找到宝箱")
                return 'fail'
            if not self._phase_chest_pickup(chest):
                self.log_error("宝箱拾取失败")
                return 'fail'
            if not self._claim_reward():
                self.log_error("奖励领取失败")
                return 'fail'
            return 'success'

    def _execute_boss_round(self, boss_info, wait_timeout, combat_mode):
        if combat_mode == '地缚灵':
            return self._dibuling_round(wait_timeout)

        boss_index = boss_info['index']
        boss_choice = boss_info['choice']
        search_mode = boss_info['search_mode']
        teleport = boss_info.get('teleport', '不传送')

        if teleport == '海嘉德':
            self.log_info(f"BOSS{boss_index}：传送至海嘉德")
            if not self._teleport_to_haijiade():
                return 'fail'
        elif teleport == '九域':
            self.log_info(f"BOSS{boss_index}：传送至九域")
            if not self._teleport_to_jiuyu():
                return 'fail'
        elif teleport == '格网':
            self.log_info(f"BOSS{boss_index}：传送至格网")
            if not self._teleport_to_grid():
                return 'fail'
        elif teleport == '洛克哈特':
            self.log_info(f"BOSS{boss_index}：传送至洛克哈特")
            if not self._teleport_to_lockhart():
                return 'fail'

        if not self._open_map_and_enter_boss():
            self.log_error("进入世界BOSS界面失败")
            return 'fail'

        if not self._select_boss_by_config(boss_choice):
            self.log_error(f"BOSS{boss_index} 选择失败，跳过本次循环")
            return 'fail'

        if not self._wait_and_click_feature('gotoboss', timeout=30, after_sleep=0):
            return 'fail'

        if not self._wait_and_click_feature('shenlin', timeout=30, after_sleep=8):
            return 'fail'

        if combat_mode == '吸血鬼':
            if not self._wait_main_page_vampire():
                self.log_error("吸血鬼：启动流程失败")
                return 'fail'
            self.last_shenlin_time = time.time()
            if not self._vampire_search(wait_timeout):
                self.log_error("吸血鬼流程失败")
                return 'fail'
            return 'success'

        activate_result = self._wait_main_page_and_activate()

        if activate_result is False:
            self.log_error("启动战斗流程失败")
            return 'fail'

        if activate_result is not True:
            chest_box = activate_result
            self.log_info("首次自动战斗后检测到宝箱，直接进入开箱流程")
            if not self._phase_chest_pickup(chest_box):
                self.log_error("宝箱拾取失败")
                return 'fail'
            if not self._claim_reward():
                self.log_error("奖励领取失败")
                return 'fail'
            return 'success'

        self.last_shenlin_time = time.time()

        if combat_mode == '自动战斗':
            self.log_info("开始监测BOSS刷新（自动战斗模式）")
            monitor_result = self._monitor_boss_spawn_only(wait_timeout)
            if monitor_result == 'timeout':
                self.log_error("BOSS刷新监测超时")
                return 'timeout'
            if not self._phase_b_wait_boss_ui_disappear():
                self.log_error("首领提示未消失")
                return 'fail'
            self.log_info("重新开启自动战斗")
            self.start_auto_combat()
            return self._search_and_pickup(search_mode)
        else:
            stop_event = threading.Event()
            boss_spawned = threading.Event()
            boss_dead = threading.Event()

            if combat_mode == '孟章':
                target = self._mengzhang_combat_loop
            elif combat_mode == '雅诺':
                target = self._yanuo_combat_loop
            elif combat_mode == '孟章（前台）':
                target = self._mengzhang_front_combat_loop
            elif combat_mode == '雅诺（前台）':
                target = self._yanuo_front_combat_loop
            else:
                self.log_error(f"未知战斗方式: {combat_mode}")
                return 'fail'

            generation = self._begin_worker_round(stop_event)
            try:
                t_combat = threading.Thread(target=target, args=(stop_event, boss_spawned, boss_dead, generation),
                                            daemon=True, name='MWB-combat')
                self._register_worker_thread(t_combat)
                t_combat.start()
                self.log_info("操作线程已启动，等待2秒后启动监控线程...")
                self._sleep_with_check(2)

                t_monitor = threading.Thread(
                    target=self._monitor_boss_status,
                    args=(stop_event, boss_spawned, boss_dead, wait_timeout, generation),
                    daemon=True,
                    name='MWB-monitor'
                )
                self._register_worker_thread(t_monitor)
                t_monitor.start()
                self.log_info("监控线程已启动，两者并行运行")

                start_monitor = time.time()
                while not self._should_stop(stop_event, boss_dead, generation=generation):
                    if not boss_spawned.is_set() and (time.time() - start_monitor > wait_timeout):
                        self.log_info(f"监测超时（{wait_timeout}秒），未检测到BOSS刷新，终止")
                        stop_event.set()
                        break
                    self._sleep_with_check(0.2)
            finally:
                # 关键：主线程无论是正常结束、超时，还是被 TaskDisabledException 中断，
                # 都必须先发停止信号并等战斗/监控线程真正退出，否则旧线程会一直残留，
                # 用户再次启动时就变成两个 BOSS 任务同时跑。
                self._stop_worker_threads()

            if not boss_dead.is_set():
                if not boss_spawned.is_set():
                    return 'timeout'
                else:
                    return 'fail'
            else:
                self.log_info("检测到BOSS死亡，继续拾取流程")
                return self._search_and_pickup(search_mode)

    def run(self):
        # 启动前先回收上一次运行可能残留的线程（用户停止后立刻再次启动的场景）
        self._stop_worker_threads()
        try:
            loop_mode = self.config.get('循环模式', '轮换')
            forward_time = self.config.get('前进时间', 2000)
            wait_timeout = self.config.get('等待超时', 60)
            combat_mode = self.config.get('战斗方式', '自动战斗')

            bosses = []
            bosses.append({
                'index': 1,
                'choice': self.config.get('BOSS1选择', '罗贝拉格'),
                'search_mode': self.config.get('BOSS1搜索模式', '十字搜索'),
                'teleport': self.config.get('BOSS1传送', '不传送'),
            })
            if self.config.get('启用BOSS2', False):
                bosses.append({
                    'index': 2,
                    'choice': self.config.get('BOSS2选择', '罗贝拉格'),
                    'search_mode': self.config.get('BOSS2搜索模式', '十字搜索'),
                    'teleport': self.config.get('BOSS2传送', '不传送'),
                })
            if self.config.get('启用BOSS3', False):
                bosses.append({
                    'index': 3,
                    'choice': self.config.get('BOSS3选择', '罗贝拉格'),
                    'search_mode': self.config.get('BOSS3搜索模式', '十字搜索'),
                    'teleport': self.config.get('BOSS3传送', '不传送'),
                })

            if not bosses:
                self.log_error("没有启用任何BOSS")
                return

            self.log_info(f"配置: 循环模式={loop_mode}, 战斗方式={combat_mode}, 等待超时={wait_timeout}s, "
                          f"宝箱阈值={self.CHEST_THRESHOLD}")

            current_index = 0
            loop_count = 0

            while True:
                loop_count += 1
                self._check_stopped()
                self.log_info(f"--- 第 {loop_count} 次循环开始 ---")
                loop_start_time = time.time()

                if combat_mode != '地缚灵':
                    if loop_count > 1 and self.last_shenlin_time != 0:
                        elapsed = time.time() - self.last_shenlin_time
                        if elapsed < 60:
                            wait_time = 60 - elapsed
                            self.log_info(f"神临冷却中，已过 {elapsed:.1f}秒，需等待 {wait_time:.1f}秒")
                            self._sleep_with_check(wait_time)

                    if not self.is_main_page():
                        self.log_error("无法进入游戏主页面，等待5秒后重试")
                        self._sleep_with_check(5)
                        continue

                boss_info = bosses[current_index]
                self.log_info(f"当前执行 BOSS{boss_info['index']}：{boss_info['choice']}")

                result = self._execute_boss_round(boss_info, wait_timeout, combat_mode)

                if loop_mode == '轮换':
                    current_index = (current_index + 1) % len(bosses)
                    self.log_info("轮换模式：切换到下一个 BOSS")
                else:
                    if result == 'timeout':
                        current_index = (current_index + 1) % len(bosses)
                        self.log_info("专注模式：等待超时，切换到下一个 BOSS")
                    else:
                        self.log_info("专注模式：保持当前 BOSS")

                elapsed = time.time() - loop_start_time
                self.log_info(f"本次循环总耗时 {elapsed:.1f}秒")

        except TaskDisabledException:
            self.log_info("多世界BOSS任务被用户手动停止")
        except Exception as e:
            self.log_error(f"多世界BOSS任务异常: {e}", notify=True)
            self.screenshot("multiworldboss_error")
            raise
        finally:
            # 兜底：任何退出路径都不允许留下工作线程
            self._stop_worker_threads()