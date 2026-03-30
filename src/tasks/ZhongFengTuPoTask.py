import time
from ok import TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask


class ZhongFengTuPoTask(BaseQRSLTask):
    """众峰突破自动化任务
    自动完成众峰突破刷取潜能点。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "众峰突破"
        self.description = "自动完成众峰突破刷取潜能点"
        self.icon = FluentIcon.FLAG

        self.default_config.update({
            '关卡选择': '当前关卡',
            '循环次数': 10000,
        })
        self.config_description = {
            '关卡选择': '选择要挑战的关卡',
            '循环次数': '任务执行的最大循环次数',
        }
        self.config_type['关卡选择'] = {
            'type': "drop_down",
            'options': ['当前关卡']
        }

    def _wait_and_click_feature(self, feature_name, timeout, after_sleep=0, raise_if_not_found=False):
        """等待指定特征图片出现并点击"""
        box = self.wait_feature(feature_name, time_out=timeout, raise_if_not_found=False)
        if box:
            self.log_info(f"找到并点击 [{feature_name}]")
            self._click_box_safe(box)
            if after_sleep > 0:
                self.sleep(after_sleep)
            return True
        self.log_error(f"等待 [{feature_name}] 超时 ({timeout}秒)")
        if raise_if_not_found:
            raise Exception(f"找不到特征 {feature_name}")
        return False

    def _wait_for_any_feature(self, feature_names, timeout, after_sleep=0):
        """等待任意一个特征图片出现，返回 (box, name)"""
        start = time.time()
        while time.time() - start < timeout:
            for name in feature_names:
                box = self.find_one(name, threshold=0.7)
                if box:
                    self.log_info(f"检测到特征 [{name}]")
                    if after_sleep > 0:
                        self.sleep(after_sleep)
                    return box, name
            self.sleep(0.5)
        self.log_error(f"等待特征 {feature_names} 超时 ({timeout}秒)")
        return None, None

    def run(self):
        """任务主循环"""
        try:
            self.log_info("===== 众峰突破任务启动 =====", notify=True)
            max_loops = self.config.get('循环次数', 10000)
            loop_count = 0

            while loop_count < max_loops:
                loop_count += 1
                self.log_info(f"--- 第 {loop_count}/{max_loops} 次循环开始 ---")

                if not self.is_main_page():
                    self.log_error("无法进入游戏主页面，跳过本次循环")
                    self.sleep(5)
                    continue

                self.log_info("按ESC键打开菜单")
                self.send_key_safe('esc', down_time=0.02)
                self.sleep(1)

                # 修改点：等待 guild1 或 guild2 出现并点击
                box, name = self._wait_for_any_feature(['guild1', 'guild2'], timeout=5, after_sleep=0)
                if box is None:
                    self.log_error("未找到工会图标（guild1/guild2），跳过本次循环")
                    self.sleep(5)
                    continue
                self.log_info(f"找到并点击工会图标 [{name}]")
                self._click_box_safe(box)

                if not self._wait_and_click_feature('huodong', timeout=10, after_sleep=0):
                    self.log_error("未找到活动图标，跳过本次循环")
                    self.sleep(5)
                    continue

                if not self._wait_and_click_feature('zhongfengtupo', timeout=10, after_sleep=0):
                    self.log_error("未找到众峰突破图标，跳过本次循环")
                    self.sleep(5)
                    continue

                box, name = self._wait_for_any_feature(['back', 'jinruzhandou'], timeout=10)
                if name is None:
                    self.log_error("既未出现返回按钮也未出现进入战斗按钮，跳过本次循环")
                    self.sleep(5)
                    continue

                if name == 'jinruzhandou':
                    self.log_info("检测到进入战斗按钮，点击它")
                    self._click_box_safe(box)
                    self.sleep(1)

                self.log_info("已进入众峰突破界面")

                level = self.config.get('关卡选择', '当前关卡')
                if level == '当前关卡':
                    if not self._wait_and_click_feature('enterchallenge', timeout=10, after_sleep=0):
                        self.log_error("未找到进入挑战按钮，跳过本次循环")
                        self.sleep(5)
                        continue
                else:
                    self.log_info(f"关卡 [{level}] 尚未实现，跳过本次循环")
                    self.sleep(5)
                    continue

                if not self._wait_and_click_feature('sure', timeout=5, after_sleep=10):
                    self.log_error("未找到确认按钮，跳过本次循环")
                    self.sleep(5)
                    continue

                self.log_info("等待退出按钮变白...")
                if not self.wait_for_exit_button_white(timeout=60):
                    self.log_error("等待退出按钮变白超时，跳过本次循环")
                    self.sleep(5)
                    continue

                self.log_info("退出副本")
                self.exit_dungeon()

                if not self.wait_for_main_page_color(timeout=60):
                    self.log_error("等待主页颜色超时，跳过本次循环")
                    self.sleep(5)
                    continue

                self.log_info(f"第 {loop_count} 次循环完成")

            self.log_info(f"===== 众峰突破任务结束，共完成 {loop_count} 次循环 =====", notify=True)

        except TaskDisabledException:
            self.log_info("众峰突破任务被用户手动停止")
        except Exception as e:
            self.log_error(f"众峰突破任务异常: {e}", notify=True)
            self.screenshot("zhongfengtupo_error")
            raise