import time
from ok import Box, TaskDisabledException
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask


class LianHeZuoZhanTask(BaseQRSLTask):
    """联合作战自动化任务"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "联合作战"
        self.description = "矿砂"
        self.group_name = "精炼强化"
        self.group_icon = FluentIcon.UP
        self.icon = FluentIcon.PEOPLE

        # 配置项（UI显示顺序按字典定义顺序）
        self.default_config.update({
            '循环次数': 10000,
            '宝箱等待超时': 180,
            '启用前进': False,      # 前进开关
            '前进时间': 9,          # 前进时长（秒）
            '启用向右': False,      # 向右开关
            '向右时间': 3,          # 向右时长（秒）
        })

        self.config_description = {
            '循环次数': '循环执行副本的次数',
            '宝箱等待超时': '等待宝箱的超时时间（秒）',
            '启用前进': '是否执行前进步骤（若关闭则跳过前进，直接开启自动战斗）',
            '前进时间': '按W键前进的时间（秒）',
            '启用向右': '是否执行向右移动步骤（在前进之后执行）',
            '向右时间': '按D键向右移动的时间（秒）',
        }

    def run(self):
        """联合作战自动化流程"""
        try:
            self.log_info("===== 联合作战任务启动 =====", notify=True)

            max_loops = self.config.get('循环次数', 10000)
            chest_timeout = self.config.get('宝箱等待超时', 180)
            enable_forward = self.config.get('启用前进', False)
            forward_time = self.config.get('前进时间', 9)
            enable_right = self.config.get('启用向右', False)
            right_time = self.config.get('向右时间', 3)

            self.log_info(f"配置参数: 循环次数={max_loops}, 宝箱超时={chest_timeout}秒, "
                          f"启用前进={enable_forward}, 前进时间={forward_time}秒, "
                          f"启用向右={enable_right}, 向右时间={right_time}秒")

            loop_count = 0

            while loop_count < max_loops:
                loop_count += 1
                self.log_info(f"--- 第 {loop_count}/{max_loops} 次循环开始 ---")

                # 确保游戏在主页面
                self.log_info("检测是否在游戏主页面...")
                if not self.is_main_page():
                    self.log_error("无法进入游戏主页面，跳过本次循环")
                    self.sleep(5)
                    continue

                self.log_info("确认在主页面")

                # 进入副本
                self.log_info("尝试进入副本...")
                if not self.enter_dungeon():
                    self.log_error("进入副本失败，跳过本次循环")
                    self.sleep(5)
                    continue

                self.log_info("成功进入副本")

                # 前进步骤
                if enable_forward:
                    self.log_info(f"前进 {forward_time} 秒...")
                    self.send_key_safe('w', down_time=forward_time)
                else:
                    self.log_info("前进功能已禁用，跳过前进步骤")

                # 向右步骤（在前进之后执行）
                if enable_right:
                    self.log_info(f"向右移动 {right_time} 秒...")
                    self.send_key_safe('d', down_time=right_time)
                else:
                    self.log_info("向右功能已禁用，跳过向右步骤")

                # 开启自动战斗
                self.log_info("开启自动战斗...")
                self.start_auto_combat()
                self.sleep(2)

                # 等待宝箱出现
                self.log_info(f"等待宝箱出现（超时{chest_timeout}秒）...")
                start_time = time.time()
                found_opened_chest = False
                found_unopened_chest = False
                chest_box = None

                while time.time() - start_time < chest_timeout:
                    frame = self.frame
                    if frame is None:
                        self.sleep(0.5)
                        continue
                    height, width = frame.shape[:2]
                    full_box = Box(0, 0, width, height)

                    opened_box = self.find_one('opened chest', threshold=0.7)
                    if opened_box:
                        self.log_info("检测到已打开的宝箱")
                        found_opened_chest = True
                        break

                    for name in ['chest1', 'chest2', 'chest3', 'chest4', 'chest5']:
                        result = self.find_feature(name, box=full_box, threshold=0.8)
                        if result:
                            chest_box = result[0]
                            self.log_info(f"检测到未打开的宝箱: {name}")
                            found_unopened_chest = True
                            break

                    if found_opened_chest or found_unopened_chest:
                        break

                    self.sleep(0.5)

                # 根据宝箱状态执行操作
                if found_opened_chest:
                    self.log_info("检测到已打开的宝箱，直接退出副本...")
                elif found_unopened_chest and chest_box:
                    self.log_info("检测到未打开的宝箱，尝试接近并打开...")
                    remaining_time = chest_timeout - (time.time() - start_time)
                    success = self.approach_chest(max_walk_time=remaining_time)
                    if success:
                        self.log_info("成功打开宝箱")
                    else:
                        self.log_error("打开宝箱失败")
                else:
                    self.log_error(f"{chest_timeout}秒内未找到任何宝箱，退出副本重试")

                # 退出副本
                self.log_info("退出副本...")
                self.exit_dungeon()

                self.log_info(f"第 {loop_count} 次循环完成")

            # 循环正常结束
            self.log_info(f"===== 联合作战任务结束，共完成 {loop_count} 次循环 =====", notify=True)

        except TaskDisabledException:
            # 用户手动停止，仅记录信息，不视为错误
            self.log_info("联合作战任务被用户手动停止")
        except Exception as e:
            self.log_error(f"任务执行过程中出现异常: {e}", exception=e, notify=True)
            self.screenshot("lianhezuozhan_error")
            raise   # 重新抛出，让框架知道任务异常结束