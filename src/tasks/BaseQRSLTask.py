import time
from ok import BaseTask, Box
from ok import TaskDisabledException

class BaseQRSLTask(BaseTask):
    """QRSL游戏专用基础任务类"""

    CHEST_NAMES = ['chest1', 'chest2', 'chest3', 'chest4', 'chest5']
    ENTER_TEAM_COORDS = (1900, 320)
    AUTO_COMBAT_COORDS = (1160, 930)
    EXIT_CHECK_COORDS = (267, 65)
    MAIN_PAGE_COORDS = (22, 63)
    TARGET_CHECK_COORDS = (863, 1028)
    REF_RESOLUTION = (1920, 1080)
    TARGET_COLOR_BGR = (237, 166, 62)
    TARGET_CHECK_COLOR = (236, 236, 236)

    def _get_scaled_coordinates(self, ref_x, ref_y):
        frame = self.frame
        if frame is None:
            return ref_x, ref_y
        height, width = frame.shape[:2]
        scale_x = width / self.REF_RESOLUTION[0]
        scale_y = height / self.REF_RESOLUTION[1]
        return int(ref_x * scale_x), int(ref_y * scale_y)

    def _execute_atomic_operation(self, operation_func):
        try:
            operation_func()
            return True
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error(f"操作失败: {e}")
            return False

    def _click_safe(self, x, y, **kwargs):
        """安全的点击方法"""
        def operation():
            self.click(x, y, **kwargs)
        return self._execute_atomic_operation(operation)

    def _click_box_safe(self, box, **kwargs):
        """安全的点击Box方法"""
        def operation():
            self.click_box(box, **kwargs)
        return self._execute_atomic_operation(operation)

    def _click_with_alt(self, x, y, alt_down_delay=0.8, click_delay=1.5, alt_key='alt'):
        def operation():
            self.send_key_down(alt_key)
            self.sleep(alt_down_delay)
            self._click_safe(x, y, move_back=True, down_time=0.01, interval=0.4)
            self.sleep(click_delay)
            self.send_key_up(alt_key)
        return self._execute_atomic_operation(operation)

    def _is_white_color(self, pixel_bgr, tolerance=10):
        return all(245 <= color <= 255 for color in pixel_bgr)

    def _color_similar(self, color1, color2, tolerance=30):
        return sum(abs(int(color1[i]) - int(color2[i])) for i in range(3)) < tolerance

    def check_exit_button_color(self):
        frame = self.frame
        if frame is None:
            return False
        check_x, check_y = self._get_scaled_coordinates(*self.EXIT_CHECK_COORDS)
        height, width = frame.shape[:2]
        if check_y >= height or check_x >= width:
            return False
        pixel_color = frame[check_y, check_x]
        return self._is_white_color(pixel_color)

    def check_target_color(self):
        frame = self.frame
        if frame is None:
            return False
        target_x, target_y = self._get_scaled_coordinates(*self.TARGET_CHECK_COORDS)
        height, width = frame.shape[:2]
        if target_y >= height or target_x >= width:
            return False
        pixel_color = frame[target_y, target_x]
        return self._color_similar(pixel_color, self.TARGET_CHECK_COLOR, tolerance=10)

    def wait_for_exit_button_white(self, timeout=60):
        self.log_info(f"等待进入副本，超时{timeout}秒...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_exit_button_color():
                self.log_info("成功进入副本")
                return True
            self.sleep(0.5)
        self.log_error("等待进入副本超时")
        return False

    def wait_for_target_color(self, timeout):
        self.log_info(f"等待目标颜色出现，超时{timeout}秒...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_target_color():
                self.log_info("检测到目标颜色")
                return True
            self.sleep(0.5)
        self.log_error("等待目标颜色超时")
        return False

    def enter_team(self, alt_down_delay=0.8, click_delay=1, alt_key='alt'):
        target_x, target_y = self._get_scaled_coordinates(*self.ENTER_TEAM_COORDS)
        for attempt in range(10):
            success = self._click_with_alt(target_x, target_y, alt_down_delay, click_delay, alt_key)
            if not success:
                continue
            self.sleep(1)
            attend_box = self.find_one('attend', threshold=0.75)
            if attend_box:
                self.sleep(0.5)
                return True, attend_box
            else:
                self.sleep(1)
        self.log_error("进入队伍失败")
        return False, None

    def start_auto_combat(self, alt_down_delay=0.8, click_delay=1.5, alt_key='alt'):
        target_x, target_y = self._get_scaled_coordinates(*self.AUTO_COMBAT_COORDS)
        success = self._click_with_alt(target_x, target_y, alt_down_delay, click_delay, alt_key)
        return success

    def enter_dungeon(self):
        self.log_info("开始进入副本流程...")
        success, attend_box = self.enter_team(alt_down_delay=0.8, click_delay=1)
        if not success or not attend_box:
            self.log_error("进入队伍失败，无法继续进入副本")
            return False
        self.log_info("点击'参加'按钮")
        self._click_box_safe(attend_box, after_sleep=1)
        enter_box = self.wait_feature('enter', time_out=10, threshold=0.75)
        if not enter_box:
            self.log_error("未找到'进入'按钮")
            return False
        self._click_box_safe(enter_box, after_sleep=0.5)
        return self.wait_for_exit_button_white(timeout=60)

    def exit_dungeon(self):
        frame = self.frame
        if frame is None:
            return False
        check_x, check_y = self._get_scaled_coordinates(*self.EXIT_CHECK_COORDS)
        pixel_color = frame[check_y, check_x]
        if not self._is_white_color(pixel_color):
            return False
        if not self._click_with_alt(check_x, check_y, alt_down_delay=0.8, click_delay=1.5):
            return False
        confirm_box = self.wait_feature('confirm', time_out=10, threshold=0.7)
        if confirm_box:
            confirm_center = confirm_box.center()
            if self._click_with_alt(confirm_center[0], confirm_center[1], alt_down_delay=0.8, click_delay=1.5):
                self.sleep(10)
                return True
        return False

    def is_main_page(self):
        max_attempts = 30
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            frame = self.frame
            if frame is None:
                self.sleep(1)
                continue
            height, width = frame.shape[:2]
            current_x, current_y = self._get_scaled_coordinates(*self.MAIN_PAGE_COORDS)
            pixel_color = frame[current_y, current_x]
            if self._color_similar(pixel_color, self.TARGET_COLOR_BGR):
                self.sleep(2)
                return True
            back_box = self.find_one('back', threshold=0.75)
            if back_box:
                self._click_box_safe(back_box, after_sleep=2)
                self.next_frame()
                continue
            cancel_box = self.find_one('cancel', threshold=0.75)
            if cancel_box:
                self._click_box_safe(cancel_box, after_sleep=2)
                self.next_frame()
                continue
            check_x, check_y = self._get_scaled_coordinates(*self.EXIT_CHECK_COORDS)
            pixel_color = frame[check_y, check_x]
            if self._is_white_color(pixel_color):
                self.exit_dungeon()
                self.sleep(10)
                self.next_frame()
                continue
            self.back(after_sleep=2)
            self.next_frame()
        return False

    def wait_any_chest(self, time_out=30):
        start_time = time.time()
        while time.time() - start_time < time_out:
            frame = self.frame
            if frame is None:
                self.sleep(0.5)
                continue
            height, width = frame.shape[:2]
            full_box = Box(0, 0, width, height)
            for name in self.CHEST_NAMES:
                result = self.find_feature(name, box=full_box, threshold=0.8)
                if result:
                    return result[0]
            self.sleep(1)
        return None

    def approach_chest(self, max_walk_time=60):
        target_chest = self.wait_any_chest(time_out=30)
        if target_chest is None:
            return False
        start_time = time.time()
        chest_disappear_count = 0
        last_key_press_time = 0
        key_press_interval = 0.15
        locked_chest_type = None
        try:
            while time.time() - start_time < max_walk_time:
                self.sleep(0)   # 检查任务是否被停止，保证停止信号能及时响应
                current_time = time.time()
                if self.find_one('opened chest', threshold=0.7):
                    self.sleep(0.5)
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
                            return False
                else:
                    chest_disappear_count = 0
                target_chest = current_chest
                chest_x, chest_y = target_chest.center()
                if not self._adjust_position(chest_x, chest_y, screen_center_x, width, height):
                    last_key_press_time = current_time
        except Exception as e:
            self.log_error(f"接近宝箱异常: {e}")
            return False
        return bool(self.find_one('opened chest', threshold=0.7))

    def _get_closest_box(self, boxes, target_box):
        last_center = target_box.center()
        distances = [abs(r.center()[0] - last_center[0]) + abs(r.center()[1] - last_center[1]) for r in boxes]
        closest_idx = distances.index(min(distances))
        return boxes[closest_idx]

    def _reacquire_chest(self):
        for _ in range(10):
            frame = self.frame
            if frame is None:
                continue
            height, width = frame.shape[:2]
            full_box = Box(0, 0, width, height)
            for name in self.CHEST_NAMES:
                results = self.find_feature(name, box=full_box, threshold=0.6)
                if results:
                    return results[0]
            self.sleep(0.5)
        return None

    def _adjust_position(self, chest_x, chest_y, screen_center_x, width, height):
        center_tolerance = int(width * 0.05)
        center_min = screen_center_x - center_tolerance
        center_max = screen_center_x + center_tolerance
        vertical_threshold = int(height * (800 / 1080))
        left_boundary = int(width * (450 / 1920))
        right_boundary = int(width * (1470 / 1920))
        if chest_x < center_min or chest_x > center_max:
            horizontal_error = chest_x - screen_center_x
            if chest_x < left_boundary or chest_x > right_boundary:
                key = 'a' if horizontal_error < 0 else 'd'
                down_time = 1.0
            else:
                key = 'a' if horizontal_error < 0 else 'd'
                down_time = 0.1
            self._send_key_safe(key, down_time)
            return False
        if chest_y < vertical_threshold:
            self._send_key_safe('w', 1.0)
        else:
            self._send_key_safe('s', 1.0)
        return True

    def _send_key_safe(self, key, down_time=0.1):
        try:
            self.send_key_down(key)
            self.sleep(down_time)
        finally:
            self.send_key_up(key)   # 确保按键被释放，无论是否发生异常

    def send_key_safe(self, key, down_time=0.1):
        self._send_key_safe(key, down_time)

    def wait_for_main_page_color(self, timeout=60):
        self.log_info(f"等待主页颜色出现，超时{timeout}秒...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            frame = self.frame
            if frame is None:
                self.sleep(0.5)
                continue
            x, y = self._get_scaled_coordinates(*self.MAIN_PAGE_COORDS)
            height, width = frame.shape[:2]
            if y >= height or x >= width:
                self.sleep(0.5)
                continue
            pixel_color = frame[y, x]
            if self._color_similar(pixel_color, self.TARGET_COLOR_BGR, tolerance=30):
                self.log_info("检测到主页颜色")
                return True
            self.sleep(0.5)
        self.log_error("等待主页颜色超时")
        return False