import os
import numpy as np
from ok import ConfigOption

version = "dev"

# 游戏按键配置（包含源器键和技能键）
key_config_option = ConfigOption('游戏按键配置', {
    '源器键1': 'x',
    '源器键2': 'c',


}, description='游戏技能按键')

def make_bottom_right_black(frame):
    try:
        height, width = frame.shape[:2]
        black_width = int(0.13 * width)
        black_height = int(0.025 * height)
        start_x = width - black_width
        start_y = height - black_height
        black_rect = np.zeros((black_height, black_width, frame.shape[2]), dtype=frame.dtype)
        frame[start_y:height, start_x:width] = black_rect
        return frame
    except Exception as e:
        print(f"Error processing frame: {e}")
        return frame

config = {
    'debug': False,
    'use_gui': True,
    'config_folder': 'configs',
    'global_configs': [key_config_option],  # 只保留一个游戏按键配置
    'screenshot_processor': make_bottom_right_black,
    'gui_icon': 'icons/icon.png',
    'wait_until_before_delay': 0,
    'wait_until_check_delay': 0,
    'wait_until_settle_time': 0,
    'ocr': {
        'lib': 'onnxocr',
        'params': {
            'use_openvino': True,
        }
    },
    'windows': {
        'exe': ['QRSL.exe'],
        'hwnd_class': 'UnrealWindow',
        'interaction': 'Genshin',
        'capture_method': ['WGC', 'BitBlt_RenderFull'],
        'check_hdr': True,
        'force_no_hdr': False,
        'require_bg': True
    },

    #'adb': {
    # Mumu模拟器通常使用原生方式（无需adb server），效率极高
    #    'emulator': 'mumu',           # 明确指定模拟器类型
    #     'adb_path': 'adb',            # 如果 adb 不在 PATH 中，填完整路径，如 r'D:\Program Files\Netease\MuMu\emulator\nemu\vmonitor\bin\adb_server.exe'
    #    'packages': ['com.pwrd.hotta.laohu'],  # 替换为你的游戏包名
    #     'use_native': True,           # 启用 Mumu 原生截图/输入（比 adb 快）
    #    'device_serial': None,        # 如果有多个设备，指定序列号
    #},

    'start_timeout': 120,
    'window_size': {
        'width': 1200,
        'height': 800,
        'min_width': 600,
        'min_height': 450,
    },
    'supported_resolution': {
        'ratio': '16:9',
        'min_size': (1280, 720),
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],
    },
    'links': {
        'default': {
            'github': 'https://github.com/ok-oldking/ok-script-boilerplate',
            'discord': 'https://discord.gg/vVyCatEBgA',
            'sponsor': 'https://www.paypal.com/ncp/payment/JWQBH7JZKNGCQ',
            'share': 'Download from https://github.com/ok-oldking/ok-script-boilerplate',
            'faq': 'https://github.com/ok-oldking/ok-script-boilerplate'
        }
    },
    'screenshots_folder': "screenshots",
    'gui_title': 'ok-hotta',
    'template_matching': {
        'coco_feature_json': os.path.join('assets', 'result.json'),
        'default_horizontal_variance': 0.002,
        'default_vertical_variance': 0.002,
        'default_threshold': 0.8,
    },
    'version': version,
    'my_app': ['src.globals', 'Globals'],
    'onetime_tasks': [
    ["src.tasks.LianHeZuoZhanTask", "LianHeZuoZhanTask"],
    ["src.tasks.TaoFaZuoZhanTask", "TaoFaZuoZhanTask"],
        # ["src.tasks.WorldBoss", "WorldBossTask"],
    ["src.tasks.MultiWorldBoss", "MultiWorldBossTask"],
    ["src.tasks.AutoCombatTask", "AutoCombatTask"],
    ["src.tasks.FishingTask", "FishingTask"],
    ["src.tasks.ZhongFengTuPoTask", "ZhongFengTuPoTask"],
    ["src.tasks.JieXianMaoDianTask", "JieXianMaoDianTask"],
    #["src.tasks.WorldBoss_adb", "WorldBossAdbTask"],
    ["ok", "DiagnosisTask"],
],
    'trigger_tasks': [
        ["src.tasks.AutoKeypressTask", "AutoKeypressTask"],
    ],
    'custom_tabs': [
        # ['src.ui.MyTab', 'MyTab'],
    ],
}