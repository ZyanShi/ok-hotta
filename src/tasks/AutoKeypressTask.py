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
            '按键': 'e',          # 配置项名称改为“按键”
        })
        self.config_description = {
            '按键间隔': '按下按键的时间间隔（秒）',
            '按键': '要按下的按键',   # 描述也同步改为“按键”
        }
        self.last_press_time = 0

    def run(self):
        key = None
        key_down = False
        try:
            key = self.config.get('按键', 'e')      # 读取时使用“按键”
            interval = self.config.get('按键间隔', 30)

            current_time = time.time()
            if current_time - self.last_press_time >= interval:
                self.log_info(f"自动按下按键 [{key}]")
                self.send_key_down(key)
                key_down = True
                self.sleep(0.1)
                self.send_key_up(key)
                key_down = False
                self.last_press_time = current_time
        except TaskDisabledException:
            pass
        except Exception as e:
            self.log_error(f"自动按键执行异常: {e}")
        finally:
            # 停止时可能正好卡在 sleep(0.1) 里，这里兜底抬起按键，
            # 否则这个键会一直处于按下状态（角色/界面会一直响应该按键）
            if key_down and key is not None:
                try:
                    self.send_key_up(key)
                except Exception as e:
                    self.log_error(f"松开按键 [{key}] 失败: {e}")