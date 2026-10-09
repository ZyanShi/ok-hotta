import time
import threading
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask
from src.config import key_config_option


class MultiWorldBossTask(BaseQRSLTask):
    """多世界BOSS自动化任务（支持轮换/专注模式）"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "多世界BOSS"
        self.group_name = "精炼强化"
        self.description = "自动轮换/专注挑战多个世界BOSS并拾取宝箱"
        self.group_icon = FluentIcon.MARKET
        self.icon = FluentIcon.MARKET

        # 可选 BOSS 列表（已去掉带 & 的组合及玛格玛）
        boss_options = [
            '罗贝拉格',
            '阿波菲斯',
            '急冻机甲',
            '露琪亚',
            '巴巴罗萨',
            '伦迪尔',
            '朱厌',
            '玄鸦',
            '飞廉',
            '英招',
            '阵点球',
            '幻蝎',
            '地驭',
            '皇后虫',
        ]
        search_options = ['米字搜索', '十字搜索', '南音传送']
        combat_options = ['自动战斗', '孟章（前台）', '雅诺（前台）', '孟章', '雅诺']
        loop_mode_options = ['轮换', '专注']
        teleport_options = ['不传送', '海嘉德', '九域', '格网', '洛克哈特']

        self.default_config.update({
            '循环模式': '轮换',
            '前进时间': 3,
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
            '前进时间': '进入战斗后按 W 前进的持续时间（秒）',
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

        self._source_key = self._get_source_key()
        self.boss_image_map = {
            '罗贝拉格': None,
            '阿波菲斯': 'Apophis',
            '急冻机甲': 'CryoLobster',
            '露琪亚': 'Sweetie',
            '巴巴罗萨': 'Barbarossa',
            '伦迪尔': 'Lundir',
            '朱厌': 'Zhuyan',
            '玄鸦': 'Xuanya',
            '飞廉': 'Feilian',
            '英招': 'yingzhao',
            '阵点球': 'Zhendianqiu',
            '幻蝎': 'huanxie',
            '地驭': 'diyu',
            '皇后虫': 'huanghouchong',
        }
        self.last_shenlin_time = 0

    # ==================== 可中断睡眠 ====================
    def _sleep_with_check(self, seconds, interval=0.2):
        elapsed = 0
        while elapsed < seconds:
            self._check_stopped()
            remaining = min(interval, seconds - elapsed)
            self.sleep(remaining)
            elapsed += remaining

    # ---- 全局按键读取 ----
    def _get_source_key(self):
        try:
            global_config = self.get_global_config(key_config_option)
            return global_config.get('源器键1', 'x')
        except Exception:
            self.log_debug("读取全局源器键1失败，使用默认值 'x'")
            return 'x'

    def _get_source_key2(self):
        try:
            global_config = self.get_global_config(key_config_option)
            return global_config.get('源器键2', 'c')
        except Exception:
            self.log_debug("读取全局源器键2失败，使用默认值 'c'")
            return 'c'

    def _open_map_and_enter_boss(self):
        self.log_info("按M打开地图")
        self.send_key('m')
        self._sleep_with_check(2)
        click_x, click_y = self._get_scaled_coordinates(350, 940)
        self.log_info(f"点击世界BOSS入口，缩放后坐标: ({click_x}, {click_y})")
        self._click_safe(click_x, click_y, after_sleep=2)
        return True

    def _wait_and_click_feature(self, feature_name, timeout, after_sleep=0, box=None):
        found_box = self.wait_feature(feature_name, time_out=timeout, raise_if_not_found=False, box=box)
        if found_box:
            self.log_info(f"找到并点击 [{feature_name}]")
            self._click_box_safe(found_box)
            if after_sleep > 0:
                self._sleep_with_check(after_sleep)
            return True
        self.log_error(f"等待 [{feature_name}] 超时 ({timeout}秒)")
        return False

    # ==================== 简化后的 BOSS 选择（带3次翻页重试，全屏搜索） ====================
    def _select_boss_by_config(self, boss_choice=None):
        """
        直接根据 BOSS 名称查找图片并点击，无额外动作，全程全屏搜索。
        流程：
          1. 识别 1 秒，找到则点击；
          2. 未找到 → move + sleep(1) + scroll(-35) + sleep(1) + 识别 1 秒；
          3. 重复上述翻页 + 识别，共执行 3 次翻页；
          4. 3 次翻页后仍未找到 → 返回 False（由调用方跳过本次循环）。
        """
        if boss_choice is None:
            boss_choice = self.config.get('BOSS1选择', '罗贝拉格')

        image_name = self.boss_image_map.get(boss_choice)
        if image_name is None:
            self.log_info(f"BOSS选择为 [{boss_choice}]，无需额外操作")
            return True

        # ---- 工具函数：构建全屏 full_box ----
        def _make_full_box():
            frame = self.frame
            if frame is None:
                return None
            h, w = frame.shape[:2]
            return Box(0, 0, w, h)

        # ---- 工具函数：尝试识别一次（1 秒，全屏），找到则点击并返回 True ----
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

        # ---- 工具函数：执行一次翻页操作 ----
        def _do_scroll(tag=""):
            self.log_info(f"执行翻页{tag}：move(1730,935) + sleep(1) + scroll(-35) + sleep(1)")
            x, y = self._get_scaled_coordinates(1730, 935)
            self.move(x, y)
            self._sleep_with_check(1)
            self.scroll(x, y, -35)
            self._sleep_with_check(1)

        # ---- 第 1 次识别（无翻页） ----
        if _try_find_and_click("（第1次）"):
            return True

        # ---- 翻页循环执行 3 次，每次翻页后识别一次 ----
        for i in range(1, 4):
            _do_scroll(f"（第{i}次）")
            if _try_find_and_click(f"（翻页后第{i}次）"):
                return True

        # ---- 3 次翻页后仍未找到 ----
        self.log_error(f"3次翻页后仍未找到 [{image_name}]，跳过本次循环")
        return False

    def _wait_main_page_and_activate(self):
        self.log_info("等待返回游戏主页面...")
        if not self.wait_for_main_page_color(timeout=60):
            return False
        self.log_info(f"按源器键1 [{self._source_key}]")
        self.send_key_down(self._source_key)
        self._sleep_with_check(0.5)
        self.send_key_up(self._source_key)
        self._sleep_with_check(0.2)

        weapon_key = self.config.get('武器键', '2')
        self.log_info(f"切换武器，按武器键 [{weapon_key}]")
        self.send_key(weapon_key)
        self._sleep_with_check(0.2)

        forward_time = self.config.get('前进时间', 3)
        self.log_info(f"前进{forward_time}秒")
        self.send_key_safe('w', down_time=forward_time)

        combat_mode = self.config.get('战斗方式', '自动战斗')
        if combat_mode == '自动战斗':
            self.log_info("开启自动战斗")
            self.start_auto_combat()
        else:
            self.log_info(f"{combat_mode}模式：不开启自动战斗，由自定义逻辑控制")
        return True

    def wait_for_main_page_color(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            if self.check_main_page_color():
                return True
            self._sleep_with_check(0.5)
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

    # ==================== BOSS 刷新检测 ====================
    def _is_boss_spawned(self):
        frame = self.frame
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
        frame = self.frame
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
        self.log_info(f"等待首领提示消失，超时{timeout}秒（二次确认）...")
        start = time.time()
        while time.time() - start < timeout:
            if self._check_boss_ui_disappeared():
                if self._confirm_boss_dead():
                    self.log_info("首领提示已消失（二次确认通过）")
                    return True
                else:
                    self.log_debug("二次确认未通过，继续等待")
            self._sleep_with_check(0.2)
        self.log_error(f"等待首领提示消失超时（{timeout}秒）")
        return False

    # ==================== 战斗循环 ====================
    def _mengzhang_combat_loop(self, stop_event, boss_spawned, boss_dead):
        frame = self.frame
        if frame is None:
            self.log_error("孟章：无法获取屏幕帧")
            return
        target_x, target_y = self._get_scaled_coordinates(1815, 900)
        self.log_info(f"孟章：长按坐标 ({target_x}, {target_y})（已适配分辨率）")
        source1_key = self._source_key
        source2_key = self._get_source_key2()
        try:
            self.log_info("孟章：按 Enter 键（仅一次）")
            self.send_key('enter')
            time.sleep(0.8)
            while not stop_event.is_set() and not boss_dead.is_set():
                self.log_debug("孟章：长按坐标 {} 50秒开始".format((target_x, target_y)))
                self.mouse_down(target_x, target_y, key='left')
                start_time = time.time()
                while time.time() - start_time < 50:
                    if stop_event.is_set() or boss_dead.is_set():
                        break
                    self._sleep_with_check(1.0, interval=1.0)
                self.mouse_up(key='left')
                self.log_debug("孟章：释放左键")
                if stop_event.is_set() or boss_dead.is_set():
                    break
                self.log_debug(f"孟章：按源器2 ({source2_key})，等待15秒")
                self.send_key(source2_key)
                time.sleep(15)
                if stop_event.is_set() or boss_dead.is_set():
                    break
                self.log_debug(f"孟章：按源器1 ({source1_key})，等待3秒")
                self.send_key(source1_key)
                time.sleep(3)
        except TaskDisabledException:
            self.log_info("孟章操作线程收到禁用信号，退出")
            try:
                self.mouse_up(key='left')
            except:
                pass
        except Exception as e:
            self.log_error(f"孟章操作循环异常: {e}")
            try:
                self.mouse_up(key='left')
            except:
                pass
        finally:
            time.sleep(1)
            click_x, click_y = self._get_scaled_coordinates(1025, 560)
            self.log_info(f"孟章：点击坐标 ({click_x}, {click_y}) 以关闭残留界面")
            self.click(click_x, click_y, after_sleep=0.5)
        self.log_info("孟章操作循环结束")

    def _yanuo_combat_loop(self, stop_event, boss_spawned, boss_dead):
        frame = self.frame
        if frame is None:
            self.log_error("雅诺：无法获取屏幕帧")
            return
        target_x, target_y = self._get_scaled_coordinates(1815, 900)
        self.log_info(f"雅诺：长按坐标 ({target_x}, {target_y})（已适配分辨率）")
        try:
            self.log_info("雅诺：按 Enter 键")
            self.send_key('enter')
            time.sleep(0.8)
            self.log_info("雅诺：按下左键，长按开始")
            self.mouse_down(target_x, target_y, key='left')
            while not stop_event.is_set() and not boss_dead.is_set():
                self._sleep_with_check(1.0, interval=1.0)
            self.log_info("雅诺：停止信号或BOSS死亡，释放左键")
            self.mouse_up(key='left')
        except TaskDisabledException:
            self.log_info("雅诺操作线程收到禁用信号，退出")
            try:
                self.mouse_up(key='left')
            except:
                pass
        except Exception as e:
            self.log_error(f"雅诺操作循环异常: {e}")
            try:
                self.mouse_up(key='left')
            except:
                pass
        finally:
            time.sleep(1)
            click_x, click_y = self._get_scaled_coordinates(1025, 560)
            self.log_info(f"雅诺：点击坐标 ({click_x}, {click_y}) 以关闭残留界面")
            self.click(click_x, click_y, after_sleep=0.5)
        self.log_info("雅诺操作循环结束")

    def _mengzhang_front_combat_loop(self, stop_event, boss_spawned, boss_dead):
        frame = self.frame
        if frame is None:
            self.log_error("孟章（前台）：无法获取屏幕帧")
            return
        h, w = frame.shape[:2]
        center_x = w // 2
        center_y = h // 2
        self.log_info(f"孟章（前台）：屏幕中心坐标 ({center_x}, {center_y})")
        source1_key = self._source_key
        source2_key = self._get_source_key2()
        try:
            self.log_debug("孟章（前台）：左键单击一次（初始）")
            self.mouse_down(center_x, center_y, key='left')
            self.sleep(0.05)
            self.mouse_up(key='left')
            self.sleep(0.1)
        except Exception as e:
            self.log_error(f"孟章（前台）初始单击异常: {e}")
            return
        while not stop_event.is_set() and not boss_dead.is_set():
            try:
                self.log_debug("孟章（前台）：长按左键50秒开始")
                self.mouse_down(center_x, center_y, key='left')
                start_time = time.time()
                while time.time() - start_time < 50:
                    if stop_event.is_set() or boss_dead.is_set():
                        break
                    self._sleep_with_check(1.0, interval=1.0)
                self.mouse_up(key='left')
                self.log_debug("孟章（前台）：释放左键")
                if stop_event.is_set() or boss_dead.is_set():
                    break
                self.log_debug(f"孟章（前台）：按源器2 ({source2_key})，等待15秒")
                self.send_key(source2_key)
                t_before = time.time()
                time.sleep(15)
                t_after = time.time()
                self.log_debug(f"孟章（前台）：源器2等待实际耗时 {t_after - t_before:.3f} 秒")
                if stop_event.is_set() or boss_dead.is_set():
                    break
                self.log_debug(f"孟章（前台）：按源器1 ({source1_key})，等待3秒")
                self.send_key(source1_key)
                t_before = time.time()
                time.sleep(3)
                t_after = time.time()
                self.log_debug(f"孟章（前台）：源器1等待实际耗时 {t_after - t_before:.3f} 秒")
            except TaskDisabledException:
                self.log_info("孟章（前台）操作线程收到禁用信号，退出")
                try:
                    self.mouse_up(key='left')
                except:
                    pass
                break
            except Exception as e:
                self.log_error(f"孟章（前台）操作循环异常: {e}")
                try:
                    self.mouse_up(key='left')
                except:
                    pass
                break
        self.log_info("孟章（前台）操作循环结束")

    def _yanuo_front_combat_loop(self, stop_event, boss_spawned, boss_dead):
        frame = self.frame
        if frame is None:
            self.log_error("雅诺（前台）：无法获取屏幕帧")
            return
        h, w = frame.shape[:2]
        center_x = w // 2
        center_y = h // 2
        self.log_info(f"雅诺（前台）：屏幕中心坐标 ({center_x}, {center_y})")
        try:
            self.mouse_down(center_x, center_y, key='left')
            self.sleep(0.05)
            self.mouse_up(key='left')
            self.sleep(0.1)
            self.log_info("雅诺（前台）：长按左键开始（将持续至BOSS死亡或超时），2秒后发送一次反引号键")
            self.mouse_down(center_x, center_y, key='left')
            start_time = time.time()
            key_sent = False
            while not stop_event.is_set() and not boss_dead.is_set():
                now = time.time()
                if not key_sent and (now - start_time >= 2.0):
                    self.send_key('`')
                    self.log_debug("雅诺（前台）：长按2秒后发送反引号键")
                    key_sent = True
                self._sleep_with_check(1.0, interval=1.0)
            self.log_info("雅诺（前台）：释放左键")
            self.mouse_up(key='left')
        except TaskDisabledException:
            self.log_info("雅诺（前台）操作线程收到禁用信号，退出")
            try:
                self.mouse_up(key='left')
            except:
                pass
        except Exception as e:
            self.log_error(f"雅诺（前台）操作循环异常: {e}")
            try:
                self.mouse_up(key='left')
            except:
                pass
        finally:
            self.log_info("雅诺（前台）操作线程结束")

    # ==================== 监控线程 ====================
    def _monitor_boss_status(self, stop_event, boss_spawned, boss_dead, timeout):
        start_time = time.time()
        boss_spawned_occurred = False
        while not stop_event.is_set() and not boss_dead.is_set():
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
                    self._sleep_with_check(1, interval=1.0)
                    continue
            else:
                if self._check_boss_ui_disappeared():
                    if self._confirm_boss_dead():
                        boss_dead.set()
                        self.log_info("监测到BOSS死亡（二次确认通过）！")
                        break
                    else:
                        self.log_debug("二次确认未通过，继续监控")
                self._sleep_with_check(1, interval=1.0)
        self.log_info("BOSS状态监测线程结束")

    def _monitor_boss_spawn_only(self, timeout):
        self.log_info(f"等待BOSS刷新，超时{timeout}秒...")
        start = time.time()
        while time.time() - start < timeout:
            if self._is_boss_spawned():
                self.log_info("检测到BOSS刷新！")
                return 'boss_found'
            self._sleep_with_check(2, interval=2.0)
        self.log_info(f"BOSS刷新超时（{timeout}秒）")
        return 'timeout'

    # ==================== 宝箱拾取 ====================
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
            self._sleep_with_check(0.5)
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
            self._sleep_with_check(0.5)
        return None

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

    def _nanyin_teleport_search(self):
        self.log_info("启动南音传送搜索")
        self.send_key('m')
        self._sleep_with_check(2)

        self.log_info("等待 nanyintp 出现，超时5秒，阈值0.75")
        start_time = time.time()
        nanyin_box = None
        while time.time() - start_time < 5:
            self._check_stopped()
            frame = self.frame
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
            self.log_info("南音传送：未找到 nanyintp，点击屏幕中心后继续后续步骤")
            self.click(0.5, 0.5)
            self._sleep_with_check(1)
        else:
            self._click_box_safe(nanyin_box, after_sleep=1)

        frame = self.frame
        if frame is None:
            self.log_error("南音传送：无法获取屏幕帧")
            return False
        h, w = frame.shape[:2]
        full_box = Box(0, 0, w, h)
        ocr_results = self.wait_ocr(box=full_box, match="虚空渊流", time_out=5, raise_if_not_found=False)

        if not ocr_results:
            self.log_error("南音传送：未找到虚空渊流，继续尝试下一步")
        else:
            self._click_box_safe(ocr_results[0], after_sleep=1)

        if not self._wait_and_click_feature('tp', timeout=5, after_sleep=1):
            self.log_error("南音传送：未找到 tp 图片")
            return False

        if not self._wait_and_click_feature('sure', timeout=10, after_sleep=8):
            self.log_error("南音传送：未找到 sure 图片")
            return False

        self.log_info("南音传送：等待传送后回到主页面...")
        if not self.wait_for_main_page_color(timeout=30):
            self.log_error("南音传送：未检测到主页面，但继续尝试下一步")

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
            if self._is_character_state_normal():
                self.log_info("状态已恢复正常")
                return True
            self.log_debug("按下S键 (0.2秒)")
            self.send_key_safe('s', down_time=0.2)
            self._sleep_with_check(0.2)
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

        try:
            while time.time() - start_time < max_walk_time:
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

            self._sleep_with_check(1)
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
            self.send_key_safe('f', down_time=0.05)
            frame = self.frame
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

    # ==================== 传送 ====================
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
        """传送至九域（基于格网修改，仅改一个坐标）"""
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
            (520, 725, 1),   # 原格网是 (1030, 725, 1)，九域改为 (520, 725, 1)
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

    # ==================== 搜索并拾取 ====================
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

    # ==================== 执行单个 BOSS 一轮 ====================
    def _execute_boss_round(self, boss_info, wait_timeout, combat_mode):
        boss_index = boss_info['index']
        boss_choice = boss_info['choice']
        search_mode = boss_info['search_mode']
        teleport = boss_info.get('teleport', '不传送')

        # 传送（单选）
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
        # '不传送' 则什么都不做

        # 打开地图进入 BOSS
        if not self._open_map_and_enter_boss():
            self.log_error("进入世界BOSS界面失败")
            return 'fail'

        # 选择 BOSS（含翻页重试，失败则跳过本次循环）
        if not self._select_boss_by_config(boss_choice):
            self.log_error(f"BOSS{boss_index} 选择失败，跳过本次循环")
            return 'fail'

        # 点击 gotoboss
        if not self._wait_and_click_feature('gotoboss', timeout=30, after_sleep=0):
            return 'fail'

        # 点击 shenlin
        if not self._wait_and_click_feature('shenlin', timeout=30, after_sleep=8):
            return 'fail'

        # 等待主页面并激活
        if not self._wait_main_page_and_activate():
            self.log_error("启动战斗流程失败")
            return 'fail'

        self.last_shenlin_time = time.time()

        # 战斗阶段
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
            # 其他战斗方式，双线程
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

            t_combat = threading.Thread(target=target, args=(stop_event, boss_spawned, boss_dead), daemon=True)
            t_combat.start()
            self.log_info("操作线程已启动，等待2秒后启动监控线程...")
            time.sleep(2)

            t_monitor = threading.Thread(
                target=self._monitor_boss_status,
                args=(stop_event, boss_spawned, boss_dead, wait_timeout),
                daemon=True
            )
            t_monitor.start()
            self.log_info("监控线程已启动，两者并行运行")

            start_monitor = time.time()
            while not boss_dead.is_set() and not stop_event.is_set():
                if not boss_spawned.is_set() and (time.time() - start_monitor > wait_timeout):
                    self.log_info(f"监测超时（{wait_timeout}秒），未检测到BOSS刷新，终止")
                    stop_event.set()
                    break
                self._sleep_with_check(0.2)

            stop_event.set()
            t_combat.join(timeout=2)
            t_monitor.join(timeout=2)

            if not boss_dead.is_set():
                if not boss_spawned.is_set():
                    return 'timeout'
                else:
                    return 'fail'
            else:
                self.log_info("检测到BOSS死亡，继续拾取流程")
                return self._search_and_pickup(search_mode)

    # ==================== 主循环 ====================
    def run(self):
        try:
            loop_mode = self.config.get('循环模式', '轮换')
            forward_time = self.config.get('前进时间', 3)
            wait_timeout = self.config.get('等待超时', 60)
            combat_mode = self.config.get('战斗方式', '自动战斗')

            # 构建启用的 BOSS 列表
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

            current_index = 0
            loop_count = 0

            while True:
                loop_count += 1
                self.log_info(f"--- 第 {loop_count} 次循环开始 ---")
                loop_start_time = time.time()

                # 神临冷却
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
                else:  # 专注
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