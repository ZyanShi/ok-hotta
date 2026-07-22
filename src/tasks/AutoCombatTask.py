import time
import re
from ok import TaskDisabledException, Box
from src.tasks.BaseQRSLTask import BaseQRSLTask
from qfluentwidgets import FluentIcon


class AutoCombatTask(BaseQRSLTask):
    """自动战斗任务"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动战斗（前台）"
        self.description = "自动切换武器并执行战斗逻辑"
        self.icon = FluentIcon.SYNC

        # 配置项（与原来保持一致）
        self.default_config.update({
            '武器1': '镇魂曲',
            '武器2': '小小飓风',
            '武器3': '波吕克斯',
            '武器1按键': '1',
            '武器2按键': '2',
            '武器3按键': '3',
            '技能按键': 'e',
            '源器1按键': 'x',
            '源器2按键': 'c',
        })

        self.config_description = {
            '武器1': '选择武器1',
            '武器2': '选择武器2',
            '武器3': '选择武器3',
            '武器1按键': '武器1的快捷键',
            '武器2按键': '武器2的快捷键',
            '武器3按键': '武器3的快捷键',
            '技能按键': '技能按键的快捷键',
            '源器1按键': '源器1的快捷键',
            '源器2按键': '源器2的快捷键',
        }

        # 下拉框配置（保留原有选项）
        self.config_type['武器1'] = {'type': 'drop_down', 'options': ['镇魂曲']}
        self.config_type['武器2'] = {'type': 'drop_down', 'options': ['小小飓风']}
        self.config_type['武器3'] = {'type': 'drop_down', 'options': ['波吕克斯']}

        self.weapon_method_map = {
            '镇魂曲': 'zhenhunqu',
            '小小飓风': 'xiaoxiaojufeng',
            '波吕克斯': 'bolukes',
        # 将来扩展：添加新武器名称和对应方法名
        }
    # ---------- 数字检测函数 ----------
    def _is_digit_present(self) -> bool:
        # 相对坐标（基于1920x1080换算，兼容任意分辨率）
        x1, y1 = 1715 / 1920, 950 / 1080  # 0.8932, 0.8796
        x2, y2 = 1795 / 1920, 1035 / 1080  # 0.9349, 0.9583
        try:
            results = self.ocr(x=x1, y=y1, to_x=x2, to_y=y2, target_height=540)
            for res in results:
                text = res.name.strip()
                if re.search(r'\d', text):
                    return True
        except Exception as e:
            self.log_debug(f"数字检测OCR异常: {e}")
        return False

    # ---------- 武器连招函数 ----------
    def zhenhunqu(self):
        """镇魂曲连招（延时优化版）"""
        weapon_key = self.config.get('武器1按键')
        skill_key = self.config.get('技能按键')

        self.send_key(weapon_key)
        self.sleep(0.1)
        self.send_key('space')
        self.sleep(0.5)
        self.send_key(skill_key)
        self.sleep(1.7)
        self.send_key(skill_key)
        self.sleep(1.8)

    def xiaoxiaojufeng(self):
        """小小飓风连招（延时调整）"""
        weapon_key = self.config.get('武器2按键')
        skill_key = self.config.get('技能按键')

        self.send_key(weapon_key)
        self.sleep(0.3)

        max_attempts = 20
        for _ in range(max_attempts):
            self.send_key(skill_key)
            self.sleep(0.5)
            if self._is_digit_present():
                self.log_info("小小飓风检测到数字，跳出循环")
                break
        else:
            self.log_warning("小小飓风未检测到数字，已达最大尝试次数")

    def bolukes(self):
        """波吕克斯连招（绝对坐标长按，确保生效）"""
        weapon_key = self.config.get('武器3按键')
        skill_key = self.config.get('技能按键')
        source1_key = self.config.get('源器1按键')

        # 1. 按武器3，空格，重复三次（右键+左键）
        self.send_key(weapon_key)
        self.sleep(0.3)
        self.send_key('space')
        self.sleep(0.9)
        for _ in range(3):
            self.right_click(0.5, 0.5)  # 右键点击中心
            self.sleep(0.3)
            self.click(0.5, 0.5)  # 左键点击中心
            self.sleep(0.8)

        # 2. 按技能键两次（修改为技能键）
        self.send_key(skill_key)
        self.sleep(0.2)
        self.send_key(skill_key)
        self.sleep(1.0)

        # 3. 按源器1
        self.send_key(source1_key)
        self.sleep(0.1)

        # 4. 长按鼠标左键4秒（使用绝对坐标）
        # 获取当前屏幕帧尺寸，计算中心点绝对坐标
        frame = self.frame
        if frame is None:
            return
        h, w = frame.shape[:2]
        center_x = w // 2
        center_y = h // 2

        self.mouse_down(center_x, center_y, key='left')  # 按下
        self.sleep(4.0)  # 保持4秒
        self.mouse_up(key='left')  # 释放

        # 5. 21秒循环（保持原逻辑）
        start_time = time.time()
        last_combo_time = start_time
        end_time = start_time + 21.0

        while time.time() < end_time:
            self.click(0.5, 0.5)
            self.sleep(0.5)

            current_time = time.time()
            if current_time - last_combo_time >= 8.0:
                for _ in range(2):
                    self.right_click(0.5, 0.5)
                    self.sleep(0.5)
                    self.click(0.5, 0.5)
                    self.sleep(1.0)
                last_combo_time = current_time

    # ---------- 主循环 ----------
    def run(self):
        try:
            self.log_info("自动战斗任务启动，延迟2秒...")
            self.sleep(2)

            # 获取配置的武器顺序（按1,2,3）
            weapon_keys = ['武器1', '武器2', '武器3']  # 这三个配置项的名称
            weapon_names = [self.config.get(key, '') for key in weapon_keys]
            # 过滤掉空值（如果用户未选择）
            valid_weapons = [name for name in weapon_names if name]

            while True:
                for weapon_name in valid_weapons:
                    method_name = self.weapon_method_map.get(weapon_name)
                    if method_name:
                        method = getattr(self, method_name, None)
                        if method:
                            method()  # 执行对应的连招
                        else:
                            self.log_error(f"未找到武器 '{weapon_name}' 对应的方法 '{method_name}'")
                    else:
                        self.log_error(f"武器 '{weapon_name}' 未在映射表中定义，跳过")
                # 循环完成后继续下一轮（无需额外间隔）
        except TaskDisabledException:
            self.log_info("任务被禁用，退出")
        except Exception as e:
            self.log_error(f"自动战斗执行异常: {e}")
            self.screenshot("auto_combat_error")
            raise