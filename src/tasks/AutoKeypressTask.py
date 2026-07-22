import time
from ok import TriggerTask, TaskDisabledException
from qfluentwidgets import FluentIcon

class AutoKeypressTask(TriggerTask):
    """自动按键触发器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "自动按键"
        self.description = "每隔一段时间自动按下指定按键"
        self.icon = FluentIcon.SYNC
        self.default_config.update({
            '按键间隔': 30,
            '技能键': 'e',          # 移入任务自身配置
        })
        self.config_description = {
            '按键间隔': '按下按键的时间间隔（秒）',
            '技能键': '要按下的按键',
        }
        self.last_press_time = 0

    def run(self):
        try:
            skill_key = self.config.get('技能键', 'e')
            interval = self.config.get('按键间隔', 30)

            current_time = time.time()
            if current_time - self.last_press_time >= interval:
                self.log_info(f"自动按下按键 [{skill_key}]")
                self.send_key_down(skill_key)
                self.sleep(0.1)
                self.send_key_up(skill_key)
                self.last_press_time = current_time
        except TaskDisabledException:
            pass
        except Exception as e:
            self.log_error(f"自动按键执行异常: {e}")