# src/tasks/JieXianMaoDianTask.py

import time
from ok import TaskDisabledException, Box
from qfluentwidgets import FluentIcon
from src.tasks.BaseQRSLTask import BaseQRSLTask

class JieXianMaoDianTask(BaseQRSLTask):
    """
    解限锚点任务
    检测指定区域内的文字，匹配成功后依次点击玩家头像、申请入队、传送、确认传送，
    同时每隔2秒检测新消息区域并自动点击。
    点击确认后播放声音提示。
    支持设置排除文字，当检测到的文本包含排除词时忽略。
    新增：完全匹配开关，可控制是否要求文字与关键词完全一致。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "解限锚点"
        self.description = "检测文字后自动点击玩家头像、申请入队、传送、确认传送，多个关键词用英文逗号分隔"
        self.icon = FluentIcon.PIN

        # 默认配置
        self.default_config.update({
            '模式选择': '半自动',
            '完全匹配': True,  # 新增：默认开启完全匹配
            '检测文字': '2饰,3饰,2X饰品,3X饰品,2X时装,3X时装,2X小垃圾,3X小垃圾,2X载具,3X载具,二饰,三饰,二星时装,三星时装,20,30,二十,三十',
            '排除文字': '吃,我,蹲,有,300,200,还,打,爆率,上,能,行,点,来,测,的,期,给,没,拉,不,呢',
            '申请入队延迟(ms)': 500,  # 点击玩家头像后等待时间
        })

        self.config_description = {
            '完全匹配': '开启时，要求检测到的文字与关键词完全一致；关闭时，文字包含关键词即触发',
            '模式选择': '选择任务模式',
            '申请入队延迟(ms)': '点击玩家头像后等待时间（毫秒）',

            # 检测文字和排除文字的描述在基类中已自动处理，无需重复
        }

        # 显式定义下拉框和复选框类型
        self.config_type = {
            '模式选择': {'type': 'drop_down', 'options': ['半自动']},
        }

        # 原始脚本的默认坐标（1080p 分辨率）
        self.DEFAULT_CLICK_POSITIONS = [
            (265, 869),   # 1.玩家头像
            (316, 772),   # 2.申请入队
            (1530, 297),  # 3.传送
            (1242, 579)   # 4.确认传送
        ]
        self.DEFAULT_DETECT_REGION = (360, 879, 513, 916)  # 主检测区域
        self.MSG_CHECK_REGION = (760, 900, 920, 940)       # 新消息检测区域

    def run(self):
        try:
            self.log_info("===== 解限锚点任务启动 =====", notify=True)

            # 1. 读取并验证配置
            target_raw = self.config.get('检测文字', '').strip()
            if not target_raw:
                self.log_error("未设置检测文字，任务终止")
                return
            keywords = [kw.strip() for kw in target_raw.split(',') if kw.strip()]
            if not keywords:
                self.log_error("检测文字格式错误，请用英文逗号分隔多个关键词")
                return

            exclude_raw = self.config.get('排除文字', '').strip()
            exclude_words = [w.strip() for w in exclude_raw.split(',') if w.strip()] if exclude_raw else []

            mode = self.config.get('模式选择', '半自动')
            exact_match = self.config.get('完全匹配', True)  # 读取完全匹配开关
            self.log_info(f"当前模式: {mode}")
            self.log_info(f"完全匹配模式: {'开启' if exact_match else '关闭'}")

            # 读取申请入队延迟
            delay_apply = self.config.get('申请入队延迟(ms)', 500) / 1000.0

            # 2. 获取缩放后的坐标
            self.next_frame()
            click_points = []
            for x, y in self.DEFAULT_CLICK_POSITIONS:
                scaled_x, scaled_y = self._get_scaled_coordinates(x, y)
                click_points.append((scaled_x, scaled_y))

            # 主检测区域缩放
            x1, y1, x2, y2 = self.DEFAULT_DETECT_REGION
            x1_scaled, y1_scaled = self._get_scaled_coordinates(x1, y1)
            x2_scaled, y2_scaled = self._get_scaled_coordinates(x2, y2)
            if x1_scaled > x2_scaled:
                x1_scaled, x2_scaled = x2_scaled, x1_scaled
            if y1_scaled > y2_scaled:
                y1_scaled, y2_scaled = y2_scaled, y1_scaled
            detect_box = Box(x1_scaled, y1_scaled,
                             width=x2_scaled - x1_scaled,
                             height=y2_scaled - y1_scaled)

            # 新消息检测区域缩放
            mx1, my1, mx2, my2 = self.MSG_CHECK_REGION
            mx1_scaled, my1_scaled = self._get_scaled_coordinates(mx1, my1)
            mx2_scaled, my2_scaled = self._get_scaled_coordinates(mx2, my2)
            if mx1_scaled > mx2_scaled:
                mx1_scaled, mx2_scaled = mx2_scaled, mx1_scaled
            if my1_scaled > my2_scaled:
                my1_scaled, my2_scaled = my2_scaled, my1_scaled
            msg_box = Box(mx1_scaled, my1_scaled,
                          width=mx2_scaled - mx1_scaled,
                          height=my2_scaled - my1_scaled)

            self.log_info(f"主检测区域: ({x1_scaled},{y1_scaled})-({x2_scaled},{y2_scaled})")
            self.log_info(f"新消息区域: ({mx1_scaled},{my1_scaled})-({mx2_scaled},{my2_scaled})")
            self.log_info(f"点击坐标: {click_points}")
            if exclude_words:
                self.log_info(f"排除文字: {exclude_words}")
            self.log_info(f"申请入队延迟: {delay_apply}s")

            # 3. 循环检测（主文字 + 新消息）
            last_msg_check = 0
            matched_text = None

            while True:
                # 3.1 新消息检测（每2秒一次）
                now = time.time()
                if now - last_msg_check >= 2:
                    last_msg_check = now
                    try:
                        msg_results = self.ocr(box=msg_box, target_height=540)
                        if msg_results:
                            for box in msg_results:
                                text = box.name
                                if "新消息" in text:
                                    self.log_info(f"✅ 检测到新消息: {text}")
                                    self.click_box(box)
                                    self.sleep(0.2)
                                    break
                    except Exception as e:
                        self.log_error(f"新消息检测异常: {e}")

                # 3.2 主文字检测（带排除逻辑和完全匹配判断）
                ocr_results = self.ocr(box=detect_box, target_height=540)
                if ocr_results:
                    for box in ocr_results:
                        text = box.name
                        # 检查排除词
                        if exclude_words and any(ex in text for ex in exclude_words):
                            self.log_debug(f"忽略包含排除词的文本: {text}")
                            continue

                        for kw in keywords:
                            if exact_match:
                                # 完全匹配：文本必须与关键词完全相同（忽略首尾空格）
                                if text.strip() == kw.strip():
                                    matched_text = kw
                                    self.log_info(f"✅ 检测到目标文字（完全匹配）: {text} (关键词: {kw})")
                                    break
                            else:
                                # 包含匹配：关键词是文本的子串
                                if kw in text:
                                    matched_text = kw
                                    self.log_info(f"✅ 检测到目标文字（包含匹配）: {text} (关键词: {kw})")
                                    break

                        if matched_text:
                            break
                if matched_text:
                    break

                self.log_debug(f"未检测到 {keywords}，继续...")
                self.sleep(0.5)

            # 4. 执行完整点击序列（四步）
            self.log_info("开始执行点击序列")
            try:
                # 第一步：玩家头像
                self.click(*click_points[0])
                self.log_info(f"✅ 点击玩家头像 {click_points[0]}")
                self.sleep(delay_apply)

                # 第二步：申请入队
                self.click(*click_points[1])
                self.log_info(f"✅ 点击申请入队 {click_points[1]}")

                # 第三步：等待3秒后点击传送
                self.log_info("⏳ 等待3秒后点击传送...")
                self.sleep(3)
                self.click(*click_points[2])
                self.log_info(f"✅ 点击传送 {click_points[2]}")

                # 第四步：等待1秒后点击确认
                self.log_info("⏳ 等待1秒后点击确认...")
                self.sleep(1)
                self.click(*click_points[3])
                self.log_info(f"✅ 点击确认传送 {click_points[3]}")

                # 播放声音提示：1000Hz 蜂鸣 0.5秒
                try:
                    import winsound
                    winsound.Beep(1000, 500)
                except Exception as e:
                    self.log_debug(f"播放声音失败: {e}")

                self.log_info("✅ 所有操作完成", notify=True)
                self.notification("解限锚点任务完成", "已点击确认传送")

            except Exception as e:
                self.log_error(f"点击操作失败: {e}")
                self.screenshot("click_error")

        except TaskDisabledException:
            self.log_info("解限锚点任务被用户手动停止")
        except Exception as e:
            self.log_error(f"解限锚点任务异常: {e}", notify=True)
            self.screenshot("jiexian_error")
            raise