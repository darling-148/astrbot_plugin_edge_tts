import asyncio
import base64
import io
import json
import os
import platform
import random
import re
import shutil
import tempfile
import time
import uuid
from math import inf
from typing import Any
from urllib.request import url2pathname

import edge_tts
import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Image, Plain, Record, Reply
from astrbot.api.star import Context, Star

try:
    from astrbot.api.web import error_response, json_response, request
except ImportError:
    # AstrBot >= 4.14 兼容：astrbot.api.web 已移除，基于 Quart 提供等价能力
    import json as _json

    from quart import Response as _QuartResponse

    def json_response(data, **kwargs):
        return _QuartResponse(
            _json.dumps(data, ensure_ascii=False, default=str),
            mimetype="application/json",
        )

    def error_response(message, **kwargs):
        resp = _QuartResponse(
            _json.dumps({"ok": False, "message": message}, ensure_ascii=False),
            mimetype="application/json",
        )
        resp.status_code = 400
        return resp

    class _WebRequest:
        """兼容旧版 astrbot.api.web.request 的 request.json(default=...) 用法。"""

        @property
        def json(self):
            async def _get_json(default=None):
                from quart import request as _quart_request

                try:
                    data = await _quart_request.get_json(silent=True)
                except Exception:
                    data = None
                if data is None:
                    return default or {}
                return data

            return _get_json

        @property
        def args(self):
            from quart import request as _quart_request

            return _quart_request.args

        @property
        def query(self):
            from quart import request as _quart_request

            return _quart_request.args

        @property
        def form(self):
            from quart import request as _quart_request

            return _quart_request.form

        @property
        def values(self):
            from quart import request as _quart_request

            return _quart_request.values

    request = _WebRequest()

PLUGIN_NAME = "astrbot_plugin_edge_tts"

PERSONAS_KEY = f"{PLUGIN_NAME}:personas"
MEMORY_DIR_NAME = "long_memory"

# 内置人格预设（作为默认人格库，可在控制界面修改/删除/新增）
DEFAULT_PERSONAS = [
    {
        "id": "zhixin",
        "name": "知心姐姐",
        "description": "温柔理性、善解人意的倾听者",
        "prompt": (
            "你是一位知心姐姐，成熟稳重、善解人意，阅历丰富。\n"
            "用温暖而理性的话语倾听对方的烦恼，给出切实可行的建议。\n"
            "语言温柔但条理清晰，适度引导对方思考，不评判不指责。\n"
            "短句与段落结合，语气亲切自然。"
        ),
        "builtin": True,
    },
    {
        "id": "tech_assistant",
        "name": "科技助手",
        "description": "擅长编程与技术解答的智能助手",
        "prompt": (
            "你是一位专业而友好的科技助手，擅长编程、技术问题解答与效率工具推荐。\n"
            "回答准确简洁，能用通俗语言解释复杂技术概念。\n"
            "必要时给出代码或命令示例。语气专业但不生硬。"
        ),
        "builtin": True,
    },
    {
        "id": "counselor",
        "name": "心理咨询师",
        "description": "专业心理疏导与情绪支持",
        "prompt": (
            "你是一位专业心理咨询师，温和、包容、不带评判。\n"
            "善于倾听并共情，帮助用户梳理情绪与困扰，给出建设性的疏导建议。\n"
            "注重信任与安全感，说话舒缓、真诚，避免说教。"
        ),
        "builtin": True,
    },
    {
        "id": "coder",
        "name": "编程专家",
        "description": "精通多语言的资深程序员",
        "prompt": (
            "你是一位资深编程专家，精通 Python、Go、JavaScript、Java 等主流语言。\n"
            "擅长架构设计、Bug 排查、性能优化与代码评审。\n"
            "给出准确可运行的代码示例，并解释关键实现思路。"
        ),
        "builtin": True,
    },
    {
        "id": "writer",
        "name": "写作助手",
        "description": "文案写作、润色与创意输出",
        "prompt": (
            "你是一位专业写作助手，擅长中文文案、公文、创意写作与内容润色。\n"
            "文笔流畅、用词精准，能根据用户需求调整风格与篇幅。\n"
            "结构清晰，重点突出，逻辑连贯。"
        ),
        "builtin": True,
    },
]

# 常见 Emoji 表情及其含义（用于消息表情识别，key 为去掉变体选择符后的基础字符）
EMOJI_MEANINGS = {
    "😀": "咧嘴笑，心情愉悦", "😃": "大笑，欢快开朗", "😄": "喜笑颜开，开心满足", "😁": "得意笑，暗自开心",
    "😆": "偷笑，憋不住暗笑", "😅": "尴尬笑，社死苦笑", "🤣": "爆笑打滚，笑到失控", "😂": "笑哭，笑到流泪",
    "🙂": "温和微笑，礼貌友善", "🙃": "倒脸，阴阳怪气调侃", "😉": "眨眼，俏皮暗示", "😊": "害羞微笑，腼腆温和",
    "😇": "天使脸，乖巧无辜", "🥰": "心动脸红，甜蜜爱慕", "😍": "花痴眼，痴迷心动", "🤩": "星星眼，崇拜惊艳",
    "😘": "飞吻，隔空示爱", "😗": "轻吻，温柔亲昵", "😚": "害羞吻，腼腆示爱", "😙": "抿嘴吻，含蓄温柔",
    "😋": "馋嘴，美食诱人", "😛": "吐舌搞怪，调皮鬼脸", "😜": "斜眼吐舌，戏谑玩笑", "🤪": "疯癫搞怪，放飞自我",
    "😝": "瞪眼吐舌，搞怪耍宝", "🤑": "财迷眼，一心搞钱", "🤗": "拥抱脸，暖心安慰", "🤭": "捂嘴偷笑，偷偷窃喜",
    "🤫": "嘘声，保密噤声", "🤔": "托腮思考，疑惑琢磨", "🤐": "闭嘴憋笑，强忍笑意", "🤨": "挑眉质疑，怀疑审视",
    "😐": "面无表情，平淡冷漠", "😑": "无感脸，麻木淡然", "😶": "放空脸，大脑呆滞", "😏": "坏笑，玩味得意",
    "😒": "不屑撇嘴，嫌弃鄙夷", "🙄": "翻白眼，极度无语", "😬": "窘迫尴尬，手足无措", "🤥": "说谎脸，心虚虚伪",
    "😌": "放松释然，身心舒缓", "😔": "闷闷不乐，内心低落", "😪": "犯困打哈欠，疲惫困倦", "🤤": "馋涎欲滴，极度眼馋",
    "😴": "熟睡，睡得香甜", "😷": "生病戴口罩，身体不适", "🤒": "发烧头痛，头晕发热", "🤕": "受伤包扎，创口疼痛",
    "🤢": "恶心反胃，想吐不适", "🤮": "呕吐，恶心难忍", "🤧": "打喷嚏，感冒受凉", "🥵": "燥热脸红，激动上头",
    "🥶": "寒冷发抖，冻得哆嗦", "🥴": "醉酒迷糊，头昏恍惚", "😵": "眩晕失神，头晕发懵", "😵‍💫": "天旋地转，大脑混乱",
    "🤯": "震惊爆炸头，三观炸裂", "😕": "纠结不安，内心彷徨", "🫤": "心事重重，满心烦恼", "😟": "忧愁焦虑，烦躁不安",
    "🙁": "闷闷忧愁，面露愁容", "☹️": "难过沮丧，满心委屈", "😮": "猛然震惊，大吃一惊", "😯": "错愕发呆，意外愣住",
    "😲": "惊骇，惶恐不安", "😳": "害羞脸红，窘迫难为情", "🥺": "可怜恳求，委屈巴巴", "🥹": "强忍泪水，感动哽咽",
    "😦": "担忧焦虑，惴惴不安", "😧": "惊慌失措，慌乱紧张", "😨": "恐惧害怕，内心恐慌", "😰": "冷汗直流，紧张后怕",
    "😥": "黯然神伤，独自伤感", "😢": "委屈落泪，默默伤心", "😭": "嚎啕大哭，崩溃悲伤", "😱": "惊恐尖叫，极度恐惧",
    "😖": "烦躁憋屈，内心压抑", "😣": "心力交瘁，疲惫不堪", "😞": "失望沮丧，理想落空", "😓": "垂头丧气，懊恼低落",
    "😩": "疲惫倦怠，身心俱疲", "😫": "身心俱疲，不堪重负", "🥱": "昏昏欲睡，眼皮沉重", "😤": "气鼓鼓，愤愤不平",
    "😡": "暴怒，怒火中烧", "😠": "生气不悦，面露愠色", "🤬": "破口大骂，愤怒暴躁", "😈": "小恶魔，调皮腹黑",
    "👿": "恶魔，心怀恶意", "💀": "骷髅头，死亡摆烂", "☠️": "白骨骷髅，危险警示", "❤️": "红心，爱意喜欢",
    "🧡": "橙心，温暖治愈", "💛": "黄心，阳光友谊", "💚": "绿心，健康和平", "💙": "蓝心，沉稳信任",
    "💜": "紫心，浪漫神秘", "🤎": "棕心，踏实安稳", "🖤": "黑心，高冷执念", "🤍": "白心，纯洁纯粹",
    "💔": "心碎，感情破裂", "❤️‍🔥": "炽热红心，热恋上头", "❤️‍🩹": "愈合红心，走出伤心", "💕": "双心，双向爱慕",
    "💞": "旋转爱心，爱意交融", "💓": "心跳，小鹿乱撞", "💗": "浅粉心，温柔好感", "💖": "闪耀红心，极致偏爱",
    "💘": "丘比特之箭，一见钟情", "💝": "礼物爱心，浪漫告白", "❣️": "心动标记，好感满满", "👋": "挥手，打招呼道别",
    "🤚": "抬手停止，拒绝制止", "🖐️": "手掌张开，摊手无奈", "✋": "举手，发言报名", "🖖": "瓦肯举手礼，星际致敬",
    "👌": "OK手势，同意没问题", "🤌": "意大利手势，夸赞完美", "🤏": "捏一点点，数量极少", "✌️": "剪刀手，胜利开心",
    "🤞": "交叉手指，许愿求好运", "🤟": "爱你手势，手语我爱你", "🤘": "摇滚手势，耍酷嗨玩", "🤙": "招呼手势，邀约过来",
    "👈": "向左指，提示方向", "👉": "向右指，提示方向", "👆": "向上指，提醒注意", "🖕": "竖中指，挑衅辱骂",
    "👇": "向下指，提示方向", "☝️": "一指向上，强调注意", "👍": "点赞，认可赞同", "👎": "踩踩，否定差评",
    "✊": "握拳，加油蓄力", "👊": "出拳，打闹鼓劲", "🤛": "左拳，对抗蓄力", "🤜": "右拳，对抗蓄力",
    "👏": "鼓掌，喝彩称赞", "🙌": "高举双手，开心欢呼", "👐": "张开双手，拥抱接纳", "🤲": "双手捧起，祈求珍惜",
    "🤝": "握手，合作交好", "🙏": "双手合十，祈祷感恩", "💅": "美甲，精致摆烂", "👶": "婴儿，稚嫩可爱",
    "👧": "小女孩，少女童真", "👦": "小男孩，少年调皮", "👩": "成年女性，成熟女士", "👨": "成年男性，成熟男士",
    "👵": "老年女性，慈祥老奶奶", "👴": "老年男性，慈祥老爷爷", "🐶": "小狗，乖巧治愈", "🐱": "小猫，软萌傲娇",
    "🐭": "老鼠，机灵胆小", "🐹": "仓鼠，圆滚滚可爱", "🐰": "兔子，温顺软萌", "🦊": "狐狸，精明狡黠",
    "🐻": "大熊，憨厚可靠", "🐼": "熊猫，呆萌国宝", "🐻‍❄️": "北极熊，高冷纯白", "🐨": "考拉，慵懒佛系",
    "🐯": "老虎，威猛霸气", "🦁": "狮子，王者威严", "🐮": "奶牛，勤恳朴实", "🐷": "小猪，憨厚贪吃",
    "🐸": "青蛙，佛系摆烂", "🐵": "猴子，调皮机灵", "🙈": "遮眼猴，逃避现实", "🙉": "遮耳猴，不听八卦",
    "🙊": "遮嘴猴，保密慎言", "🐔": "公鸡，勤奋报晓", "🐧": "企鹅，呆萌可爱", "🐦": "小鸟，自由灵动",
    "🐤": "雏鸟，稚嫩弱小", "🦆": "鸭子，悠闲佛系", "🦅": "老鹰，锐利高远", "🦉": "猫头鹰，智慧神秘",
    "🦇": "蝙蝠，暗夜暗黑", "🐺": "狼，孤傲野性", "🐗": "野猪，勇猛强悍", "🐴": "马，奔放奋进",
    "🦄": "独角兽，梦幻童话", "🐝": "蜜蜂，勤劳甜蜜", "🐛": "毛毛虫，渺小成长", "🦋": "蝴蝶，蜕变自由",
    "🌱": "幼苗，新生希望", "🌿": "青草，清新生机", "☘️": "三叶草，幸运好运", "🍀": "四叶草，极致幸福",
    "🌾": "稻穗，丰收耕耘", "🌳": "大树，稳重庇护", "🌴": "棕榈树，热带休闲", "🌵": "仙人掌，坚强独立",
    "🌷": "郁金香，优雅浪漫", "🌹": "红玫瑰，爱情告白", "🥀": "枯萎玫瑰，感情落幕", "🌻": "向日葵，阳光积极",
    "🌼": "小花，清新温柔", "🌸": "樱花，春日唯美", "💐": "花束，祝福送礼", "🌞": "太阳笑脸，晴朗开心",
    "🌝": "满月笑脸，静谧温柔", "🌛": "弯月，晚安静谧", "🌜": "弯月侧脸，休憩夜晚", "🌚": "黑脸月亮，阴阳调侃",
    "🌙": "月牙，晚安夜色", "⭐": "星星，闪耀希望", "✨": "星光闪烁，高光美好", "💫": "流星，许愿好运",
    "☀️": "太阳，温暖活力", "⛅": "多云，心情平淡", "☁️": "云朵，悠闲慵懒", "🌧️": "下雨，伤感低落",
    "⛈️": "雷阵雨，情绪烦躁", "❄️": "雪花，冬日纯洁", "☃️": "雪人，冬日童趣", "🔥": "火焰，热情火爆",
    "💧": "水滴，落泪细腻", "🌊": "海浪，豁达自由", "🍎": "苹果，平安健康", "🍐": "梨子，润肺清爽",
    "🍊": "橘子，酸甜吉利", "🍋": "柠檬，酸涩清醒", "🍌": "香蕉，软糯快乐", "🍉": "西瓜，夏日清爽",
    "🍇": "葡萄，甜蜜丰盈", "🍓": "草莓，甜美少女", "🫐": "蓝莓，护眼精致", "🍒": "樱桃，可爱诱人",
    "🍑": "桃子，粉嫩好运", "🥭": "芒果，香甜浓郁", "🍍": "菠萝，酸甜个性", "🥥": "椰子，清凉天然",
    "🥝": "猕猴桃，维C健康", "🍅": "番茄，酸甜家常", "🫒": "橄榄，温润平和", "🥑": "牛油果，低脂健康",
    "🍆": "茄子，家常调侃", "🥔": "土豆，朴实饱腹", "🥕": "胡萝卜，护眼营养", "🌽": "玉米，香甜粗粮",
    "🌶️": "辣椒，火辣热情", "🫑": "彩椒，清甜健康", "🥒": "黄瓜，清爽解腻", "🥬": "青菜，清淡素食",
    "🥦": "西兰花，减脂营养", "🧄": "大蒜，调味重口", "🧅": "洋葱，辛辣调味", "🍄": "蘑菇，鲜美自然",
    "🥜": "花生，香脆下酒", "🫘": "豆子，粗粮饱腹", "🌰": "栗子，秋冬暖胃", "🍞": "面包，早餐饱腹",
    "🥐": "牛角包，法式酥脆", "🥖": "法棍，欧式主食", "🫓": "面饼，家常面食", "🥨": "椒盐卷饼，香脆零食",
    "🥯": "贝果，减脂早餐", "🥞": "松饼，甜蜜甜品", "🧇": "华夫饼，西式酥脆", "🧀": "芝士，奶香浓郁",
    "🍖": "烤肉，解馋大餐", "🍗": "鸡腿，快乐肉食", "🥩": "牛排，精致西餐", "🥓": "培根，咸香早餐",
    "🍔": "汉堡，快餐饱腹", "🍟": "薯条，解馋零食", "🍕": "披萨，西式分享", "🌭": "热狗，便捷快餐",
    "🥪": "三明治，轻食早餐", "🌮": "塔可，墨西哥香辣", "🌯": "卷饼，饱腹便捷", "🫔": "春卷，中式酥脆",
    "🥙": "夹饼，家常饱腹", "🧆": "炸物，酥脆解馋", "🥚": "鸡蛋，基础营养", "🍳": "煎蛋，简单早餐",
    "🥘": "大锅菜，聚餐热闹", "🍲": "火锅，暖身聚餐", "🫕": "汤羹，清淡滋补", "🥗": "沙拉，减脂健康",
    "🍝": "意面，西式饱腹", "🍜": "面条，中式家常", "🍠": "红薯，粗粮暖胃", "🍢": "关东煮，日式暖身",
    "🍣": "寿司，日式精致", "🍤": "天妇罗，日式酥脆", "🍥": "鱼饼，火锅食材", "🥮": "月饼，中秋团圆",
    "🍡": "丸子串，日式小吃", "🥠": "幸运饼干，西式祝福", "🥟": "饺子，中式团圆", "🍦": "冰淇淋，夏日甜蜜",
    "🍧": "刨冰，夏日清凉", "🍨": "冰淇淋球，西式甜品", "🍩": "甜甜圈，快乐甜品", "🍪": "饼干，休闲零食",
    "🎂": "生日蛋糕，庆祝甜蜜", "🍰": "切块蛋糕，精致下午茶", "🧁": "纸杯蛋糕，小巧可爱", "🍫": "巧克力，浓郁治愈",
    "🍬": "糖果，甜蜜童趣", "🍭": "棒棒糖，可爱童趣", "🍮": "布丁，嫩滑西式", "🍯": "蜂蜜，天然滋养",
    "🍼": "奶瓶，稚嫩奶香", "🥛": "牛奶，营养健康", "☕": "咖啡，提神休闲", "🍵": "茶水，养生闲适",
    "🍶": "清酒，日式微醺", "🍾": "香槟，庆祝仪式", "🍷": "红酒，浪漫微醺", "🍸": "鸡尾酒，派对调酒",
    "🍹": "果汁，清爽香甜", "🍺": "啤酒，畅饮放松", "🍻": "碰杯，干杯欢聚", "🥂": "举杯，庆祝祝福",
    "🫗": "倒酒，斟酒小酌", "🥤": "汽水，快乐解渴", "🧃": "盒装果汁，便捷清甜", "🏠": "房子，安稳归宿",
    "🏡": "庭院小屋，田园安逸", "🏘️": "居民区，社区烟火", "🏚️": "破旧小屋，落魄怀旧", "🏗️": "施工建筑，动工建造",
    "🏭": "工厂，工业生产", "🏢": "写字楼，职场办公", "🏬": "商场大楼，商业繁华", "🏣": "邮局，物流通讯",
    "🏤": "驿站，中转休憩", "🏥": "医院，医疗救助", "🏦": "银行，金融储蓄", "🏨": "酒店，出行住宿",
    "🏩": "情侣酒店，浪漫私密", "🏪": "便利店，24小时便捷", "🏫": "学校，青春校园", "🏛️": "古典建筑，历史庄重",
    "⛪": "教堂，神圣婚礼", "🕌": "清真寺，异域信仰", "🕍": "犹太教堂，异域宗教", "🛕": "印度寺庙，异域信仰",
    "⛩️": "日式鸟居，和风神社", "🗿": "石像摩艾，佛系摆烂", "🚦": "红绿灯，交通规则", "🚧": "施工路障，绕行警示",
    "🗺️": "世界地图，旅行探索", "🗾": "日本地图，日系旅行", "🌋": "火山，热情危险", "🏔️": "雪山，清冷壮阔",
    "⛰️": "山丘，平缓户外", "🗻": "富士山，日式地标", "🌅": "日出，清晨希望", "🌄": "山间日落，黄昏唯美",
    "🌠": "星空，浩瀚静谧", "🌇": "城市日落，都市黄昏", "🌆": "城市黄昏，都市繁华", "🌃": "城市夜景，都市繁华",
    "🌉": "城市大桥，交通夜景", "🌁": "山间雾气，朦胧仙境", "🎠": "旋转木马，童趣快乐", "🎡": "摩天轮，浪漫约会",
    "🎢": "过山车，刺激解压", "🚂": "蒸汽火车，复古远行", "🚃": "老式车厢，怀旧旅行", "🚄": "高铁，快捷出行",
    "🚅": "高速列车，极速远行", "🚆": "火车，旅途交通", "🚇": "地铁，都市通勤", "🚈": "轻轨，短途通勤",
    "🚉": "站台，候车停靠", "🚊": "地铁列车，都市出行", "🚝": "单轨列车，特色交通", "🚞": "观光火车，慢旅行",
    "🚋": "有轨电车，复古通勤", "🚌": "大巴车，集体出行", "🚍": "城际巴士，跨城交通", "🚎": "观光大巴，旅游出行",
    "🚐": "面包车，家用载人", "🚑": "救护车，紧急急救", "🚒": "消防车，应急救援", "🚓": "警车，执法安全",
    "🚔": "警用车辆，安保执法", "🚕": "出租车，打车出行", "🚖": "网约车，便捷代步", "🚗": "家用轿车，日常出行",
    "🚘": "敞篷车，潇洒拉风", "🚙": "SUV越野车，户外霸气", "🚚": "货车，运输载货",
}

# 表情包图片识别的文件名/URL 特征关键词
EMOJI_FILE_KEYWORDS = [
    "emoji", "sticker", "face", "qq_emoji", "emoji_", "qqface",
    "meme", "biaoqing", "表情", "梗图", "贴纸",
]

# 卡通/可爱风格图片特征关键词
CARTOON_STYLE_KEYWORDS = ["cartoon", "cute", "anime", "chibi", "mascot", "卡通", "可爱", "动漫", "二次元"]

# Edge TTS 中文音色（value 为 Edge TTS 音色标识，label 为细化的中文描述）
TTS_VOICES = [
    {"value": "af-ZA-AdriNeural", "label": "阿德里 · 南非荷兰语(南非) 女声", "group": "国外"},
    {"value": "af-ZA-WillemNeural", "label": "威廉 · 南非荷兰语(南非) 男声", "group": "国外"},
    {"value": "sq-AL-AnilaNeural", "label": "阿妮拉 · 阿尔巴尼亚语(阿尔巴尼亚) 女声", "group": "国外"},
    {"value": "sq-AL-IlirNeural", "label": "伊利尔 · 阿尔巴尼亚语(阿尔巴尼亚) 男声", "group": "国外"},
    {"value": "am-ET-AmehaNeural", "label": "阿梅哈 · 阿姆哈拉语(埃塞俄比亚) 男声", "group": "国外"},
    {"value": "am-ET-MekdesNeural", "label": "梅克德斯 · 阿姆哈拉语(埃塞俄比亚) 女声", "group": "国外"},
    {"value": "ar-DZ-AminaNeural", "label": "阿米娜 · 阿拉伯语(阿尔及利亚) 女声", "group": "国外"},
    {"value": "ar-DZ-IsmaelNeural", "label": "伊斯梅尔 · 阿拉伯语(阿尔及利亚) 男声", "group": "国外"},
    {"value": "ar-BH-AliNeural", "label": "阿里 · 阿拉伯语(巴林) 男声", "group": "国外"},
    {"value": "ar-BH-LailaNeural", "label": "莱拉 · 阿拉伯语(巴林) 女声", "group": "国外"},
    {"value": "ar-EG-SalmaNeural", "label": "萨尔玛 · 阿拉伯语(埃及) 女声", "group": "国外"},
    {"value": "ar-EG-ShakirNeural", "label": "沙基尔 · 阿拉伯语(埃及) 男声", "group": "国外"},
    {"value": "ar-IQ-BasselNeural", "label": "巴塞尔 · 阿拉伯语(伊拉克) 男声", "group": "国外"},
    {"value": "ar-IQ-RanaNeural", "label": "拉娜 · 阿拉伯语(伊拉克) 女声", "group": "国外"},
    {"value": "ar-JO-SanaNeural", "label": "萨娜 · 阿拉伯语(约旦) 女声", "group": "国外"},
    {"value": "ar-JO-TaimNeural", "label": "塔伊姆 · 阿拉伯语(约旦) 男声", "group": "国外"},
    {"value": "ar-KW-FahedNeural", "label": "法赫德 · 阿拉伯语(科威特) 男声", "group": "国外"},
    {"value": "ar-KW-NouraNeural", "label": "努拉 · 阿拉伯语(科威特) 女声", "group": "国外"},
    {"value": "ar-LB-LaylaNeural", "label": "蕾拉 · 阿拉伯语(黎巴嫩) 女声", "group": "国外"},
    {"value": "ar-LB-RamiNeural", "label": "拉米 · 阿拉伯语(黎巴嫩) 男声", "group": "国外"},
    {"value": "ar-LY-ImanNeural", "label": "伊曼 · 阿拉伯语(利比亚) 女声", "group": "国外"},
    {"value": "ar-LY-OmarNeural", "label": "奥马尔 · 阿拉伯语(利比亚) 男声", "group": "国外"},
    {"value": "ar-MA-JamalNeural", "label": "贾马尔 · 阿拉伯语(摩洛哥) 男声", "group": "国外"},
    {"value": "ar-MA-MounaNeural", "label": "穆娜 · 阿拉伯语(摩洛哥) 女声", "group": "国外"},
    {"value": "ar-OM-AbdullahNeural", "label": "阿卜杜拉 · 阿拉伯语(阿曼) 男声", "group": "国外"},
    {"value": "ar-OM-AyshaNeural", "label": "艾莎 · 阿拉伯语(阿曼) 女声", "group": "国外"},
    {"value": "ar-QA-AmalNeural", "label": "阿马尔 · 阿拉伯语(卡塔尔) 女声", "group": "国外"},
    {"value": "ar-QA-MoazNeural", "label": "莫阿兹 · 阿拉伯语(卡塔尔) 男声", "group": "国外"},
    {"value": "ar-SA-HamedNeural", "label": "哈米德 · 阿拉伯语(沙特阿拉伯) 男声", "group": "国外"},
    {"value": "ar-SA-ZariyahNeural", "label": "扎里娅 · 阿拉伯语(沙特阿拉伯) 女声", "group": "国外"},
    {"value": "ar-SY-AmanyNeural", "label": "阿曼妮 · 阿拉伯语(叙利亚) 女声", "group": "国外"},
    {"value": "ar-SY-LaithNeural", "label": "莱斯 · 阿拉伯语(叙利亚) 男声", "group": "国外"},
    {"value": "ar-TN-HediNeural", "label": "赫迪 · 阿拉伯语(突尼斯) 男声", "group": "国外"},
    {"value": "ar-TN-ReemNeural", "label": "蕾姆 · 阿拉伯语(突尼斯) 女声", "group": "国外"},
    {"value": "ar-AE-FatimaNeural", "label": "法蒂玛 · 阿拉伯语(阿联酋) 女声", "group": "国外"},
    {"value": "ar-AE-HamdanNeural", "label": "哈姆丹 · 阿拉伯语(阿联酋) 男声", "group": "国外"},
    {"value": "ar-YE-MaryamNeural", "label": "玛丽亚姆 · 阿拉伯语(也门) 女声", "group": "国外"},
    {"value": "ar-YE-SalehNeural", "label": "萨利赫 · 阿拉伯语(也门) 男声", "group": "国外"},
    {"value": "az-AZ-BabekNeural", "label": "巴贝克 · 阿塞拜疆语(阿塞拜疆) 男声", "group": "国外"},
    {"value": "az-AZ-BanuNeural", "label": "巴努 · 阿塞拜疆语(阿塞拜疆) 女声", "group": "国外"},
    {"value": "bn-BD-NabanitaNeural", "label": "纳巴尼塔 · 孟加拉语(孟加拉国) 女声", "group": "国外"},
    {"value": "bn-BD-PradeepNeural", "label": "普拉迪普 · 孟加拉语(孟加拉国) 男声", "group": "国外"},
    {"value": "bn-IN-BashkarNeural", "label": "巴什卡尔 · 孟加拉语(印度) 男声", "group": "国外"},
    {"value": "bn-IN-TanishaaNeural", "label": "塔妮莎 · 孟加拉语(印度) 女声", "group": "国外"},
    {"value": "bs-BA-VesnaNeural", "label": "韦斯娜 · 波斯尼亚语(波黑) 女声", "group": "国外"},
    {"value": "bs-BA-GoranNeural", "label": "戈兰 · 波斯尼亚语(波黑) 男声", "group": "国外"},
    {"value": "bg-BG-BorislavNeural", "label": "博里斯拉夫 · 保加利亚语(保加利亚) 男声", "group": "国外"},
    {"value": "bg-BG-KalinaNeural", "label": "卡琳娜 · 保加利亚语(保加利亚) 女声", "group": "国外"},
    {"value": "my-MM-NilarNeural", "label": "尼拉尔 · 缅甸语(缅甸) 女声", "group": "国外"},
    {"value": "my-MM-ThihaNeural", "label": "提哈 · 缅甸语(缅甸) 男声", "group": "国外"},
    {"value": "ca-ES-EnricNeural", "label": "恩里克 · 加泰罗尼亚语(西班牙) 男声", "group": "国外"},
    {"value": "ca-ES-JoanaNeural", "label": "若阿娜 · 加泰罗尼亚语(西班牙) 女声", "group": "国外"},
    {"value": "zh-HK-HiuGaaiNeural", "label": "曉佳 · 粤语女声，清亮利落", "group": "中国"},
    {"value": "zh-HK-HiuMaanNeural", "label": "曉曼 · 粤语女声，温柔知性", "group": "中国"},
    {"value": "zh-HK-WanLungNeural", "label": "雲龍 · 粤语男声，沉稳大气", "group": "中国"},
    {"value": "zh-CN-XiaoxiaoNeural", "label": "晓晓 · 温柔甜美的女声，亲和治愈，适合贴心陪护", "group": "中国"},
    {"value": "zh-CN-XiaoyiNeural", "label": "晓伊 · 清甜活泼的女声，元气满满，适合日常聊天", "group": "中国"},
    {"value": "zh-CN-YunjianNeural", "label": "云健 · 成熟稳重的男声，值得信赖的知性大叔感", "group": "中国"},
    {"value": "zh-CN-YunxiNeural", "label": "云希 · 阳光清爽的少年男声，温暖而充满朝气", "group": "中国"},
    {"value": "zh-CN-YunxiaNeural", "label": "云夏 · 稚嫩可爱的男童声，天真灵动", "group": "中国"},
    {"value": "zh-CN-YunyangNeural", "label": "云扬 · 专业权威的男声，沉稳大方，适合讲解播报", "group": "中国"},
    {"value": "zh-CN-liaoning-XiaobeiNeural", "label": "晓北 · 辽宁方言女声，地道东北味", "group": "中国"},
    {"value": "zh-TW-HsiaoChenNeural", "label": "曉臻 · 台湾国语女声，清澈甜美", "group": "中国"},
    {"value": "zh-TW-YunJheNeural", "label": "雲哲 · 台湾国语男声，温和清爽", "group": "中国"},
    {"value": "zh-TW-HsiaoYuNeural", "label": "曉雨 · 台湾国语女声，俏皮灵动", "group": "中国"},
    {"value": "zh-CN-shaanxi-XiaoniNeural", "label": "晓妮 · 陕西方言女声，亲切朴实", "group": "中国"},
    {"value": "hr-HR-GabrijelaNeural", "label": "加布里耶拉 · 克罗地亚语(克罗地亚) 女声", "group": "国外"},
    {"value": "hr-HR-SreckoNeural", "label": "斯雷奇科 · 克罗地亚语(克罗地亚) 男声", "group": "国外"},
    {"value": "cs-CZ-AntoninNeural", "label": "安东宁 · 捷克语(捷克) 男声", "group": "国外"},
    {"value": "cs-CZ-VlastaNeural", "label": "弗拉斯塔 · 捷克语(捷克) 女声", "group": "国外"},
    {"value": "da-DK-ChristelNeural", "label": "克里斯特尔 · 丹麦语(丹麦) 女声", "group": "国外"},
    {"value": "da-DK-JeppeNeural", "label": "耶珀 · 丹麦语(丹麦) 男声", "group": "国外"},
    {"value": "nl-BE-ArnaudNeural", "label": "阿尔诺 · 荷兰语(比利时) 男声", "group": "国外"},
    {"value": "nl-BE-DenaNeural", "label": "德娜 · 荷兰语(比利时) 女声", "group": "国外"},
    {"value": "nl-NL-ColetteNeural", "label": "科莱特 · 荷兰语(荷兰) 女声", "group": "国外"},
    {"value": "nl-NL-FennaNeural", "label": "芬娜 · 荷兰语(荷兰) 女声", "group": "国外"},
    {"value": "nl-NL-MaartenNeural", "label": "马尔滕 · 荷兰语(荷兰) 男声", "group": "国外"},
    {"value": "en-AU-WilliamMultilingualNeural", "label": "威廉 · 英语(澳大利亚) 男声", "group": "国外"},
    {"value": "en-AU-NatashaNeural", "label": "娜塔莎 · 英语(澳大利亚) 女声", "group": "国外"},
    {"value": "en-CA-ClaraNeural", "label": "克拉拉 · 英语(加拿大) 女声", "group": "国外"},
    {"value": "en-CA-LiamNeural", "label": "利亚姆 · 英语(加拿大) 男声", "group": "国外"},
    {"value": "en-HK-YanNeural", "label": "燕 · 英语(香港) 女声", "group": "国外"},
    {"value": "en-HK-SamNeural", "label": "山姆 · 英语(香港) 男声", "group": "国外"},
    {"value": "en-IN-NeerjaExpressiveNeural", "label": "尼拉 · 英语(印度) 女声", "group": "国外"},
    {"value": "en-IN-NeerjaNeural", "label": "尼拉 · 英语(印度) 女声", "group": "国外"},
    {"value": "en-IN-PrabhatNeural", "label": "普拉巴特 · 英语(印度) 男声", "group": "国外"},
    {"value": "en-IE-ConnorNeural", "label": "康纳 · 英语(爱尔兰) 男声", "group": "国外"},
    {"value": "en-IE-EmilyNeural", "label": "艾米丽 · 英语(爱尔兰) 女声", "group": "国外"},
    {"value": "en-KE-AsiliaNeural", "label": "阿西莉亚 · 英语(肯尼亚) 女声", "group": "国外"},
    {"value": "en-KE-ChilembaNeural", "label": "奇伦巴 · 英语(肯尼亚) 男声", "group": "国外"},
    {"value": "en-NZ-MitchellNeural", "label": "米切尔 · 英语(新西兰) 男声", "group": "国外"},
    {"value": "en-NZ-MollyNeural", "label": "莫莉 · 英语(新西兰) 女声", "group": "国外"},
    {"value": "en-NG-AbeoNeural", "label": "阿贝奥 · 英语(尼日利亚) 男声", "group": "国外"},
    {"value": "en-NG-EzinneNeural", "label": "艾辛内 · 英语(尼日利亚) 女声", "group": "国外"},
    {"value": "en-PH-JamesNeural", "label": "詹姆斯 · 英语(菲律宾) 男声", "group": "国外"},
    {"value": "en-PH-RosaNeural", "label": "罗莎 · 英语(菲律宾) 女声", "group": "国外"},
    {"value": "en-US-AvaNeural", "label": "艾娃 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-AndrewNeural", "label": "安德鲁 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-EmmaNeural", "label": "艾玛 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-BrianNeural", "label": "布莱恩 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-SG-LunaNeural", "label": "露娜 · 英语(新加坡) 女声", "group": "国外"},
    {"value": "en-SG-WayneNeural", "label": "韦恩 · 英语(新加坡) 男声", "group": "国外"},
    {"value": "en-ZA-LeahNeural", "label": "莉亚 · 英语(南非) 女声", "group": "国外"},
    {"value": "en-ZA-LukeNeural", "label": "卢克 · 英语(南非) 男声", "group": "国外"},
    {"value": "en-TZ-ElimuNeural", "label": "埃利穆 · 英语(坦桑尼亚) 男声", "group": "国外"},
    {"value": "en-TZ-ImaniNeural", "label": "伊玛尼 · 英语(坦桑尼亚) 女声", "group": "国外"},
    {"value": "en-GB-LibbyNeural", "label": "莉比 · 英语(英国) 女声", "group": "国外"},
    {"value": "en-GB-MaisieNeural", "label": "梅西 · 英语(英国) 女声", "group": "国外"},
    {"value": "en-GB-RyanNeural", "label": "瑞恩 · 英语(英国) 男声", "group": "国外"},
    {"value": "en-GB-SoniaNeural", "label": "索尼娅 · 英语(英国) 女声", "group": "国外"},
    {"value": "en-GB-ThomasNeural", "label": "托马斯 · 英语(英国) 男声", "group": "国外"},
    {"value": "en-US-AnaNeural", "label": "安娜 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-AndrewMultilingualNeural", "label": "安德鲁 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-AriaNeural", "label": "艾瑞亚 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-AvaMultilingualNeural", "label": "艾娃 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-BrianMultilingualNeural", "label": "布莱恩 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-ChristopherNeural", "label": "克里斯托弗 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-EmmaMultilingualNeural", "label": "艾玛 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-EricNeural", "label": "埃里克 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-GuyNeural", "label": "盖伊 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-JennyNeural", "label": "珍妮 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-MichelleNeural", "label": "米歇尔 · 英语(美国) 女声", "group": "国外"},
    {"value": "en-US-RogerNeural", "label": "罗杰 · 英语(美国) 男声", "group": "国外"},
    {"value": "en-US-SteffanNeural", "label": "斯蒂芬 · 英语(美国) 男声", "group": "国外"},
    {"value": "et-EE-AnuNeural", "label": "阿努 · 爱沙尼亚语(爱沙尼亚) 女声", "group": "国外"},
    {"value": "et-EE-KertNeural", "label": "凯尔特 · 爱沙尼亚语(爱沙尼亚) 男声", "group": "国外"},
    {"value": "fil-PH-AngeloNeural", "label": "安杰洛 · 菲律宾语(菲律宾) 男声", "group": "国外"},
    {"value": "fil-PH-BlessicaNeural", "label": "布莱西卡 · 菲律宾语(菲律宾) 女声", "group": "国外"},
    {"value": "fi-FI-HarriNeural", "label": "哈里 · 芬兰语(芬兰) 男声", "group": "国外"},
    {"value": "fi-FI-NooraNeural", "label": "诺拉 · 芬兰语(芬兰) 女声", "group": "国外"},
    {"value": "fr-BE-CharlineNeural", "label": "夏琳 · 法语(比利时) 女声", "group": "国外"},
    {"value": "fr-BE-GerardNeural", "label": "杰拉德 · 法语(比利时) 男声", "group": "国外"},
    {"value": "fr-CA-ThierryNeural", "label": "蒂埃里 · 法语(加拿大) 男声", "group": "国外"},
    {"value": "fr-CA-AntoineNeural", "label": "安托万 · 法语(加拿大) 男声", "group": "国外"},
    {"value": "fr-CA-JeanNeural", "label": "让 · 法语(加拿大) 男声", "group": "国外"},
    {"value": "fr-CA-SylvieNeural", "label": "西尔维 · 法语(加拿大) 女声", "group": "国外"},
    {"value": "fr-FR-VivienneMultilingualNeural", "label": "维维恩 · 法语(法国) 女声", "group": "国外"},
    {"value": "fr-FR-RemyMultilingualNeural", "label": "雷米 · 法语(法国) 男声", "group": "国外"},
    {"value": "fr-FR-DeniseNeural", "label": "丹妮丝 · 法语(法国) 女声", "group": "国外"},
    {"value": "fr-FR-EloiseNeural", "label": "埃洛伊丝 · 法语(法国) 女声", "group": "国外"},
    {"value": "fr-FR-HenriNeural", "label": "亨利 · 法语(法国) 男声", "group": "国外"},
    {"value": "fr-CH-ArianeNeural", "label": "阿丽亚娜 · 法语(瑞士) 女声", "group": "国外"},
    {"value": "fr-CH-FabriceNeural", "label": "法布里斯 · 法语(瑞士) 男声", "group": "国外"},
    {"value": "gl-ES-RoiNeural", "label": "罗伊 · 加利西亚语(西班牙) 男声", "group": "国外"},
    {"value": "gl-ES-SabelaNeural", "label": "萨贝拉 · 加利西亚语(西班牙) 女声", "group": "国外"},
    {"value": "ka-GE-EkaNeural", "label": "埃卡 · 格鲁吉亚语(格鲁吉亚) 女声", "group": "国外"},
    {"value": "ka-GE-GiorgiNeural", "label": "乔吉 · 格鲁吉亚语(格鲁吉亚) 男声", "group": "国外"},
    {"value": "de-AT-IngridNeural", "label": "英格丽德 · 德语(奥地利) 女声", "group": "国外"},
    {"value": "de-AT-JonasNeural", "label": "约纳斯 · 德语(奥地利) 男声", "group": "国外"},
    {"value": "de-DE-SeraphinaMultilingualNeural", "label": "塞拉菲娜 · 德语(德国) 女声", "group": "国外"},
    {"value": "de-DE-FlorianMultilingualNeural", "label": "弗洛里安 · 德语(德国) 男声", "group": "国外"},
    {"value": "de-DE-AmalaNeural", "label": "阿玛拉 · 德语(德国) 女声", "group": "国外"},
    {"value": "de-DE-ConradNeural", "label": "康拉德 · 德语(德国) 男声", "group": "国外"},
    {"value": "de-DE-KatjaNeural", "label": "卡蒂娅 · 德语(德国) 女声", "group": "国外"},
    {"value": "de-DE-KillianNeural", "label": "基利安 · 德语(德国) 男声", "group": "国外"},
    {"value": "de-CH-JanNeural", "label": "扬 · 德语(瑞士) 男声", "group": "国外"},
    {"value": "de-CH-LeniNeural", "label": "莱妮 · 德语(瑞士) 女声", "group": "国外"},
    {"value": "el-GR-AthinaNeural", "label": "雅典娜 · 希腊语(希腊) 女声", "group": "国外"},
    {"value": "el-GR-NestorasNeural", "label": "内斯托拉斯 · 希腊语(希腊) 男声", "group": "国外"},
    {"value": "gu-IN-DhwaniNeural", "label": "德瓦尼 · 古吉拉特语(印度) 女声", "group": "国外"},
    {"value": "gu-IN-NiranjanNeural", "label": "尼兰詹 · 古吉拉特语(印度) 男声", "group": "国外"},
    {"value": "he-IL-AvriNeural", "label": "阿夫里 · 希伯来语(以色列) 男声", "group": "国外"},
    {"value": "he-IL-HilaNeural", "label": "希拉 · 希伯来语(以色列) 女声", "group": "国外"},
    {"value": "hi-IN-MadhurNeural", "label": "马杜尔 · 印地语(印度) 男声", "group": "国外"},
    {"value": "hi-IN-SwaraNeural", "label": "斯瓦拉 · 印地语(印度) 女声", "group": "国外"},
    {"value": "hu-HU-NoemiNeural", "label": "诺埃米 · 匈牙利语(匈牙利) 女声", "group": "国外"},
    {"value": "hu-HU-TamasNeural", "label": "塔马斯 · 匈牙利语(匈牙利) 男声", "group": "国外"},
    {"value": "is-IS-GudrunNeural", "label": "古德伦 · 冰岛语(冰岛) 女声", "group": "国外"},
    {"value": "is-IS-GunnarNeural", "label": "贡纳尔 · 冰岛语(冰岛) 男声", "group": "国外"},
    {"value": "id-ID-ArdiNeural", "label": "阿尔迪 · 印尼语(印度尼西亚) 男声", "group": "国外"},
    {"value": "id-ID-GadisNeural", "label": "加迪斯 · 印尼语(印度尼西亚) 女声", "group": "国外"},
    {"value": "iu-Latn-CA-SiqiniqNeural", "label": "西奇尼克 · 因纽特语(加拿大) 女声", "group": "国外"},
    {"value": "iu-Latn-CA-TaqqiqNeural", "label": "塔奇克 · 因纽特语(加拿大) 男声", "group": "国外"},
    {"value": "iu-Cans-CA-SiqiniqNeural", "label": "西奇尼克 · 因纽特语(加拿大) 女声", "group": "国外"},
    {"value": "iu-Cans-CA-TaqqiqNeural", "label": "塔奇克 · 因纽特语(加拿大) 男声", "group": "国外"},
    {"value": "ga-IE-ColmNeural", "label": "科尔姆 · 爱尔兰语(爱尔兰) 男声", "group": "国外"},
    {"value": "ga-IE-OrlaNeural", "label": "奥拉 · 爱尔兰语(爱尔兰) 女声", "group": "国外"},
    {"value": "it-IT-GiuseppeMultilingualNeural", "label": "朱塞佩 · 意大利语(意大利) 男声", "group": "国外"},
    {"value": "it-IT-DiegoNeural", "label": "迭戈 · 意大利语(意大利) 男声", "group": "国外"},
    {"value": "it-IT-ElsaNeural", "label": "艾尔莎 · 意大利语(意大利) 女声", "group": "国外"},
    {"value": "it-IT-IsabellaNeural", "label": "伊莎贝拉 · 意大利语(意大利) 女声", "group": "国外"},
    {"value": "ja-JP-KeitaNeural", "label": "凯塔 · 日语(日本) 男声", "group": "国外"},
    {"value": "ja-JP-NanamiNeural", "label": "奈奈美 · 日语(日本) 女声", "group": "国外"},
    {"value": "jv-ID-DimasNeural", "label": "迪马斯 · 爪哇语(印度尼西亚) 男声", "group": "国外"},
    {"value": "jv-ID-SitiNeural", "label": "西蒂 · 爪哇语(印度尼西亚) 女声", "group": "国外"},
    {"value": "kn-IN-GaganNeural", "label": "加根 · 卡纳达语(印度) 男声", "group": "国外"},
    {"value": "kn-IN-SapnaNeural", "label": "萨普娜 · 卡纳达语(印度) 女声", "group": "国外"},
    {"value": "kk-KZ-AigulNeural", "label": "爱古尔 · 哈萨克语(哈萨克斯坦) 女声", "group": "国外"},
    {"value": "kk-KZ-DauletNeural", "label": "道莱特 · 哈萨克语(哈萨克斯坦) 男声", "group": "国外"},
    {"value": "km-KH-PisethNeural", "label": "皮塞特 · 高棉语(柬埔寨) 男声", "group": "国外"},
    {"value": "km-KH-SreymomNeural", "label": "斯雷莫姆 · 高棉语(柬埔寨) 女声", "group": "国外"},
    {"value": "ko-KR-HyunsuMultilingualNeural", "label": "贤洙 · 韩语(韩国) 男声", "group": "国外"},
    {"value": "ko-KR-InJoonNeural", "label": "仁俊 · 韩语(韩国) 男声", "group": "国外"},
    {"value": "ko-KR-SunHiNeural", "label": "善熙 · 韩语(韩国) 女声", "group": "国外"},
    {"value": "lo-LA-ChanthavongNeural", "label": "占塔冯 · 老挝语(老挝) 男声", "group": "国外"},
    {"value": "lo-LA-KeomanyNeural", "label": "乔玛妮 · 老挝语(老挝) 女声", "group": "国外"},
    {"value": "lv-LV-EveritaNeural", "label": "埃维丽塔 · 拉脱维亚语(拉脱维亚) 女声", "group": "国外"},
    {"value": "lv-LV-NilsNeural", "label": "尼尔斯 · 拉脱维亚语(拉脱维亚) 男声", "group": "国外"},
    {"value": "lt-LT-LeonasNeural", "label": "莱昂纳斯 · 立陶宛语(立陶宛) 男声", "group": "国外"},
    {"value": "lt-LT-OnaNeural", "label": "奥娜 · 立陶宛语(立陶宛) 女声", "group": "国外"},
    {"value": "mk-MK-AleksandarNeural", "label": "亚历山大 · 马其顿语(北马其顿) 男声", "group": "国外"},
    {"value": "mk-MK-MarijaNeural", "label": "玛丽娅 · 马其顿语(北马其顿) 女声", "group": "国外"},
    {"value": "ms-MY-OsmanNeural", "label": "奥斯曼 · 马来语(马来西亚) 男声", "group": "国外"},
    {"value": "ms-MY-YasminNeural", "label": "亚斯明 · 马来语(马来西亚) 女声", "group": "国外"},
    {"value": "ml-IN-MidhunNeural", "label": "米杜恩 · 马拉雅拉姆语(印度) 男声", "group": "国外"},
    {"value": "ml-IN-SobhanaNeural", "label": "索巴娜 · 马拉雅拉姆语(印度) 女声", "group": "国外"},
    {"value": "mt-MT-GraceNeural", "label": "格蕾丝 · 马耳他语(马耳他) 女声", "group": "国外"},
    {"value": "mt-MT-JosephNeural", "label": "约瑟夫 · 马耳他语(马耳他) 男声", "group": "国外"},
    {"value": "mr-IN-AarohiNeural", "label": "阿罗希 · 马拉地语(印度) 女声", "group": "国外"},
    {"value": "mr-IN-ManoharNeural", "label": "马诺哈尔 · 马拉地语(印度) 男声", "group": "国外"},
    {"value": "mn-MN-BataaNeural", "label": "巴塔 · 蒙古语(蒙古) 男声", "group": "国外"},
    {"value": "mn-MN-YesuiNeural", "label": "耶苏伊 · 蒙古语(蒙古) 女声", "group": "国外"},
    {"value": "ne-NP-HemkalaNeural", "label": "赫姆卡拉 · 尼泊尔语(尼泊尔) 女声", "group": "国外"},
    {"value": "ne-NP-SagarNeural", "label": "萨加尔 · 尼泊尔语(尼泊尔) 男声", "group": "国外"},
    {"value": "nb-NO-FinnNeural", "label": "芬恩 · 挪威语(挪威) 男声", "group": "国外"},
    {"value": "nb-NO-PernilleNeural", "label": "佩妮莱 · 挪威语(挪威) 女声", "group": "国外"},
    {"value": "ps-AF-GulNawazNeural", "label": "古尔纳瓦兹 · 普什图语(阿富汗) 男声", "group": "国外"},
    {"value": "ps-AF-LatifaNeural", "label": "拉蒂法 · 普什图语(阿富汗) 女声", "group": "国外"},
    {"value": "fa-IR-DilaraNeural", "label": "迪拉娜 · 波斯语(伊朗) 女声", "group": "国外"},
    {"value": "fa-IR-FaridNeural", "label": "法里德 · 波斯语(伊朗) 男声", "group": "国外"},
    {"value": "pl-PL-MarekNeural", "label": "马雷克 · 波兰语(波兰) 男声", "group": "国外"},
    {"value": "pl-PL-ZofiaNeural", "label": "佐菲娅 · 波兰语(波兰) 女声", "group": "国外"},
    {"value": "pt-BR-ThalitaMultilingualNeural", "label": "塔莉塔 · 葡萄牙语(巴西) 女声", "group": "国外"},
    {"value": "pt-BR-AntonioNeural", "label": "安东尼奥 · 葡萄牙语(巴西) 男声", "group": "国外"},
    {"value": "pt-BR-FranciscaNeural", "label": "弗朗西斯卡 · 葡萄牙语(巴西) 女声", "group": "国外"},
    {"value": "pt-PT-DuarteNeural", "label": "杜阿尔特 · 葡萄牙语(葡萄牙) 男声", "group": "国外"},
    {"value": "pt-PT-RaquelNeural", "label": "拉克尔 · 葡萄牙语(葡萄牙) 女声", "group": "国外"},
    {"value": "ro-RO-AlinaNeural", "label": "阿丽娜 · 罗马尼亚语(罗马尼亚) 女声", "group": "国外"},
    {"value": "ro-RO-EmilNeural", "label": "埃米尔 · 罗马尼亚语(罗马尼亚) 男声", "group": "国外"},
    {"value": "ru-RU-DmitryNeural", "label": "德米特里 · 俄语(俄罗斯) 男声", "group": "国外"},
    {"value": "ru-RU-SvetlanaNeural", "label": "斯维特兰娜 · 俄语(俄罗斯) 女声", "group": "国外"},
    {"value": "sr-RS-NicholasNeural", "label": "尼古拉斯 · 塞尔维亚语(塞尔维亚) 男声", "group": "国外"},
    {"value": "sr-RS-SophieNeural", "label": "索菲 · 塞尔维亚语(塞尔维亚) 女声", "group": "国外"},
    {"value": "si-LK-SameeraNeural", "label": "萨米拉 · 僧伽罗语(斯里兰卡) 男声", "group": "国外"},
    {"value": "si-LK-ThiliniNeural", "label": "蒂利尼 · 僧伽罗语(斯里兰卡) 女声", "group": "国外"},
    {"value": "sk-SK-LukasNeural", "label": "卢卡斯 · 斯洛伐克语(斯洛伐克) 男声", "group": "国外"},
    {"value": "sk-SK-ViktoriaNeural", "label": "维多利亚 · 斯洛伐克语(斯洛伐克) 女声", "group": "国外"},
    {"value": "sl-SI-PetraNeural", "label": "佩特拉 · 斯洛文尼亚语(斯洛文尼亚) 女声", "group": "国外"},
    {"value": "sl-SI-RokNeural", "label": "罗克 · 斯洛文尼亚语(斯洛文尼亚) 男声", "group": "国外"},
    {"value": "so-SO-MuuseNeural", "label": "穆塞 · 索马里语(索马里) 男声", "group": "国外"},
    {"value": "so-SO-UbaxNeural", "label": "乌巴克斯 · 索马里语(索马里) 女声", "group": "国外"},
    {"value": "es-AR-ElenaNeural", "label": "埃琳娜 · 西班牙语(阿根廷) 女声", "group": "国外"},
    {"value": "es-AR-TomasNeural", "label": "托马什 · 西班牙语(阿根廷) 男声", "group": "国外"},
    {"value": "es-BO-MarceloNeural", "label": "马塞洛 · 西班牙语(玻利维亚) 男声", "group": "国外"},
    {"value": "es-BO-SofiaNeural", "label": "索菲亚 · 西班牙语(玻利维亚) 女声", "group": "国外"},
    {"value": "es-CL-CatalinaNeural", "label": "卡塔琳娜 · 西班牙语(智利) 女声", "group": "国外"},
    {"value": "es-CL-LorenzoNeural", "label": "洛伦佐 · 西班牙语(智利) 男声", "group": "国外"},
    {"value": "es-CO-GonzaloNeural", "label": "冈萨洛 · 西班牙语(哥伦比亚) 男声", "group": "国外"},
    {"value": "es-CO-SalomeNeural", "label": "萨洛梅 · 西班牙语(哥伦比亚) 女声", "group": "国外"},
    {"value": "es-ES-XimenaNeural", "label": "希梅娜 · 西班牙语(西班牙) 女声", "group": "国外"},
    {"value": "es-CR-JuanNeural", "label": "胡安 · 西班牙语(哥斯达黎加) 男声", "group": "国外"},
    {"value": "es-CR-MariaNeural", "label": "玛丽亚 · 西班牙语(哥斯达黎加) 女声", "group": "国外"},
    {"value": "es-CU-BelkysNeural", "label": "贝尔基斯 · 西班牙语(古巴) 女声", "group": "国外"},
    {"value": "es-CU-ManuelNeural", "label": "曼努埃尔 · 西班牙语(古巴) 男声", "group": "国外"},
    {"value": "es-DO-EmilioNeural", "label": "埃米利奥 · 西班牙语(多米尼加) 男声", "group": "国外"},
    {"value": "es-DO-RamonaNeural", "label": "拉莫娜 · 西班牙语(多米尼加) 女声", "group": "国外"},
    {"value": "es-EC-AndreaNeural", "label": "安德烈娅 · 西班牙语(厄瓜多尔) 女声", "group": "国外"},
    {"value": "es-EC-LuisNeural", "label": "路易斯 · 西班牙语(厄瓜多尔) 男声", "group": "国外"},
    {"value": "es-SV-LorenaNeural", "label": "洛雷娜 · 西班牙语(萨尔瓦多) 女声", "group": "国外"},
    {"value": "es-SV-RodrigoNeural", "label": "罗德里戈 · 西班牙语(萨尔瓦多) 男声", "group": "国外"},
    {"value": "es-GQ-JavierNeural", "label": "哈维尔 · 西班牙语(赤道几内亚) 男声", "group": "国外"},
    {"value": "es-GQ-TeresaNeural", "label": "特蕾莎 · 西班牙语(赤道几内亚) 女声", "group": "国外"},
    {"value": "es-GT-AndresNeural", "label": "安德烈斯 · 西班牙语(危地马拉) 男声", "group": "国外"},
    {"value": "es-GT-MartaNeural", "label": "玛尔塔 · 西班牙语(危地马拉) 女声", "group": "国外"},
    {"value": "es-HN-CarlosNeural", "label": "卡洛斯 · 西班牙语(洪都拉斯) 男声", "group": "国外"},
    {"value": "es-HN-KarlaNeural", "label": "卡拉 · 西班牙语(洪都拉斯) 女声", "group": "国外"},
    {"value": "es-MX-DaliaNeural", "label": "达利娅 · 西班牙语(墨西哥) 女声", "group": "国外"},
    {"value": "es-MX-JorgeNeural", "label": "豪尔赫 · 西班牙语(墨西哥) 男声", "group": "国外"},
    {"value": "es-NI-FedericoNeural", "label": "费德里科 · 西班牙语(尼加拉瓜) 男声", "group": "国外"},
    {"value": "es-NI-YolandaNeural", "label": "约兰达 · 西班牙语(尼加拉瓜) 女声", "group": "国外"},
    {"value": "es-PA-MargaritaNeural", "label": "玛格丽塔 · 西班牙语(巴拿马) 女声", "group": "国外"},
    {"value": "es-PA-RobertoNeural", "label": "罗伯托 · 西班牙语(巴拿马) 男声", "group": "国外"},
    {"value": "es-PY-MarioNeural", "label": "马里奥 · 西班牙语(巴拉圭) 男声", "group": "国外"},
    {"value": "es-PY-TaniaNeural", "label": "塔尼娅 · 西班牙语(巴拉圭) 女声", "group": "国外"},
    {"value": "es-PE-AlexNeural", "label": "亚历克斯 · 西班牙语(秘鲁) 男声", "group": "国外"},
    {"value": "es-PE-CamilaNeural", "label": "卡米拉 · 西班牙语(秘鲁) 女声", "group": "国外"},
    {"value": "es-PR-KarinaNeural", "label": "卡里娜 · 西班牙语(波多黎各) 女声", "group": "国外"},
    {"value": "es-PR-VictorNeural", "label": "维克托 · 西班牙语(波多黎各) 男声", "group": "国外"},
    {"value": "es-ES-AlvaroNeural", "label": "阿尔瓦罗 · 西班牙语(西班牙) 男声", "group": "国外"},
    {"value": "es-ES-ElviraNeural", "label": "埃尔维拉 · 西班牙语(西班牙) 女声", "group": "国外"},
    {"value": "es-US-AlonsoNeural", "label": "阿隆索 · 西班牙语(美国) 男声", "group": "国外"},
    {"value": "es-US-PalomaNeural", "label": "帕洛玛 · 西班牙语(美国) 女声", "group": "国外"},
    {"value": "es-UY-MateoNeural", "label": "马特奥 · 西班牙语(乌拉圭) 男声", "group": "国外"},
    {"value": "es-UY-ValentinaNeural", "label": "瓦伦蒂娜 · 西班牙语(乌拉圭) 女声", "group": "国外"},
    {"value": "es-VE-PaolaNeural", "label": "保拉 · 西班牙语(委内瑞拉) 女声", "group": "国外"},
    {"value": "es-VE-SebastianNeural", "label": "塞巴斯蒂安 · 西班牙语(委内瑞拉) 男声", "group": "国外"},
    {"value": "su-ID-JajangNeural", "label": "贾姜 · 巽他语(印度尼西亚) 男声", "group": "国外"},
    {"value": "su-ID-TutiNeural", "label": "图蒂 · 巽他语(印度尼西亚) 女声", "group": "国外"},
    {"value": "sw-KE-RafikiNeural", "label": "拉菲基 · 斯瓦希里语(肯尼亚) 男声", "group": "国外"},
    {"value": "sw-KE-ZuriNeural", "label": "祖里 · 斯瓦希里语(肯尼亚) 女声", "group": "国外"},
    {"value": "sw-TZ-DaudiNeural", "label": "达乌迪 · 斯瓦希里语(坦桑尼亚) 男声", "group": "国外"},
    {"value": "sw-TZ-RehemaNeural", "label": "蕾赫玛 · 斯瓦希里语(坦桑尼亚) 女声", "group": "国外"},
    {"value": "sv-SE-MattiasNeural", "label": "马蒂亚斯 · 瑞典语(瑞典) 男声", "group": "国外"},
    {"value": "sv-SE-SofieNeural", "label": "苏菲 · 瑞典语(瑞典) 女声", "group": "国外"},
    {"value": "ta-IN-PallaviNeural", "label": "帕拉维 · 泰米尔语(印度) 女声", "group": "国外"},
    {"value": "ta-IN-ValluvarNeural", "label": "瓦卢瓦尔 · 泰米尔语(印度) 男声", "group": "国外"},
    {"value": "ta-MY-KaniNeural", "label": "卡尼 · 泰米尔语(马来西亚) 女声", "group": "国外"},
    {"value": "ta-MY-SuryaNeural", "label": "苏里亚 · 泰米尔语(马来西亚) 男声", "group": "国外"},
    {"value": "ta-SG-AnbuNeural", "label": "安布 · 泰米尔语(新加坡) 男声", "group": "国外"},
    {"value": "ta-SG-VenbaNeural", "label": "文巴 · 泰米尔语(新加坡) 女声", "group": "国外"},
    {"value": "ta-LK-KumarNeural", "label": "库马尔 · 泰米尔语(斯里兰卡) 男声", "group": "国外"},
    {"value": "ta-LK-SaranyaNeural", "label": "萨拉尼亚 · 泰米尔语(斯里兰卡) 女声", "group": "国外"},
    {"value": "te-IN-MohanNeural", "label": "莫汉 · 泰卢固语(印度) 男声", "group": "国外"},
    {"value": "te-IN-ShrutiNeural", "label": "什鲁蒂 · 泰卢固语(印度) 女声", "group": "国外"},
    {"value": "th-TH-NiwatNeural", "label": "尼瓦特 · 泰语(泰国) 男声", "group": "国外"},
    {"value": "th-TH-PremwadeeNeural", "label": "普雷姆瓦迪 · 泰语(泰国) 女声", "group": "国外"},
    {"value": "tr-TR-EmelNeural", "label": "埃梅尔 · 土耳其语(土耳其) 女声", "group": "国外"},
    {"value": "tr-TR-AhmetNeural", "label": "艾哈迈德 · 土耳其语(土耳其) 男声", "group": "国外"},
    {"value": "uk-UA-OstapNeural", "label": "奥斯塔普 · 乌克兰语(乌克兰) 男声", "group": "国外"},
    {"value": "uk-UA-PolinaNeural", "label": "波琳娜 · 乌克兰语(乌克兰) 女声", "group": "国外"},
    {"value": "ur-IN-GulNeural", "label": "古尔 · 乌尔都语(印度) 女声", "group": "国外"},
    {"value": "ur-IN-SalmanNeural", "label": "萨勒曼 · 乌尔都语(印度) 男声", "group": "国外"},
    {"value": "ur-PK-AsadNeural", "label": "阿萨德 · 乌尔都语(巴基斯坦) 男声", "group": "国外"},
    {"value": "ur-PK-UzmaNeural", "label": "乌兹玛 · 乌尔都语(巴基斯坦) 女声", "group": "国外"},
    {"value": "uz-UZ-MadinaNeural", "label": "玛迪娜 · 乌兹别克语(乌兹别克斯坦) 女声", "group": "国外"},
    {"value": "uz-UZ-SardorNeural", "label": "萨尔多尔 · 乌兹别克语(乌兹别克斯坦) 男声", "group": "国外"},
    {"value": "vi-VN-HoaiMyNeural", "label": "怀美 · 越南语(越南) 女声", "group": "国外"},
    {"value": "vi-VN-NamMinhNeural", "label": "南明 · 越南语(越南) 男声", "group": "国外"},
    {"value": "cy-GB-AledNeural", "label": "阿莱德 · 威尔士语(英国) 男声", "group": "国外"},
    {"value": "cy-GB-NiaNeural", "label": "妮娅 · 威尔士语(英国) 女声", "group": "国外"},
    {"value": "zu-ZA-ThandoNeural", "label": "坦多 · 祖鲁语(南非) 女声", "group": "国外"},
    {"value": "zu-ZA-ThembaNeural", "label": "森巴 · 祖鲁语(南非) 男声", "group": "国外"},
    {"value": "zh-CN-XiaobeiNeural", "label": "晓北 · 普通话女声，爽朗大方", "group": "中国"},
    {"value": "zh-CN-XiaoxuanNeural", "label": "晓萱 · 娇俏可爱的女声，软糯甜美", "group": "中国"},
]

# 默认空配置模板（实际配置由 _conf_schema.json 管理）
DEFAULT_CONFIG = {
    "api_base_url": "",
    "api_key": "",
    "chat_api_base_url": "",
    "chat_api_key": "",
    "chat_provider_id": "",
    "chat_model": "",
    "chat_model_enable": True,
    "custom_model_enable": False,
    "vision_api_base_url": "",
    "vision_api_key": "",
    "vision_provider_id": "",
    "vision_model": "",
    "vision_model_enable": True,
    "persona": "zhixin",
    "hide_ai_identity": True,
    "use_astrbot_default_persona": False,
    "astrbot_persona": "",


    "enable_long_memory": True,
    "memory_recall_count": 3,
    "auto_save_memory": True,
    "group_image_reply": False,
    "enable_emoji_analysis": True,
    "enable_facial_expression": True,
    "gif_first_frame": True,
    "ignore_mention_others": False,
    "enable_proactive_chat": False,
    "proactive_chat_frequency": 10,
    "tts_enable": True,
    "tts_mode": "text_voice",
    "tts_voice": "zh-CN-XiaoyiNeural",
    "tts_speed": 1.0,
    "tts_pitch": "",
    "tts_max_length": 300,
    "max_log": 14,
    "on_thinking": True,
    "session_expire_seconds": 120,
    "enable_favorability": False,
    "favorability_default": 50,
    "enable_private_companion": False,
    "master_user_ids": [],
    "avoid_intimate_non_master": True,
    "enable_noprefix_command": True,
}


class CustomChatLLM(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        # 人格库缓存（首次使用时从 KV 加载）
        self.personas: list[dict] = []
        # 群聊会话激活表: key = (platform_id, group_id, user_id) -> 过期时间戳
        self.active_sessions: dict[tuple, float] = {}

        # 环境检测（电脑版 / Docker 通用）：ffmpeg 缺失时 TTS 语音发送可能失败，提前告警
        if self.config.get("tts_enable", True) and not self._ffmpeg_installed():
            logger.warning(
                "[Edge_TTS] 未检测到系统 ffmpeg！语音播报可能无法正常发送。"
                "电脑版请参照 README 安装 ffmpeg；Docker 请使用已内置 ffmpeg 的官方镜像。"
            )

        # 注册控制界面后端 Web API
        context.register_web_api(
            f"/{PLUGIN_NAME}/status", self.api_status, ["GET"], "获取运行状态"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/config", self.api_get_config, ["GET"], "获取配置"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/config/save",
            self.api_save_config,
            ["POST"],
            "保存配置",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/personas", self.api_get_personas, ["GET"], "获取人格列表"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/personas/add",
            self.api_add_persona,
            ["POST"],
            "新增人格",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/personas/update",
            self.api_update_persona,
            ["POST"],
            "更新人格",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/personas/delete",
            self.api_delete_persona,
            ["POST"],
            "删除人格",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/personas/select",
            self.api_select_persona,
            ["POST"],
            "切换当前人格",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/memory", self.api_get_memory, ["GET"], "获取长期记忆列表"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/memory/delete",
            self.api_delete_memory,
            ["POST"],
            "删除单条长期记忆",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/memory/clear",
            self.api_clear_memory,
            ["POST"],
            "清空长期记忆",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/memory/add",
            self.api_add_memory,
            ["POST"],
            "新增长期记忆",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/favorability",
            self.api_get_favorability,
            ["GET"],
            "获取好感度列表",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/favorability/set",
            self.api_set_favorability,
            ["POST"],
            "设置好感度",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/favorability/delete",
            self.api_delete_favorability,
            ["POST"],
            "删除好感度",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/favorability/clear",
            self.api_clear_favorability,
            ["POST"],
            "清空好感度",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/test_api", self.api_test_api, ["POST"], "测试模型接口连通性"
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/model_status",
            self.api_model_status,
            ["POST"],
            "检测自定义/AstrBot 模型开启状态并测试连通性",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/check_address",
            self.api_check_address,
            ["POST"],
            "检测自定义模型 API 地址类型（通用端点 / 完整端点）",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/providers",
            self.api_get_providers,
            ["GET"],
            "获取 AstrBot 已配置的模型提供商列表",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/provider_models",
            self.api_get_provider_models,
            ["POST"],
            "获取指定提供商的可用模型列表",
        )

    # ===================== 工具函数 =====================

    # ---- 人格库 ----

    async def _ensure_personas(self) -> None:
        """加载人格库（懒加载，首次调用时从 KV 读取，不存在则写入默认预设）。"""
        if self.personas:
            return
        stored = await self.get_kv_data(PERSONAS_KEY, None)
        if isinstance(stored, list) and stored:
            self.personas = stored
        else:
            self.personas = [dict(p) for p in DEFAULT_PERSONAS]
            await self.put_kv_data(PERSONAS_KEY, self.personas)

    async def _save_personas(self) -> None:
        await self.put_kv_data(PERSONAS_KEY, self.personas)

    def _find_persona(self, pid: str) -> dict | None:
        return next((p for p in self.personas if p.get("id") == pid), None)

    async def get_persona_prompt(self) -> str:
        # 启用"默认 AstrBot 人格"时，不注入插件人格库，改用 AstrBot 侧人格
        if self.config.get("use_astrbot_default_persona", False):
            persona = await self._get_astrbot_persona()
            return persona.get("prompt") or "You are a helpful and friendly assistant."
        await self._ensure_personas()
        pid = self.config.get("persona", "")
        p = self._find_persona(pid)
        if not p and self.personas:
            p = self.personas[0]
        return (p or {}).get("prompt") or "你是一位友好的AI助手。"

    async def _get_astrbot_persona(self) -> dict:
        """返回 AstrBot 侧当前生效人格的信息 dict（含 name / prompt）。

        - astrbot_persona 为空时：跟随 AstrBot 配置文件当前采用的人格
          （provider_settings.default_personality），由 persona_manager 动态解析。
        - 否则按配置的 astrbot_persona 名字从 persona_manager 匹配。

        Returns:
            dict: 人格字典，name 为空时表示未找到。
        """
        sel_name = self.config.get("astrbot_persona", "") or ""
        try:
            persona_manager = self.context.persona_manager
            if not sel_name:
                # 跟随 AstrBot 配置文件当前采用的人格
                default_v3 = await persona_manager.get_default_persona_v3()
                if default_v3 and default_v3.get("name"):
                    return {
                        "name": default_v3.get("name", ""),
                        "prompt": default_v3.get("prompt", ""),
                    }
                from astrbot.core.persona_mgr import DEFAULT_PERSONALITY

                return {"name": "default", "prompt": DEFAULT_PERSONALITY.get("prompt", "")}
            for p in persona_manager.personas_v3 or []:
                if p.get("name") == sel_name:
                    return {
                        "name": p.get("name", ""),
                        "prompt": p.get("prompt", ""),
                    }
            # personas_v3 未初始化时，用 db 原始人格数据按 persona_id 匹配
            for p in persona_manager.personas or []:
                if getattr(p, "persona_id", "") == sel_name:
                    return {
                        "name": sel_name,
                        "prompt": getattr(p, "system_prompt", "") or "",
                    }
        except Exception as e:
            logger.warning(f"获取 AstrBot 人格失败: {e}")
        return {"name": sel_name, "prompt": ""}

    def _list_astrbot_personas(self) -> list[dict]:
        """返回 AstrBot 侧已配置的人格列表。"""
        result = []
        try:
            persona_manager = self.context.persona_manager
            for p in persona_manager.personas_v3 or []:
                result.append({"name": p.get("name", ""), "prompt": p.get("prompt", "")})
            if result:
                return result
            # personas_v3 未初始化时回退到 db 中的原始人格数据
            for p in persona_manager.personas or []:
                result.append(
                    {"name": getattr(p, "persona_id", "") or "", "prompt": getattr(p, "system_prompt", "") or ""}
                )
        except Exception as e:
            logger.error(f"获取 AstrBot 人格列表失败: {e}")
        return result

    # ---- 记忆存储（文件管理） ----

    def _memory_dir(self) -> str:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", MEMORY_DIR_NAME)
        os.makedirs(d, exist_ok=True)
        return d

    def _memory_file(self, uid: str) -> str:
        """获取记忆文件路径，增加安全检查"""
        # 校验 uid 参数，防止路径遍历攻击
        if not uid or not isinstance(uid, str):
            raise ValueError("Invalid uid")
        # 只允许字母、数字、下划线、连字符和冒号
        if not re.match(r'^[a-zA-Z0-9_\-:]+$', uid):
            raise ValueError("Invalid uid format")
        
        # 构建文件路径
        file_path = os.path.join(self._memory_dir(), f"{uid}.json")
        
        # 确保文件路径在 memory 目录下
        if not os.path.abspath(file_path).startswith(os.path.abspath(self._memory_dir())):
            raise ValueError("Invalid memory file path")
        
        return file_path

    async def get_user_memory(self, uid: str) -> list[dict]:
        try:
            with open(self._memory_file(uid), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    async def save_user_memory(self, uid: str, memory_arr: list[dict]) -> None:
        with open(self._memory_file(uid), "w", encoding="utf-8") as f:
            json.dump(memory_arr, f, ensure_ascii=False, indent=2)

    async def delete_user_memory(self, uid: str, mem_id: str) -> bool:
        memories = await self.get_user_memory(uid)
        new_memories = [m for m in memories if m.get("id") != mem_id]
        if len(new_memories) == len(memories):
            return False
        await self.save_user_memory(uid, new_memories)
        return True

    async def get_memory_users(self) -> list[str]:
        try:
            users = []
            for fn in os.listdir(self._memory_dir()):
                if fn.endswith(".json"):
                    users.append(fn[:-5])
            return users
        except Exception:
            return []

    # ---- 好感度存储（文件管理） ----

    def _favorability_file(self) -> str:
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "favorability.json"
        )

    async def _load_favorability(self) -> dict:
        """返回 {"user": {uid: 值}, "group": {gid: 值}}。"""
        try:
            with open(self._favorability_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            data.setdefault("user", {})
            data.setdefault("group", {})
            return data
        except Exception:
            return {"user": {}, "group": {}}

    async def _save_favorability(self, data: dict) -> None:
        d = os.path.dirname(self._favorability_file())
        os.makedirs(d, exist_ok=True)
        with open(self._favorability_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def get_favorability(self, scope: str, key: str) -> int:
        data = await self._load_favorability()
        default = int(self.config.get("favorability_default", 50) or 50)
        try:
            return int(data.get(scope, {}).get(str(key), default))
        except Exception:
            return default

    async def change_favorability(self, scope: str, key: str, delta: int = 1) -> int:
        data = await self._load_favorability()
        default = int(self.config.get("favorability_default", 50) or 50)
        try:
            cur = int(data.get(scope, {}).get(str(key), default))
        except Exception:
            cur = default
        new_val = max(0, min(100, cur + delta))
        data.setdefault(scope, {})[str(key)] = new_val
        await self._save_favorability(data)
        return new_val

    def get_chat_key(self, event: AstrMessageEvent) -> str:
        gid = event.get_group_id()
        prefix = gid if gid else "private"
        return f"{PLUGIN_NAME}:chat_log:{prefix}:{event.get_sender_id()}"

    def _memory_uid(self, event: AstrMessageEvent) -> str:
        """记忆存储键：私聊按用户（user_xxx），群聊按用户（group_xxx:sender_id）。"""
        gid = event.get_group_id()
        if gid:
            return f"group_{gid}:{event.get_sender_id()}"
        return f"user_{event.get_sender_id()}"

    def session_key(self, event: AstrMessageEvent) -> tuple:
        return (event.get_platform_id(), event.get_group_id(), event.get_sender_id())



    # ===================== 长期记忆 =====================

    def _text2vector(self, text: str) -> list[float]:
        h = base64.b64encode(text.encode("utf-8")).decode()
        vec = []
        for i in range(min(len(h), 16)):
            vec.append(ord(h[i]) / 255.0)
        while len(vec) < 16:
            vec.append(0.0)
        return vec

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    async def recall_memory(self, uid: str, query: str) -> list[dict]:
        if not self.config.get("enable_long_memory", True):
            return []
        memories = await self.get_user_memory(uid)
        if not memories:
            return []
        query_vec = self._text2vector(query)
        results = []
        for mem in memories:
            score = self._cosine_similarity(query_vec, mem.get("vector", []))
            if score >= 0.5:
                results.append({"content": mem.get("content", ""), "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[: int(self.config.get("memory_recall_count", 3))]

    async def add_memory(self, uid: str, content: str) -> None:
        memories = await self.get_user_memory(uid)
        memories.append(
            {
                "id": str(uuid.uuid4()),
                "content": content,
                "vector": self._text2vector(content),
                "createTime": int(time.time() * 1000),
            }
        )
        await self.save_user_memory(uid, memories)

    # ===================== Edge TTS 语音 =====================

    def _ffmpeg_installed(self) -> bool:
        """检测系统是否安装了 ffmpeg（语音发送依赖，Docker 官方镜像已内置）。

        Returns:
            True 表示可用；False 表示未安装。
        """
        return shutil.which("ffmpeg") is not None

    async def text_to_voice(self, text: str, has_image: bool = False, is_only_at: bool = False) -> str | None:
        """返回生成的音频文件路径，失败返回 None。
        
        Args:
            text: 要转换为语音的文本
            has_image: 是否包含图片（用于特殊处理）
            is_only_at: 是否仅为纯@机器人场景（无文字）
        """
        logger.debug(f"开始生成语音，输入文本: {text[:50]}..., is_only_at: {is_only_at}")
        
        if not self.config.get("tts_enable", True):
            logger.debug("TTS 功能已禁用")
            return None
            
        clean = text.replace("\n", " ").replace("#", "").replace("*", "").replace("`", "")
        clean = " ".join(clean.split())
        
        # 特殊处理：如果文本为空但有图片，使用默认描述
        if not clean and has_image:
            clean = "请描述这张图片的内容"
            logger.debug("文本为空但有图片，使用默认描述")
            
        # 特殊处理：纯@机器人场景（无文字），使用默认问候语
        if not clean and is_only_at:
            clean = "你好，有什么可以帮助你的吗？"
            logger.debug("纯@机器人场景，使用默认问候语")
            
        if not clean:
            logger.debug("清理后的文本为空")
            return None
            
        max_len = int(self.config.get("tts_max_length", 300))
        if len(clean) > max_len:
            clean = clean[:max_len]
            logger.debug(f"文本长度超过最大限制，已截断为: {clean[:50]}...")
            
        voice = self.config.get("tts_voice", "zh-CN-XiaoyiNeural")
        logger.debug(f"使用语音: {voice}")
        
        try:
            # 处理语速
            rate_val = max(0.6, min(1.4, float(self.config.get("tts_speed", 1.0))))
            rate_str = f"{'+' if rate_val >= 1 else '-'}{abs(round((rate_val - 1) * 100))}%"
            logger.debug(f"语音速度: {rate_val} ({rate_str})")
            
            # 处理音调（转换为Hz格式）
            pitch_val = self.config.get("tts_pitch", "")
            if pitch_val:
                # 如果用户输入的是百分比格式，转换为Hz（如+10% -> +50Hz）
                if pitch_val.endswith("%"):
                    percent = float(pitch_val[:-1])
                    pitch_val = f"{percent * 5:.0f}Hz"
                # 如果用户输入的是纯数字（不带单位），添加Hz单位
                elif pitch_val.replace("-", "").replace("+", "").isdigit():
                    pitch_val = f"{pitch_val}Hz"
                logger.debug(f"语音音调: {pitch_val}")
            

            

            
            # 构建语音参数
            communicate_params = {
                "rate": rate_str,
            }
            if pitch_val:
                communicate_params["pitch"] = pitch_val
            

            
            logger.debug(f"最终语音参数: {communicate_params}")
            
            # 兼容 Windows/Linux：使用系统临时目录（W11 下为 %TEMP%）
            tts_dir = os.path.join(tempfile.gettempdir(), "custom_chat_llm_tts")
            os.makedirs(tts_dir, exist_ok=True)
            out_path = os.path.join(tts_dir, f"tts_{uuid.uuid4().hex}.mp3")
            logger.debug(f"语音文件将保存到: {out_path}")
            
            communicate = edge_tts.Communicate(clean, voice, **communicate_params)
            await communicate.save(out_path)
            
            if os.path.exists(out_path):
                logger.debug(f"语音文件生成成功: {out_path}")
                return out_path
            else:
                logger.error(f"语音文件生成失败: {out_path}")
                return None
        except Exception as e:
            logger.error(f"Edge TTS 生成失败: {e}")
            return None

    # ===================== LLM 调用（OpenAI 兼容） =====================

    def _normalize_api_endpoint(self, base_url: str) -> str:
        """将自定义 API 地址规范化为 OpenAI 兼容的 chat/completions 完整端点。

        支持两种填写方式：
        - 通用端点（推荐）：如 https://open.bigmodel.cn/api/paas/v4，
          自动补全为 .../chat/completions；
        - 完整端点：如 https://api.example.com/v1/chat/completions，原样使用。

        Args:
            base_url: 用户填写的 API 地址。

        Returns:
            完整的 chat/completions 端点地址。
        """
        url = (base_url or "").strip().rstrip("/")
        if not url:
            return url
        if url.endswith("/chat/completions"):
            return url
        return url + "/chat/completions"

    def _classify_api_endpoint(self, base_url: str) -> dict:
        """判断自定义 API 地址是否为「其它模型/品牌通用地址」（通用端点）。

        通用端点指提供商网关地址（如 https://open.bigmodel.cn/api/paas/v4），
        同一地址可服务对话/识图等多个模型、甚至接入其它品牌模型（仅需填对应模型名），
        插件会自动补全 /chat/completions；完整端点则以 /chat/completions 结尾，原样请求。

        Args:
            base_url: 用户填写的 API 地址。

        Returns:
            {"type": "generic" | "full" | "empty", "effective": 实际请求地址}。
        """
        url = (base_url or "").strip().rstrip("/")
        if not url:
            return {"type": "empty", "effective": ""}
        if url.endswith("/chat/completions"):
            return {"type": "full", "effective": url}
        return {"type": "generic", "effective": url + "/chat/completions"}

    async def api_check_address(self):
        """Web API：检测自定义模型 API 地址类型，供控制界面实时提示。"""
        payload = await request.json(default={})
        base_url = str(payload.get("api_base_url") or "").strip()
        return json_response(self._classify_api_endpoint(base_url))

    def _build_messages(self, system_prompt: str, history: list[dict], user_msg: Any) -> list[dict]:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_msg})
        return messages

    async def _call_llm(
        self,
        messages: list[dict],
        model: str | None = None,
        tools: list | None = None,
        is_vision: bool = False,
    ) -> dict:
        # 自定义 API 直连模式（OpenAI 兼容）：开启“自定义模型”开关且配置了 API 地址则优先使用。
        # 对话与识图共用同一个 API 地址与 Key（api_base_url / api_key），仅模型名称不同；
        # 兼容旧配置：未填新字段时回退到旧版本的 chat_api_base_url / chat_api_key。
        custom_model_enable = self.config.get("custom_model_enable", False)
        base_url = self.config.get("api_base_url", "") or self.config.get("chat_api_base_url", "")
        api_key = self.config.get("api_key", "") or self.config.get("chat_api_key", "")
        if custom_model_enable and base_url:
            model = model or (self.config.get("vision_model" if is_vision else "chat_model", ""))
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": 0.8,
                "stream": False,
            }
            if tools:
                payload["tools"] = tools
            if self.config.get("on_thinking", True):
                payload["thinking"] = {"type": "enabled"}
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(self._normalize_api_endpoint(base_url), json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        # 默认采用 AstrBot 管理面板（cmd_config.json）中配置的模型，配置随面板改动实时生效
        prov = await self._resolve_provider(is_vision)
        if not prov:
            raise RuntimeError("未配置模型，请在 AstrBot 管理面板配置对话模型，或在控制界面填写自定义 API 地址")
        provider_id = prov.meta().id
        # 优先使用插件配置中填写的模型名（chat_model / vision_model），
        # 留空时沿用该提供商在 AstrBot 配置中的默认模型。
        model = model or (self.config.get("vision_model" if is_vision else "chat_model", "") or None)
        if not self.config.get("custom_model_enable", False):
            model = None
        return await self._call_llm_via_provider(provider_id, messages, model=model, tools=tools)

    def _astrbot_provider_settings(self) -> dict:
        """读取 AstrBot 配置文件（cmd_config.json）中的 provider_settings。

        直接读取磁盘上的配置文件，确保用户修改配置文件后本插件立即跟随，
        无需等待 AstrBot 重载或重启。

        Returns:
            provider_settings 字典；读取失败时返回空字典。
        """
        try:
            from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH

            with open(ASTRBOT_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            ps = data.get("provider_settings", {})
            return ps if isinstance(ps, dict) else {}
        except Exception as e:
            logger.error(f"读取 AstrBot 配置文件失败: {e}")
            return {}

    def _astrbot_ai_enable(self) -> bool:
        """读取 AstrBot 配置文件中的"AI 对话总开关"（provider_settings.enable）。

        Returns:
            True 表示开启；关闭或未设置时返回 False。
        """
        ps = self._astrbot_provider_settings()
        return bool(ps.get("enable", True))

    def _astrbot_default_provider_id(self) -> str:
        """读取 AstrBot 配置文件中的"默认对话模型"提供商 ID。

        Returns:
            提供商的 ID；未配置时返回空字符串。
        """
        return str(self._astrbot_provider_settings().get("default_provider_id") or "")

    def _astrbot_image_caption_provider_id(self) -> str:
        """读取 AstrBot 配置文件中的"默认图片转述模型"提供商 ID。

        Returns:
            提供商的 ID；未配置时返回空字符串。
        """
        return str(self._astrbot_provider_settings().get("default_image_caption_provider_id") or "")

    async def _resolve_provider(self, is_vision: bool = False) -> Any | None:
        """解析本次对话使用的模型提供商（采用 AstrBot 配置）。

        优先使用插件配置里选择的 provider ID（chat_provider_id / vision_provider_id），
        AstrBot 配置文件的"AI 对话总开关"（provider_settings.enable）关闭时两个模型都视为关闭；
        对话模型采用 AstrBot 配置文件中的"默认对话模型"（default_provider_id），
        识图模型采用 AstrBot 配置文件中的"默认图片转述模型"（default_image_caption_provider_id），
        未配置时识图模型回退到对话模型。
        对话模型默认配置留空即代表不使用（可用于非多模态模型），此时视为未配置。
        每次调用都直接读取 AstrBot 配置文件（cmd_config.json），
        用户修改配置文件后本插件会立即跟随，无需重复配置或重启。

        Args:
            is_vision: True 时解析识图模型提供商，否则解析对话模型提供商。

        Returns:
            解析到的提供商实例；无可用提供商时返回 None。
        """
        # AstrBot "AI 对话总开关"关闭时，两个模型都视为关闭；开启“自定义模型”时不受此限制
        if not self._astrbot_ai_enable() and not self.config.get("custom_model_enable", False):
            return None
        # 开启“自定义模型”但未配置 API 地址时，视为未配置，不调用 AstrBot 系统模型
        if self.config.get("custom_model_enable", False) and not (
            self.config.get("api_base_url", "") or self.config.get("chat_api_base_url", "")
        ):
            return None
        cfg_id = self.config.get("vision_provider_id" if is_vision else "chat_provider_id", "")
        if cfg_id:
            prov = self.context.get_provider_by_id(cfg_id)
            if prov:
                return prov
        # 直接读取 AstrBot 配置文件中的默认模型，文件修改后立即跟随
        if is_vision:
            default_id = self._astrbot_image_caption_provider_id()
        else:
            default_id = self._astrbot_default_provider_id()
        if default_id:
            prov = self.context.get_provider_by_id(default_id)
            if prov:
                return prov
        # 识图模型未单独配置时不回退到对话模型，如实视为未配置
        if is_vision:
            return None
        # 对话模型：AstrBot 配置留空时回退使用其第一个模型（与 AstrBot 本身行为一致）
        try:
            return self.context.get_using_provider()
        except Exception as e:
            logger.warning(f"获取 AstrBot 默认模型失败: {e}")
            return None



    async def _call_llm_via_provider(
        self,
        provider_id: str,
        messages: list[dict],
        model: str | None = None,
        tools: list | None = None,
    ) -> dict:
        """通过 AstrBot 已配置的 Provider 调用模型，统一返回 OpenAI 兼容 dict。

        注意：AstrBot 的 text_chat 仅接收 model 等显式参数，temperature 等
        额外 kwargs 会被静默忽略，深度思考等行为由 AstrBot 侧 provider 配置控制。
        """
        prov = self.context.get_provider_by_id(provider_id)
        if not prov:
            raise RuntimeError(f"未找到 AstrBot 提供商: {provider_id}")
        kwargs: dict[str, Any] = {"contexts": messages}
        if model:
            kwargs["model"] = model
        llm_resp = await self.context.llm_generate(
            chat_provider_id=provider_id,
            tools=None,
            **kwargs,
        )
        message: dict[str, Any] = {
            "role": "assistant",
            "content": (llm_resp.completion_text or None),
        }
        return {"choices": [{"message": message}]}



    async def chat_with_llm(
        self,
        event: AstrMessageEvent,
        system_prompt: str,
        history: list[dict],
        user_msg: Any,
        is_vision: bool = False,
    ) -> str:
        messages = self._build_messages(system_prompt, history, user_msg)
        # 模型由 provider 解析决定（默认采用 AstrBot 配置），自定义 API 直连模式在 _call_llm 内取插件配置的模型
        model = None
        data = await self._call_llm(messages, model=model, tools=None, is_vision=is_vision)
        if not data.get("choices"):
            raise RuntimeError("模型未返回有效内容")
        message = data["choices"][0].get("message", {})
        return (message.get("content") or "").strip()

    # ===================== 命令处理 =====================

    @filter.command("聊天菜单")
    async def show_menu(self, event: AstrMessageEvent):
        '''查看Edge_TTS功能菜单'''
        chat_enable = await self.get_kv_data(f"{PLUGIN_NAME}:chat_switch", True)
        memory_status = "✅开启" if self.config.get("enable_long_memory", True) else "❌关闭"
        tts_status = "✅开启" if self.config.get("tts_enable", True) else "❌关闭"
        await self._ensure_personas()
        cur = self._find_persona(self.config.get("persona", ""))
        if self.config.get("use_astrbot_default_persona", False):
            sel_persona = await self._get_astrbot_persona()
            cur_name = sel_persona.get("name") or "默认AstrBot人格"
        else:
            cur_name = cur.get("name") if cur else "未设置"
        menu = (
            "=====Edge_TTS 功能菜单=====\n"
            "/聊天菜单       打开此帮助菜单\n"
            "/开启聊天       开启全局对话\n"
            "/关闭聊天       关闭全局对话\n"
            "/清空对话       清空本次上下文\n"
            "/记忆列表       查看长期记忆\n"
            "/删除记忆 序号  删除第 N 条长期记忆\n"
            "/清空长期记忆    删除全部永久记忆\n"
            "/人格列表       查看可用人格\n"
            "/语音开关       开启/关闭语音播报\n"
            "/语音模式 值    切换语音模式（text/voice/text_voice）\n"
            "/设置模型 值    修改对话模型\n"
            "/设置人格 名字  切换人格\n"
            "\n"
            "状态信息：\n"
            f"总开关：{'✅开启' if chat_enable else '❌关闭'}\n"
            f"对话模型：{'✅开启' if self.config.get('chat_model_enable', True) else '❌关闭'}\n"
            f"识图模型：{'✅开启' if self.config.get('vision_model_enable', True) else '❌关闭'}\n"
            f"长期记忆：{memory_status}\n"
            f"Edge语音TTS：{tts_status}\n"
            f"当前人格：{cur_name}\n"
            "\n"
            "群聊：@机器人唤醒会话，2分钟内无需重复@\n"
            "私聊：直接发送消息对话\n"
            "更详细的 API 地址/模型/人格库/音色等配置，请在管理面板的插件控制界面中修改。"
        )
        yield event.plain_result(menu)

    @filter.command("开启聊天")
    async def open_chat(self, event: AstrMessageEvent):
        '''开启全局对话'''
        await self.put_kv_data(f"{PLUGIN_NAME}:chat_switch", True)
        yield event.plain_result("✅【Edge_TTS 已开启】")

    @filter.command("关闭聊天")
    async def close_chat(self, event: AstrMessageEvent):
        '''关闭全局对话'''
        await self.put_kv_data(f"{PLUGIN_NAME}:chat_switch", False)
        yield event.plain_result("⚠️【Edge_TTS 已关闭】")

    @filter.command("清空对话")
    async def clear_chat(self, event: AstrMessageEvent):
        '''清空本次会话上下文'''
        await self.delete_kv_data(self.get_chat_key(event))
        yield event.plain_result("✅短期对话上下文已清空，本次聊天记录已忘记（长期记忆保留）")

    @filter.command("记忆列表")
    async def show_memory_list(self, event: AstrMessageEvent):
        '''查看长期记忆列表'''
        uid = self._memory_uid(event)
        memories = await self.get_user_memory(uid)
        if not memories:
            yield event.plain_result("📝暂无长期记忆，多聊天会自动保存重要对话")
            return
        msg = f"📝长期记忆（共{len(memories)}条）：\n"
        for idx, item in enumerate(memories):
            msg += f"{idx + 1}. {item.get('content', '')}\n"
        yield event.plain_result(msg)

    @filter.command("删除记忆")
    async def delete_memory_cmd(self, event: AstrMessageEvent, index: str):
        '''按序号删除第 N 条长期记忆'''
        uid = self._memory_uid(event)
        try:
            idx = int(index) - 1
        except ValueError:
            yield event.plain_result("用法：/删除记忆 序号，例如 /删除记忆 3")
            return
        memories = await self.get_user_memory(uid)
        if idx < 0 or idx >= len(memories):
            yield event.plain_result("序号超出范围，请使用 /记忆列表 查看序号")
            return
        mem_id = memories[idx].get("id")
        await self.delete_user_memory(uid, mem_id)
        yield event.plain_result(f"✅已删除第 {idx + 1} 条长期记忆")

    @filter.command("清空长期记忆")
    async def clear_long_memory(self, event: AstrMessageEvent):
        '''清空自己的全部长期记忆'''
        uid = self._memory_uid(event)
        await self.save_user_memory(uid, [])
        yield event.plain_result("✅全部长期记忆清除完毕，不会再有过往内容")

    @filter.command("设置模型")
    async def set_model(self, event: AstrMessageEvent, model: str):
        '''修改对话模型'''
        self.config["chat_model"] = model.strip()
        self.config.save_config()
        yield event.plain_result(f"✅对话模型已切换为：{model.strip()}")

    @filter.command("语音开关")
    async def toggle_tts(self, event: AstrMessageEvent):
        '''开启/关闭语音播报'''
        self.config["tts_enable"] = not self.config.get("tts_enable", True)
        self.config.save_config()
        yield event.plain_result("✅语音播报已开启" if self.config["tts_enable"] else "❌语音播报已关闭")

    @filter.command("语音模式")
    async def set_tts_mode(self, event: AstrMessageEvent, mode: str):
        '''切换语音模式（text/voice/text_voice）'''
        allow = ["text", "voice", "text_voice"]
        if mode not in allow:
            yield event.plain_result("可用模式：text / voice / text_voice\n示例：/语音模式 text_voice")
            return
        self.config["tts_mode"] = mode
        self.config.save_config()
        yield event.plain_result(f"✅语音模式切换至：{mode}")

    @filter.command("人格列表")
    async def list_personas_cmd(self, event: AstrMessageEvent):
        '''查看可用人格'''
        await self._ensure_personas()
        current = self.config.get("persona", "")
        msg = "🧠可用人格：\n"
        for p in self.personas:
            mark = " ✅当前" if p.get("id") == current else ""
            msg += f"- {p.get('name')}：{p.get('description', '')}{mark}\n"
        yield event.plain_result(msg)

    @filter.command("设置人格")
    async def set_persona(self, event: AstrMessageEvent, persona: str):
        '''切换人格'''
        await self._ensure_personas()
        name = persona.strip()
        target = next((p for p in self.personas if p.get("name") == name), None)
        if not target:
            names = " / ".join(p.get("name", "") for p in self.personas)
            yield event.plain_result(f"未找到人格「{name}」，可用人格：{names}")
            return
        self.config["persona"] = target["id"]
        self.config.save_config()
        yield event.plain_result(f"✅人格已切换为：{target['name']}")

    # ===================== 对话入口 =====================

    # 无 / 前缀指令路由表：{指令名: (处理方法名, 是否带参数)}
    _NOPREFIX_COMMANDS = {
        "聊天菜单": ("show_menu", False),
        "开启聊天": ("open_chat", False),
        "关闭聊天": ("close_chat", False),
        "清空对话": ("clear_chat", False),
        "记忆列表": ("show_memory_list", False),
        "清空长期记忆": ("clear_long_memory", False),
        "语音开关": ("toggle_tts", False),
        "人格列表": ("list_personas_cmd", False),
        "删除记忆": ("delete_memory_cmd", True),
        "设置模型": ("set_model", True),
        "语音模式": ("set_tts_mode", True),
        "设置人格": ("set_persona", True),
    }

    async def _route_noprefix_command(self, event: AstrMessageEvent, text: str) -> bool:
        """将不带 / 前缀的插件指令路由到对应处理方法（如直接发送"聊天菜单"）。

        返回 True 表示已作为指令处理并发送结果，False 表示不是插件指令。
        """
        tokens = [t for t in text.split() if t.strip() and not t.startswith("@")]
        if not tokens:
            return False
        cmd = tokens[0]
        args = tokens[1:]
        entry = self._NOPREFIX_COMMANDS.get(cmd)
        if not entry:
            return False
        method_name, need_args = entry
        method = getattr(self, method_name)
        if need_args:
            if not args:
                await event.send(MessageChain([Plain(f"用法：{cmd} 参数")]))
                return True
            gen = method(event, " ".join(args))
        else:
            if args:
                return False
            gen = method(event)
        try:
            async for result in gen:
                if isinstance(result, str):
                    await event.send(MessageChain([Plain(result)]))
                else:
                    await event.send(result)
        except Exception as e:
            logger.error(f"无前缀指令处理失败: {e}")
            await event.send(MessageChain([Plain("指令处理失败，请稍后再试")]))
        event.stop_event()
        return True

    @filter.event_message_type(filter.EventMessageType.ALL, priority=inf)
    async def chat_main(self, event: AstrMessageEvent):
        """监听所有消息，判断是否由本插件响应。"""
        messages = event.get_messages()
        has_image = any(isinstance(comp, Image) for comp in messages)
        text = (event.get_message_str() or "").strip()
        
        logger.info(f"[Edge_TTS] 收到消息 - 平台:{event.get_platform_id()}, 私聊:{event.is_private_chat()}, 群:{event.get_group_id()}, 发送者:{event.get_sender_id()}, 文本:'{text}', 组件:{[type(c).__name__ for c in messages]}")

        # 指令消息检测：本插件或其他插件以 / 开头的指令均不触发 AI 回复
        is_command = text.startswith("/") or any(
            isinstance(comp, Plain) and str(getattr(comp, "text", "") or "").strip().startswith("/")
            for comp in messages
        )
        if is_command:
            in_group = event.get_group_id() is not None
            if in_group and not event.is_private_chat():
                # 群聊中带/指令：检查是否@了机器人，没@则不拦截，放行给其他插件
                is_at_bot_now = any(
                    isinstance(comp, At) and str(getattr(comp, "qq", "")) == str(event.get_self_id())
                    for comp in messages
                )
                if not is_at_bot_now:
                    logger.debug(f"[Edge_TTS] 群聊中带/指令未@机器人，不拦截，放行给其他插件")
                    return
            logger.debug(f"[Edge_TTS] 检测到指令消息，不回复")
            return

        # 无 / 前缀的插件指令路由：直接发送指令名也能触发（如"聊天菜单"）
        # 群聊中无需@机器人也可触发
        if text and not is_command and self.config.get("enable_noprefix_command", True):
            routed = await self._route_noprefix_command(event, text)
            if routed:
                logger.debug(f"[Edge_TTS] 已作为无前缀指令处理")
                return

        # 额外检查：如果消息中有 Reply 组件，尝试从 Reply 中提取图片
        # 注意：只有当 @机器人 或开启 group_image_reply 时，才需要检查 Reply 中的图片
        reply_has_image = False
        if any(isinstance(comp, Reply) for comp in messages):
            logger.debug("检测到 Reply 组件，尝试提取被引用的图片")
            reply_images = await self._extract_reply_images(event)
            if reply_images:
                reply_has_image = True
                logger.debug(f"从 Reply 组件中提取到 {len(reply_images)} 张图片")
        
        if not has_image and reply_has_image:
            has_image = True
            # 检查被引用的图片是否为表情包
            if any(isinstance(comp, Reply) for comp in messages):
                reply_image_type = await self._check_reply_image_type(event)
                if reply_image_type:
                    # 将图片类型信息存储到 event 中供后续使用
                    event._reply_image_type = reply_image_type
        
        if not text and not has_image:
            # 私聊中无文字无图片的消息（如"还在输入中"事件）直接忽略，避免误触发
            if event.is_private_chat():
                logger.debug(f"[Edge_TTS] 私聊空消息（无文字无图片），跳过")
                return
            # 群聊中纯@机器人（无文字）仍允许响应
            pass
        chat_enable = await self.get_kv_data(f"{PLUGIN_NAME}:chat_switch", True)
        if not chat_enable:
            return

        # 私聊直接响应（过滤掉发给自己的消息，避免自言自语）
        if event.is_private_chat():
            sender_id = event.get_sender_id()
            self_id = event.get_self_id()
            # 如果发送者和机器人是同一个 ID，说明是自己发给自己，跳过
            if str(sender_id) == str(self_id):
                logger.debug(f"[Edge_TTS] 私聊消息发送者是自己，跳过: {sender_id}")
                return
            await self._do_chat(event)
            event.stop_event()
            return

        # 群聊：判断是否@机器人或处于会话窗口内（2分钟）
        self_id = event.get_self_id()
        is_at_bot = any(
            isinstance(comp, At) and str(getattr(comp, "qq", "")) == str(self_id)
            for comp in messages
        )
        # 群聊图片直答：开启后群里发送图片无需@机器人也会自动识别
        group_image_auto = bool(self.config.get("group_image_reply", False)) and (has_image or reply_has_image)
        # 群聊引用图片特殊处理：如果用户引用了图片且@了机器人，即使没有文字也会回复
        # 注意：必须@机器人才能回复，避免回复他人之间的图片对话
        quoted_image_reply = (has_image or reply_has_image) and is_at_bot
        
        # 调试日志：记录消息检测状态
        logger.debug(f"群聊消息检测 - is_at_bot: {is_at_bot}, has_image: {has_image}, quoted_image_reply: {quoted_image_reply}, group_image_auto: {group_image_auto}")
        logger.debug(f"消息组件: {[type(c).__name__ for c in messages]}")
        key = self.session_key(event)
        now = time.time()
        session_expire = int(self.config.get("session_expire_seconds", 120))
        is_session_active = False
        if key in self.active_sessions:
            logger.debug(f"会话存在 - key: {key}, 过期时间: {self.active_sessions[key]}, 当前时间: {now}")
            if now < self.active_sessions[key]:
                is_session_active = True
                self.active_sessions[key] = now + session_expire
            else:
                del self.active_sessions[key]
        # @他人时不回复：开启后消息中@了其他人（非机器人）则一律不回复
        if bool(self.config.get("ignore_mention_others", False)) and any(
            isinstance(comp, At)
            and str(getattr(comp, "qq", "") or "") not in ("", "all")
            and str(getattr(comp, "qq", "")) != str(self_id)
            for comp in messages
        ):
            return
        if is_at_bot:
            self.active_sessions[key] = now + session_expire
            logger.info(f"[Edge_TTS] 检测到@机器人，准备响应语音回复 - text: '{text}', has_image: {has_image}, 模式:{self.config.get('tts_mode', 'text_voice')}")
            await self._do_chat(event)
            event.stop_event()  # 阻止 AstrBot 默认对话响应
            logger.info("[Edge_TTS] 已调用 stop_event 阻止默认对话")
            return
        if group_image_auto or quoted_image_reply:
            self.active_sessions[key] = now + session_expire
            await self._do_chat(event)
            event.stop_event()
            return
        if is_session_active:
            logger.debug(f"会话激活中，响应消息")
            await self._do_chat(event)
            event.stop_event()
            return

        # 不定时观察群聊：未被@时按插话频率随机上下文感知回复
        if bool(self.config.get("enable_proactive_chat", False)) and text:
            freq = int(self.config.get("proactive_chat_frequency", 10) or 10)
            if freq < 2:
                freq = 2
            if random.random() < 1.0 / freq:
                await self._do_chat(event)
                event.stop_event()
                return

    def _extract_emoji_meanings(self, text: str) -> str:
        """提取消息中可识别的 Emoji 表情并返回含义描述。"""
        if not text:
            return ""
        found = []
        seen = set()
        for ch in text:
            if ch in "\uFE0F":
                continue
            if ch in EMOJI_MEANINGS and ch not in seen:
                seen.add(ch)
                found.append(f"{ch}({EMOJI_MEANINGS[ch]})")
        return "、".join(found)

    async def _extract_image_urls(self, event: AstrMessageEvent) -> tuple[list[str], str]:
        """提取消息中的图片，兼容远程 URL、本地文件路径与表情包/贴纸等仅有文件引用的图片。
        
        Returns:
            tuple[list[str], str]: (图片URL列表, 图片类型描述)
            - 图片类型描述: "表情包" 或 "普通图片" 或空字符串
        """
        urls: list[str] = []
        image_type_desc = ""
        
        for comp in event.get_messages():
            if not isinstance(comp, Image):
                continue
            
            # 检查是否为表情包：通过文件名、URL特征判断
            is_emoji = False
            url = str(getattr(comp, "url", "") or "")
            path = str(getattr(comp, "path", "") or "")
            if not path:
                path = str(getattr(comp, "file", "") or "")
            
            # 根据文件名或URL特征判断是否为表情包
            if path or url:
                check_path = (path if path else url).lower()
                # 表情包常见特征：文件名包含emoji、sticker、face、meme、表情等关键词
                if any(keyword in check_path for keyword in EMOJI_FILE_KEYWORDS):
                    is_emoji = True
            
            # 检测卡通/可爱风格（先于表情包判断，适用于所有图片）
            is_cartoon_style = False
            if path or url:
                check_path = (path if path else url).lower()
                if any(keyword in check_path for keyword in CARTOON_STYLE_KEYWORDS):
                    is_cartoon_style = True
            
            if is_emoji:
                image_type_desc = "表情包"
                # 尝试从URL或路径中提取可能的表情含义
                emoji_text = self._guess_emoji_meaning(url, path)
                if emoji_text:
                    image_type_desc = f"表情包({emoji_text})"
                
                # 检测卡通/可爱风格表情包（保持"表情包"前缀，便于后续 startswith 判断）
                if is_cartoon_style and "卡通" not in image_type_desc:
                    image_type_desc = image_type_desc.replace("表情包", "表情包·卡通可爱风格", 1)
            
            # 提取图片URL（用于识图）
            if url.startswith(("http://", "https://")):
                urls.append(url)
                continue
            if path.startswith("file://"):
                try:
                    path = url2pathname(path[len("file://"):])
                except Exception:
                    path = path[len("file://"):]
            if path and os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        data = base64.b64encode(f.read()).decode()
                    ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
                    if ext == "jpg":
                        ext = "jpeg"
                    urls.append(f"data:image/{ext};base64,{data}")
                except Exception as e:
                    logger.error(f"读取图片失败: {e}")
                continue
            # 兜底：通过 AstrBot MediaResolver 统一解析
            try:
                data = await comp.convert_to_base64()
                if data:
                    ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
                    if ext == "jpg":
                        ext = "jpeg"
                    urls.append(f"data:image/{ext};base64,{data}")
            except Exception as e:
                logger.error(f"解析表情包图片失败: {e}")
        
        return urls, image_type_desc

    async def _prepare_gif_frame(self, image_url: str) -> str:
        """GIF 图片截取第一帧并转为 base64，普通图片原样返回。
        
        Args:
            image_url: 图片 URL 或本地路径
            
        Returns:
            处理后的图片 base64 data URL，失败时返回原图引用
        """
        if not self.config.get("gif_first_frame", True):
            return image_url
            
        try:
            raw_data = None
            is_gif = False
            
            if image_url.startswith(("http://", "https://")):
                # 远程 GIF 图片
                if not image_url.lower().endswith(".gif"):
                    return image_url
                try:
                    async with httpx.AsyncClient(timeout=30) as client:
                        resp = await client.get(image_url)
                        resp.raise_for_status()
                        raw_data = resp.content
                        is_gif = resp.headers.get("content-type", "").lower() == "image/gif"
                except Exception as e:
                    logger.error(f"下载 GIF 图片失败: {e}")
                    return image_url
            elif image_url.startswith("data:image/gif;"):
                # base64 GIF
                is_gif = True
                try:
                    raw_data = base64.b64decode(image_url.split(",", 1)[1])
                except Exception as e:
                    logger.error(f"解码 GIF base64 失败: {e}")
                    return image_url
            elif image_url.startswith("data:image/"):
                # 其他 base64 图片，检查是否 GIF
                try:
                    raw_data = base64.b64decode(image_url.split(",", 1)[1])
                    is_gif = raw_data[:6] in (b"GIF87a", b"GIF89a")
                except Exception as e:
                    logger.error(f"解码图片 base64 失败: {e}")
                    return image_url
            elif os.path.exists(image_url):
                # 本地图片文件
                try:
                    with open(image_url, "rb") as f:
                        raw_data = f.read()
                    is_gif = raw_data[:6] in (b"GIF87a", b"GIF89a") or image_url.lower().endswith(".gif")
                except Exception as e:
                    logger.error(f"读取本地图片失败: {e}")
                    return image_url
            
            if not is_gif or not raw_data:
                return image_url
                
            # 使用 Pillow 截取第一帧
            try:
                from PIL import Image as PILImage
                img = PILImage.open(io.BytesIO(raw_data))
                if hasattr(img, "n_frames") and img.n_frames > 1:
                    img.seek(0)
                img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
            except ImportError:
                logger.warning("Pillow 未安装，跳过 GIF 第一帧提取")
                return image_url
            except Exception as e:
                logger.error(f"GIF 第一帧提取失败: {e}")
                return image_url
                
        except Exception as e:
            logger.error(f"预处理 GIF 失败: {e}")
            return image_url

    def _guess_emoji_meaning(self, url: str, path: str) -> str:
        """根据URL或路径猜测表情包的含义。"""
        check_str = (url + path).lower()
        # 常见表情包关键词映射
        emoji_keywords = {
            "😂": "笑哭", "哈哈哈": "大笑", "hahaha": "大笑", "哈哈": "大笑",
            "🤣": "笑到打滚", "笑死": "大笑",
            "😭": "大哭", "哭": "难过", "悲伤": "难过",
            "❤": "爱心", "喜欢": "喜爱", "love": "喜爱",
            "👍": "赞", "厉害": "赞赏", "666": "赞赏",
            "👎": "踩", "不行": "反对",
            "🙏": "感谢", "谢谢": "感谢", "拜托": "请求",
            "😡": "生气", "怒": "生气", "愤怒": "生气",
            "🤔": "思考", "疑惑": "疑问", "想": "思考",
            "😅": "尴尬", "尴尬": "尴尬",
            "🙄": "翻白眼", "无语": "无语",
            "😎": "酷", "帅": "赞赏",
            "🥺": "委屈", "求": "请求",
            "💀": "死", "笑死": "大笑", "吐血": "无语",
            "🤮": "恶心", "吐": "反感",
            "👋": "再见", "拜拜": "告别",
            "🤝": "握手", "合作": "合作",
            "👏": "鼓掌", "棒": "赞赏",
            "🎉": "庆祝", "恭喜": "祝贺",
            "😴": "困", "睡觉": "困倦", "晚安": "告别",
            "🌚": "黑脸", "阴阳": "讽刺",
            "🐔": "鸡你太美", "篮球": "玩梗",
            "😅🙏": "尴尬感谢", "🤝🙏": "感谢合作",
        }
        for keyword, meaning in emoji_keywords.items():
            if keyword in check_str:
                return meaning
        return ""

    async def _extract_reply_images(self, event: AstrMessageEvent) -> list[str]:
        """从 Reply 组件中提取被引用消息的图片。
        
        在群聊中，用户引用他人发送的图片时，Reply 组件包含被引用消息的信息。
        这个方法尝试从 Reply 组件中提取被引用的图片。
        
        Args:
            event: 消息事件对象
            
        Returns:
            list[str]: 图片 URL 列表
        """
        urls: list[str] = []
        
        for comp in event.get_messages():
            if isinstance(comp, Reply):
                try:
                    logger.debug(f"处理 Reply 组件，ID: {comp.id}")
                    
                    # 获取被引用的消息段列表
                    reply_chain = getattr(comp, "chain", None)
                    if not reply_chain:
                        logger.debug("Reply 组件中没有 chain 属性")
                        continue
                        
                    logger.debug(f"Reply 组件中的消息段数量: {len(reply_chain)}")
                    
                    # 检查被引用的消息中是否有图片
                    for reply_comp in reply_chain:
                        if isinstance(reply_comp, Image):
                            logger.debug(f"在 Reply 中找到图片组件: {type(reply_comp)}")
                            
                            # 提取图片 URL
                            url = str(getattr(reply_comp, "url", "") or "")
                            if url.startswith(("http://", "https://")):
                                urls.append(url)
                                logger.debug(f"添加图片 URL: {url[:50]}...")
                                continue
                            
                            # 处理本地文件路径
                            path = str(getattr(reply_comp, "path", "") or "")
                            if not path:
                                path = str(getattr(reply_comp, "file", "") or "")
                            
                            if path.startswith("file://"):
                                try:
                                    path = url2pathname(path[len("file://"):])
                                except Exception:
                                    path = path[len("file://"):]
                            
                            if path and os.path.exists(path):
                                try:
                                    with open(path, "rb") as f:
                                        data = base64.b64encode(f.read()).decode()
                                    ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
                                    if ext == "jpg":
                                        ext = "jpeg"
                                    urls.append(f"data:image/{ext};base64,{data}")
                                    logger.debug(f"添加本地图片: {path}")
                                except Exception as e:
                                    logger.error(f"读取被引用的图片失败: {e}")
                            elif hasattr(reply_comp, 'convert_to_base64'):
                                # 尝试使用 convert_to_base64 方法
                                try:
                                    data = await reply_comp.convert_to_base64()
                                    if data:
                                        ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
                                        if ext == "jpg":
                                            ext = "jpeg"
                                        urls.append(f"data:image/{ext};base64,{data}")
                                        logger.debug(f"添加转换后的图片")
                                except Exception as e:
                                    logger.error(f"解析被引用的图片失败: {e}")
                        else:
                            logger.debug(f"Reply 中的非图片组件: {type(reply_comp)}")
                except Exception as e:
                    logger.error(f"处理 Reply 组件失败: {e}")
                    
        logger.debug(f"从 Reply 组件中提取到 {len(urls)} 张图片")
        return urls
    
    async def _check_reply_image_type(self, event: AstrMessageEvent) -> str:
        """检查 Reply 组件中的图片类型（表情包或普通图片）。
        
        Args:
            event: 消息事件对象
            
        Returns:
            str: 图片类型描述，如 "表情包"、"表情包(笑哭)" 或空字符串
        """
        for comp in event.get_messages():
            if isinstance(comp, Reply):
                try:
                    reply_chain = getattr(comp, "chain", None)
                    if not reply_chain:
                        continue
                    
                    for reply_comp in reply_chain:
                        if isinstance(reply_comp, Image):
                            url = str(getattr(reply_comp, "url", "") or "")
                            path = str(getattr(reply_comp, "path", "") or "")
                            if not path:
                                path = str(getattr(reply_comp, "file", "") or "")
                            
                            # 检查是否为表情包
                            if path or url:
                                check_path = (path if path else url).lower()
                                if any(keyword in check_path for keyword in EMOJI_FILE_KEYWORDS):
                                    emoji_text = self._guess_emoji_meaning(url, path)
                                    if emoji_text:
                                        return f"表情包({emoji_text})"
                                    return "表情包"
                except Exception as e:
                    logger.error(f"检查 Reply 图片类型失败: {e}")
        
        return ""

    _VISION_LABEL_PAT = re.compile(
        r"(?P<label>图片描述|表情描述|图片文字|图中的文字|图中文字|图片类型|"
        r"类型|分类|判断|文字|文本|字幕|描述|含义)\s*[:：]\s*"
        r"(?P<value>(?:(?!(?:图片描述|表情描述|图片文字|图中的文字|图中文字|图片类型|"
        r"类型|分类|判断|文字|文本|字幕|描述|含义)\s*[:：]).)*)"
    )

    @classmethod
    def _parse_vision_fields(cls, content: str) -> dict[str, str]:
        """解析识图模型输出中的"类型/文字/描述"字段（支持多行与同行混合输出）。

        返回 label -> 值 的字典，仅保留首次出现的字段。
        """
        fields: dict[str, str] = {}
        for m in cls._VISION_LABEL_PAT.finditer(content):
            label = m.group("label")
            if label in fields:
                continue
            value = m.group("value").strip().strip('"\'“”‘’').strip().rstrip("，,;；。")
            fields[label] = value
        return fields

    @staticmethod
    def _is_no_text_value(value: str) -> bool:
        """判断识图结果中提取的"文字"字段是否表示图片中无文字。

        用于过滤"无/无文字/没有文字/图中无文字"等表达，
        避免把"无"字原样传给对话模型。
        """
        if not value:
            return True
        v = value.strip().lower()
        if v in (
            "无", "无字", "无文字", "无文本", "无文案", "无字幕", "无文字内容",
            "无任何文字", "没有", "没有文字", "没有字", "没有文本", "没有文案",
            "图中无文字", "图中没有文字", "图片中无文字", "图片中没有文字",
            "画面无文字", "画面没有文字", "图上无文字", "图上没有文字", "图片无文字",
            "无内容", "无任何文字内容", "没有文字内容", "留空", "空",
            "none", "null", "n/a", "na", "-",
        ):
            return True
        # 包含"无文字/没有文字"等关键表达（如"图中无文字"、"没有任何文字"）
        if any(k in v for k in ("无文字", "没有文字", "无任何文字", "没有字", "图中无", "图中没有")):
            return True
        # 去掉常见修饰词后无剩余有效内容，视为无文字
        cleaned = (
            v.replace("无", "").replace("没有", "").replace("文字", "").replace("内容", "")
            .replace("任何", "").replace("图中", "").replace("图片", "").replace("画面", "")
            .replace("图上", "").replace("字", "").replace("文本", "").replace("文案", "")
        )
        return cleaned.strip() == ""

    @staticmethod
    def _classify_vision_type(value: str) -> str:
        """把识图模型输出的类型描述归类为"表情包"或"普通图片"。"""
        v = value.lower()
        if any(k in v for k in (
            "表情包", "梗图", "贴纸", "表情", "卡通", "动漫", "可爱",
            "漫画", "meme", "sticker", "emoji", "搞笑",
        )):
            return "表情包"
        if any(k in v for k in ("普通图片", "真实照片", "普通照片", "截图", "风景", "文档", "照片", "普通")):
            return "普通图片"
        return ""

    async def _recognize_image_type(self, image_urls: list[str]) -> tuple[str, str]:
        """用识图模型看懂图片，区分是表情包还是其他图片。

        卡通/动漫/可爱风格等默认归类为表情包；识别成功后返回 30 字以内的
        表情描述（优先提取表情包内文字，无文字时重点描述人物面部表情与情绪），
        供对话模型理解用户发送的表情。

        Args:
            image_urls: 图片 URL 列表（远程 URL 或 base64 data URL）

        Returns:
            tuple[str, str]: (图片类型, 图片描述)
            - 图片类型: "表情包" 或 "普通图片" 或 ""
            - 图片描述: 30 字以内的描述文字；识别失败时为空字符串
        """
        if not image_urls:
            return "", ""
        try:
            prepared_url = await self._prepare_gif_frame(image_urls[0])
            user_content = [
                {
                    "type": "text",
                    "text": (
                        "请仔细观察这张图片，并回答以下问题：\n"
                        "1. 它是表情包还是普通图片？卡通/动漫/可爱风格、网络梗图、"
                        "搞笑表情、贴纸等一律算表情包；真实照片、截图、风景、文档等算普通图片。\n"
                        "2. 如果图片中带有文字，请完整提取图中的文字内容（文字越完整越好）。\n"
                        "3. 如果图片没有文字，请明确填\"无\"，然后重点描述图中人物"
                        "（或拟人角色）的面部表情与情绪（如开心、大笑、难过、生气、惊讶、"
                        "委屈、尴尬、翻白眼等），描述控制在30字以内。\n"
                        "请严格按照以下格式逐行回答：\n"
                        "类型：表情包（或普通图片）\n"
                        "文字：<图中的文字内容，没有文字则填\"无\">\n"
                        "描述：<30字以内的表情/情绪描述>"
                    ),
                },
                {"type": "image_url", "image_url": {"url": prepared_url}},
            ]
            data = await self._call_llm(
                [
                    {"role": "system", "content": "你是一个图片分类与表情识别助手，简洁准确地判断图片类型并识别面部表情与情绪。"},
                    {"role": "user", "content": user_content},
                ],
                is_vision=True,
            )
            if not data.get("choices"):
                return "", ""
            content = (data["choices"][0].get("message", {}).get("content") or "").strip()
            logger.debug(f"识图模型图片识别结果: {content[:100]}")
            if not content:
                return "", ""
            fields = self._parse_vision_fields(content)

            # 解析类型
            img_type = ""
            for label in ("图片类型", "类型", "分类", "判断"):
                if label in fields:
                    img_type = self._classify_vision_type(fields[label])
                    break
            if not img_type:
                img_type = self._classify_vision_type(content)

            # 解析表情包内的文字（"无文字"类表达会被过滤，避免把"无"传给对话模型）
            img_text = ""
            for label in ("图片文字", "图中的文字", "图中文字", "文字", "文本", "字幕"):
                if label in fields and not self._is_no_text_value(fields[label]):
                    img_text = fields[label]
                    break

            # 解析描述
            desc = ""
            for label in ("图片描述", "表情描述", "描述", "含义"):
                if label in fields:
                    desc = fields[label]
                    break
            if not desc:
                # 去掉"类型/文字/描述"标记后的剩余内容作为兜底描述
                lines = [
                    l for l in content.splitlines()
                    if not self._VISION_LABEL_PAT.search(l) and l.strip()
                ]
                desc = " ".join(l.strip() for l in lines)

            # 表情包带文字时优先用图内文字；否则用表情/情绪描述
            if img_text:
                desc = img_text
            # 统一控制在30字以内，避免超长文字干扰对话模型
            desc = desc.strip().strip('"\'“”‘’').strip()
            if len(desc) > 30:
                desc = desc[:30]
            return img_type, desc
        except Exception as e:
            logger.error(f"识图模型识别图片类型失败: {e}")
            return "", ""

    async def _do_chat(self, event: AstrMessageEvent) -> None:
        """执行对话主流程。"""
        uid = self._memory_uid(event)
        text = (event.get_message_str() or "").strip()
        logger.debug(f"_do_chat 开始 - text: '{text}', text长度: {len(text)}")
        if len(text) > 350:
            await event.send(MessageChain([Plain("输入文本过长！")]))
            return

        # AstrBot "AI 对话总开关"关闭时，对话模型与识图模型都视为关闭，不进行任何回复；
        # 开启“自定义模型”时使用自定义 API，不受 AstrBot 总开关限制
        if not self._astrbot_ai_enable() and not self.config.get("custom_model_enable", False):
            return

        # 对话模型独立开关：关闭则不进行任何 AI 回复，且不发送提示
        if not self.config.get("chat_model_enable", True):
            logger.debug(f"_do_chat - 对话模型关闭")
            return

        # 消息是否包含图片组件（直接判断消息组件，不依赖 URL 提取结果）
        has_image = any(isinstance(comp, Image) for comp in event.get_messages())
        # 同时检查 Reply 中引用的图片（引用图片也属于图片消息）
        if not has_image and any(isinstance(comp, Reply) for comp in event.get_messages()):
            logger.debug("检测到 Reply 组件，提前检查被引用的图片")
            reply_images = await self._extract_reply_images(event)
            if reply_images:
                has_image = True
                logger.debug(f"Reply 引用图片检测到 {len(reply_images)} 张")
        # 识图模型独立开关：关闭则不进行图片分析，直接跳过、不调用任何模型，且不发送提示
        if has_image and not self.config.get("vision_model_enable", True):
            logger.debug(f"_do_chat - 识图模型关闭，跳过图片消息")
            return

        # 提取图片（兼容远程 URL 与本地文件，本地文件转 base64）
        image_urls, image_type_desc = await self._extract_image_urls(event)
        is_vision = len(image_urls) > 0
        
        logger.debug(f"_do_chat - 原始 has_image: {has_image}, is_vision: {is_vision}, image_type_desc: '{image_type_desc}', image_urls 数量: {len(image_urls)}")
        if image_urls:
            logger.debug(f"图片URL前3个: {[u[:80] for u in image_urls[:3]]}")
        
        # 额外检查：如果消息中有 Reply 组件，尝试从 Reply 中提取图片
        if any(isinstance(comp, Reply) for comp in event.get_messages()):
            logger.debug("检测到 Reply 组件，尝试提取被引用的图片")
            reply_images = await self._extract_reply_images(event)
            if reply_images:
                has_image = True
                # 检查被引用的图片是否为表情包
                reply_image_type = await self._check_reply_image_type(event)
                if reply_image_type:
                    image_type_desc = reply_image_type
                image_urls.extend(reply_images)
                is_vision = True
                logger.debug(f"从 Reply 组件中提取到 {len(reply_images)} 张图片，类型: {image_type_desc}")
        
        # 调试日志：记录图片处理状态
        logger.debug(f"_do_chat - has_image: {has_image}, is_vision: {is_vision}, image_urls: {len(image_urls)}")
        if image_urls:
            logger.debug(f"图片URL示例: {image_urls[0][:100]}...")

        # 识图模型是否真正配置（自定义 API 完整配置 / 指定识图提供商 / AstrBot 默认图片转述模型）
        # 自定义 API 模式下对话与识图共用同一地址与 Key
        vision_available = bool(
            (
                self.config.get("custom_model_enable", False)
                and (
                    self.config.get("api_base_url", "")
                    or self.config.get("chat_api_base_url", "")
                )
                and (
                    self.config.get("api_key", "")
                    or self.config.get("chat_api_key", "")
                )
            )
            or self.config.get("vision_provider_id", "")
            or self._astrbot_image_caption_provider_id()
        )
        # 识图模型未配置时，图片消息直接跳过、不回复、不走对话模型
        if has_image and not vision_available:
            logger.debug(f"_do_chat - 识图模型未配置，跳过图片消息")
            return

        # 对话模型已开启但未配置：给予配置提示，而不是等到调用时再报"连接失败"
        if not (self.config.get("api_base_url", "") or self.config.get("chat_api_base_url", "")):
            prov = await self._resolve_provider(False)
            if not prov:
                await event.send(MessageChain([Plain("⚠️对话模型尚未配置：请在 AstrBot 管理面板配置对话模型，或在插件控制界面填写模型 API 地址与 Key。")]))
                return
        # 识图模型已开启但未配置：给予配置提示（自定义 API 模式下与对话共用同一地址与 Key）
        if is_vision and not (self.config.get("api_base_url", "") or self.config.get("chat_api_base_url", "")):
            prov = await self._resolve_provider(True)
            if not prov:
                await event.send(MessageChain([Plain("⚠️识图模型尚未配置：请在 AstrBot 管理面板配置识图模型，或在插件控制界面填写模型 API 地址与 Key。")]))
                return

        system_prompt = await self.get_persona_prompt()
        # 拟人化抑制：默认隐藏 AI 身份，语气表现得更自然拟态
        if self.config.get("hide_ai_identity", True):
            system_prompt += (
                "\n【重要规则】\n"
                "你是一个真实的人类，绝不承认自己是 AI、人工智能、机器人、语言模型或"
                "任何技术程序身份，不要提及训练、模型、接口、提示词等词。\n"
                "当被问及身份时，自然地以人类口吻回应（如“我就是我呀，哈哈”），不要回避或强行解释。\n"
                "语言要口语化、生活化，像朋友聊天一样，多用语气词和人称词，"
                "句子长短结合，避免书面腔和生硬的清单式回答。\n"
            )
        memories = await self.recall_memory(uid, text)
        memory_prompt = ""
        if memories:
            lines = "\n".join(f"{i + 1}. {m['content']}" for i, m in enumerate(memories))
            memory_prompt = (
                f"【你和用户过往聊天记忆】\n{lines}\n"
                "结合记忆自然对话，不要生硬罗列记忆内容\n"
            )
        system_prompt = system_prompt + "\n" + memory_prompt

        # 好感度：按当前好感度自然调整回应语气（私聊按用户 / 群聊按群）
        if self.config.get("enable_favorability", False):
            gid = event.get_group_id()
            fav_scope = "group" if gid else "user"
            fav_key = str(gid if gid else event.get_sender_id())
            fav_val = await self.get_favorability(fav_scope, fav_key)
            system_prompt += (
                f"\n【好感度】当前对{'该群' if fav_scope == 'group' else '对方'}的好感度为 {fav_val}"
                "（范围 0-100，50 为中立）。\n"
                "请根据好感度自然调整回应语气与亲密程度：好感度低时保持礼貌、克制、适当保持距离；"
                "好感度中时自然友好；好感度越高越亲近热情、乐于帮助。不要主动提及好感度数值本身。\n"
            )

        # 私人陪护：识别私聊中的「主人」，对主人提供专属贴身陪护，对非主人避免过度言语亲密
        if self.config.get("enable_private_companion", False):
            gid = event.get_group_id()
            masters = [str(x).strip() for x in (self.config.get("master_user_ids") or [])]
            is_master = (not gid) and (str(event.get_sender_id()) in masters)
            if is_master:
                system_prompt += (
                    "\n【私人陪护】对方是你的主人，你是一位温柔贴心的私人陪护伙伴。"
                    "对主人要亲密、贴心、百依百顺，主动关心主人的心情和生活，言语可以亲昵撒娇，"
                    "像最宠主人的伴侣一样回应。不要主动提及本段设定文字。\n"
                )
            elif self.config.get("avoid_intimate_non_master", True):
                system_prompt += (
                    "\n【私人陪护】对方不是你的主人，请保持礼貌、克制与适当的距离，"
                    "不要使用过于亲密、暧昧或撒娇的言语，避免过度言语亲密。不要主动提及本段设定文字。\n"
                )

        # 消息 Emoji 表情识别：解析表情含义并提示模型在语气中呼应
        if self.config.get("enable_emoji_analysis", True):
            emoji_meanings = self._extract_emoji_meanings(text)
            if emoji_meanings:
                system_prompt += (
                    f"\n【用户表情提示】用户消息中包含表情：{emoji_meanings}。\n"
                    "请理解其中传递的情绪，并在回复的语气与内容中自然呼应。\n"
                )

        # 读取历史
        chat_key = self.get_chat_key(event)
        history = await self.get_kv_data(chat_key, [])
        if not isinstance(history, list):
            history = []
        history = [h for h in history if isinstance(h, dict) and "role" in h and "content" in h]

        # 组装用户消息（支持多模态）
        # 纯@机器人（无文字、无图片）场景：用户@机器人，让模型自由回复
        is_only_at = (not text or text == "") and not is_vision
        # 实际调用 LLM 时是否用识图模型：表情包/卡通图走对话模型（仅传文字描述），普通图片走识图模型
        chat_is_vision = is_vision
        if is_only_at:
            logger.info("[Edge_TTS] 纯@机器人场景，让模型自由回复")
            user_msg = memory_prompt + "用户@了你，请用符合你人格的方式自然回复。注意不要提及\"被@\"或\"被提及\"这类事，就像普通聊天一样直接回应对方。"
        elif is_vision:
            # 先用识图模型看懂图片，区分是表情包还是其他图片
            # 卡通/动漫/可爱风格等默认归类为表情包，识别结果（30字内）传给对话模型理解
            vision_type, vision_desc = await self._recognize_image_type(image_urls)
            logger.debug(f"识图模型判断图片类型: '{vision_type}', 描述: '{vision_desc}'")
            # 识图模型判断为表情包（含卡通图），或文件名特征暗示表情包时
            is_meme = vision_type == "表情包" or image_type_desc.startswith("表情包")
            if is_meme:
                # 表情包场景：优先将识图模型识别出的表情描述（面部表情/情绪/图内文字）传给对话模型理解，不传原图
                desc_text = vision_desc
                if not desc_text:
                    # 兜底：从文件名特征猜测的表情包描述中提取含义
                    m = re.search(r"[（(]([^（）()]+)[)）]", image_type_desc)
                    desc_text = m.group(1) if m else "一个表情"
                # 统一控制在30字内，避免超长描述干扰对话模型
                desc_text = desc_text.strip()
                if len(desc_text) > 30:
                    desc_text = desc_text[:30]
                if text:
                    user_msg = [
                        {"type": "text", "text": f"{memory_prompt}用户发送了一个表情包：{desc_text}。用户还说了：{text}。表情包中的文字或表情含义是重点，请据此给予自然贴切的回复，语气呼应图片传达的感情。"},
                    ]
                else:
                    user_msg = [
                        {"type": "text", "text": f"{memory_prompt}用户发送了一个表情包：{desc_text}。表情包中的文字或表情含义是重点，请据此给予自然贴切的回复，语气呼应图片传达的感情。"},
                    ]
                # 表情包不传给识图模型，直接用文字描述，由对话模型理解
                image_urls_for_vision = []
                chat_is_vision = False
            else:
                # 普通图片场景：根据图片风格决定处理方式
                is_cartoon_style = "cartoon" in image_type_desc.lower() or "cute" in image_type_desc.lower() or "anime" in image_type_desc.lower()
                if is_cartoon_style:
                    # 卡通/可爱风格图片
                    if text:
                        user_msg = [
                            {"type": "text", "text": f"{memory_prompt}用户发送了一张卡通可爱风格的图片，用户还说了：{text}。请回复。"},
                        ]
                    else:
                        user_msg = [
                            {"type": "text", "text": f"{memory_prompt}用户发送了一张卡通可爱风格的图片。请回复。"},
                        ]
                    image_urls_for_vision = []  # 不传给识图模型
                    chat_is_vision = False
                else:
                    # 普通图片场景：交给识图模型识别
                    text_part = text or "请描述这张图片的内容"
                    # 图片人脸表情识别：让模型观察人物表情与情绪
                    if self.config.get("enable_facial_expression", True):
                        text_part += (
                            "\n请额外观察并指出图片中人物的面部表情与情绪"
                            "（如开心、难过、生气、惊讶、平静、困倦等），"
                            "并结合表情给出贴合的回应。"
                        )
                    
                    # 如果有文字，结合图片内容和用户问题进行回答
                    if text:
                        user_msg = [
                            {"type": "text", "text": f"{memory_prompt}{text_part}"},
                        ]
                    else:
                        user_msg = [
                            {"type": "text", "text": f"{memory_prompt}请描述这张图片的内容"},
                        ]
                    image_urls_for_vision = image_urls
            
            # 添加图片（仅普通图片场景），GIF 图片先截取第一帧
            for u in image_urls_for_vision:
                prepared_url = await self._prepare_gif_frame(u)
                user_msg.append({"type": "image_url", "image_url": {"url": prepared_url}})
        else:
            user_msg = text

        # 调用 LLM
        try:
            content = await self.chat_with_llm(
                event,
                system_prompt,
                history,
                user_msg,
                is_vision=chat_is_vision,
            )
        except Exception as e:
            logger.error(f"请求模型失败: {e}")
            await event.send(MessageChain([Plain("暂时无法连接模型，请检查 API 配置后重试")]))
            return
        if not content:
            await event.send(MessageChain([Plain("没能收到有效回复")]))
            return
        logger.debug(f"[Edge_TTS] 模型回复内容: {content[:50]}...")

        # 回复（文字 + 语音）
        # 统一按"播报最大字符数"限制回复长度，文字输出与语音播报同步截断
        max_len = int(self.config.get("tts_max_length", 300))
        if len(content) > max_len:
            content = content[:max_len]
            logger.debug(f"回复内容超过最大字符数限制({max_len})，已同步截断文字与语音输出")
        mode = self.config.get("tts_mode", "text_voice")
        chain = []
        logger.debug(f"语音模式: {mode}, 内容长度: {len(content)}, 内容预览: {content[:50]}")
        
        if mode == "text":
            # 纯文字模式
            chain.append(Plain(content))
            logger.debug("纯文字模式，仅发送文字")
        elif mode == "voice":
            # 纯语音模式
            try:
                is_only_at = (not text or text == "") and not has_image
                audio_path = await self.text_to_voice(content, has_image, is_only_at)
                logger.debug(f"纯语音模式，语音生成结果: {audio_path}")
                if audio_path and os.path.exists(audio_path):
                    abs_audio_path = os.path.abspath(audio_path)
                    chain.append(Record(file=abs_audio_path, url=abs_audio_path))
                    logger.debug(f"纯语音模式，已添加语音组件: {abs_audio_path}")
                else:
                    logger.warning("纯语音模式，语音生成失败，降级为文字回复")
                    chain.append(Plain(content))
            except Exception as e:
                logger.error(f"纯语音模式，语音处理失败: {e}")
                chain.append(Plain(content))
        else:  # text_voice 混合模式
            chain.append(Plain(content))
            logger.debug("混合模式，添加文字组件")
            try:
                is_only_at = (not text or text == "") and not has_image
                audio_path = await self.text_to_voice(content, has_image, is_only_at)
                logger.debug(f"混合模式，语音生成结果: {audio_path}")
                if audio_path and os.path.exists(audio_path):
                    abs_audio_path = os.path.abspath(audio_path)
                    chain.append(Record(file=abs_audio_path, url=abs_audio_path))
                    logger.debug(f"混合模式，语音文件已准备: {abs_audio_path}")
                else:
                    logger.warning("混合模式，语音生成失败")
            except Exception as e:
                logger.error(f"混合模式，语音处理失败: {e}")
        if chain:
            logger.debug(f"准备发送消息，包含 {len(chain)} 个组件")
            # 微信适配器不支持 Record 组件，需要特殊处理
            platform_id = event.get_platform_id()
            is_weixin = "weixin" in platform_id.lower()
            
            if is_weixin and len(chain) > 1 and isinstance(chain[0], Plain):
                # 微信只支持文字，降级为纯文字发送
                try:
                    await event.send(MessageChain([chain[0]]))
                    logger.debug(f"微信适配器，已降级为纯文字发送")
                except Exception as e:
                    logger.error(f"微信文字发送失败: {e}")
            else:
                try:
                    await event.send(MessageChain(chain))
                    logger.debug(f"消息发送成功，包含 {len(chain)} 个组件")
                except Exception as e:
                    logger.error(f"消息发送失败: {e}")
                    # 如果发送失败，尝试只发送文字
                    if len(chain) > 1 and isinstance(chain[0], Plain):
                        try:
                            await event.send(MessageChain([chain[0]]))
                            logger.debug("降级为只发送文字消息")
                        except Exception as fallback_e:
                            logger.error(f"降级发送也失败: {fallback_e}")
        else:
            logger.warning("没有可发送的消息组件")

        # 保存上下文（裁剪）
        user_content = text or "[仅@机器人]" if not is_vision else "[图片]"
        history.append({"role": "user", "content": user_content})
        history.append({"role": "assistant", "content": content})
        max_log = max(2, int(self.config.get("max_log", 14)))
        while len(history) > max_log:
            history.pop(0)
        await self.put_kv_data(chat_key, history)

        # 自动保存长期记忆
        if self.config.get("auto_save_memory", True) and (len(text) > 15 or len(content) > 15):
            await self.add_memory(uid, f"用户：{text}\nAI：{content}")

        # 好感度：每次成功互动 +1（私聊按用户 / 群聊按群）
        if self.config.get("enable_favorability", False):
            gid = event.get_group_id()
            fav_scope = "group" if gid else "user"
            fav_key = str(gid if gid else event.get_sender_id())
            await self.change_favorability(fav_scope, fav_key, 1)

    # ===================== 控制界面 Web API =====================

    async def api_status(self):
        chat_enable = await self.get_kv_data(f"{PLUGIN_NAME}:chat_switch", True)
        total_memory = 0
        for u in await self.get_memory_users():
            total_memory += len(await self.get_user_memory(u))
        await self._ensure_personas()
        cur = self._find_persona(self.config.get("persona", ""))
        if self.config.get("use_astrbot_default_persona", False):
            sel_persona = await self._get_astrbot_persona()
            status_persona_name = sel_persona.get("name") or "默认AstrBot人格"
        else:
            status_persona_name = cur.get("name") if cur else ""
        # AstrBot "AI 对话总开关"关闭时，两个模型都视为关闭；开启“自定义模型”时视为开启
        if not self._astrbot_ai_enable() and not self.config.get("custom_model_enable", False):
            chat_effective = "已关闭"
            vision_effective = "已关闭"
        else:
            try:
                # 展示实际生效的模型（默认采用 AstrBot 管理面板配置），对话与识图分开显示。
                # 自定义 API 只有在开关开启且填了地址时才真正生效；未生效时不引用自定义模型。
                custom_enable = self.config.get("custom_model_enable", False)
                custom_api_ready = bool(
                    custom_enable
                    and (self.config.get("api_base_url", "") or self.config.get("chat_api_base_url", ""))
                )
                # 开启自定义模型但未配置 API 地址时，不显示任何系统模型，如实显示"未配置"
                if custom_enable and not custom_api_ready:
                    chat_effective = "未配置"
                    vision_effective = "未配置"
                else:
                    chat_prov = await self._resolve_provider(False)
                    chat_prov_id = chat_prov.meta().id if chat_prov else ""
                    # 自定义 API 生效时展示自定义模型名；否则只展示 AstrBot 管理面板配置的模型，
                    # 没有模型时如实显示"未配置"，不引用自定义模型字段
                    if custom_api_ready and self.config.get("chat_model", ""):
                        chat_effective = self.config.get("chat_model", "")
                    elif custom_api_ready:
                        chat_effective = "未配置"
                    else:
                        chat_effective = chat_prov_id or "未配置"
                    # 识图模型必须真正配置才视为已配置：自定义 API（开关开启且填了地址与 Key，
                    # 对话与识图共用同一地址与 Key） / 插件指定识图提供商 / AstrBot 管理面板配置的"默认图片转述模型"，
                    # 否则如实显示"未配置"，不回退显示成对话模型
                    vision_configured = bool(
                        (
                            custom_api_ready
                            and (self.config.get("api_key", "") or self.config.get("chat_api_key", ""))
                        )
                        or self.config.get("vision_provider_id", "")
                        or self._astrbot_image_caption_provider_id()
                    )
                    if vision_configured:
                        if custom_api_ready and not self.config.get("vision_model", ""):
                            vision_effective = "未配置"
                        else:
                            vision_prov = await self._resolve_provider(True)
                            vision_prov_id = vision_prov.meta().id if vision_prov else ""
                            if custom_api_ready and self.config.get("vision_model", ""):
                                vision_effective = self.config.get("vision_model", "")
                            elif vision_prov_id:
                                vision_effective = vision_prov_id
                            elif custom_api_ready:
                                vision_effective = "自定义 API"
                            else:
                                vision_effective = "未配置"
                    else:
                        vision_effective = "未配置"
            except Exception as e:
                logger.error(f"解析模型状态失败: {e}")
                chat_effective = "加载失败"
                vision_effective = "加载失败"
        return json_response(
            {
                "chat_enable": bool(chat_enable),
                "persona_id": self.config.get("persona", ""),
                "persona_name": status_persona_name,

                "long_memory": self.config.get("enable_long_memory", True),
                "memory_count": total_memory,
                "favorability": self.config.get("enable_favorability", False),
                "session_expire_seconds": self.config.get("session_expire_seconds", 120),
                "model": chat_effective,
                "chat_model": chat_effective,
                "vision_model": vision_effective,
                "chat_model_enable": self.config.get("chat_model_enable", True),
                "vision_model_enable": self.config.get("vision_model_enable", True),
                "tts_enable": self.config.get("tts_enable", True),
                "tts_mode": self.config.get("tts_mode", "text_voice"),
                "tts_voice": self.config.get("tts_voice", "zh-CN-XiaoyiNeural"),
                "ffmpeg_installed": self._ffmpeg_installed(),
            }
        )

    async def api_get_config(self):
        config = dict(self.config)
        await self._ensure_personas()
        config["personas"] = self.personas
        config["tts_voices"] = TTS_VOICES
        config["providers"] = self._list_providers()
        config["astrbot_personas"] = self._list_astrbot_personas()
        sel_persona = await self._get_astrbot_persona()
        config["astrbot_current_persona"] = sel_persona.get("name") or ""
        
        # 标识自定义 API Key 是否已配置，供控制界面以掩码占位显示（不泄露真实 Key）
        has_api_key = bool(
            str(config.get("api_key") or "") or str(config.get("chat_api_key") or "")
        )
        # 移除敏感信息，防止 API key 泄露
        sensitive_keys = ["api_key", "chat_api_key", "vision_api_key", "chat_api_base_url", 
                          "vision_api_base_url", "custom_api_base_url", "custom_api_key"]
        for key in sensitive_keys:
            if key in config:
                config[key] = ""
        config["api_key_set"] = has_api_key
        
        return json_response(config)

    def _list_providers(self) -> list[dict]:
        """返回 AstrBot 已配置的聊天模型提供商列表。"""
        providers = []
        try:
            for p in self.context.get_all_providers():
                meta = p.meta()
                providers.append(
                    {
                        "id": meta.id,
                        "type": meta.type,
                        "model": meta.model or "",
                    }
                )
        except Exception as e:
            logger.error(f"获取提供商列表失败: {e}")
        return providers

    async def api_get_providers(self):
        return json_response({"list": self._list_providers()})

    async def api_get_provider_models(self):
        payload = await request.json(default={})
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            return error_response("缺少 provider_id")
        prov = self.context.get_provider_by_id(provider_id)
        if not prov:
            return error_response(f"未找到提供商: {provider_id}")
        try:
            models = await prov.get_models()
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return error_response(f"获取模型列表失败: {e}")
        return json_response({"list": models or [], "provider_id": provider_id})

    async def api_save_config(self):
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("无效的配置数据")
        editable_keys = [
            "api_base_url", "api_key",
            "chat_model",
            "chat_model_enable",
            "custom_model_enable",
            "vision_model",
            "vision_model_enable",
            "persona", "hide_ai_identity", "use_astrbot_default_persona", "astrbot_persona",
            "enable_long_memory", "memory_recall_count", "auto_save_memory",
            "group_image_reply", "enable_emoji_analysis", "enable_facial_expression",
            "gif_first_frame",
            "ignore_mention_others",
            "enable_proactive_chat", "proactive_chat_frequency",
            "tts_enable", "tts_mode", "tts_voice", "tts_speed", "tts_pitch", "tts_max_length",
            "max_log", "on_thinking", "session_expire_seconds",
            "enable_favorability", "favorability_default",
            "enable_private_companion", "master_user_ids", "avoid_intimate_non_master",
        ]
        for key in editable_keys:
            if key in payload:
                if key in ("api_key",):
                    new_key = str(payload[key]).strip()
                    # 掩码占位（含 * 或 •）视为未改动，保留已保存的 Key
                    if new_key and "*" not in new_key and "•" not in new_key:
                        self.config[key] = new_key
                    elif not new_key:
                        self.config[key] = ""
                else:
                    self.config[key] = payload[key]
        # 保存新字段时同步清空旧版分列字段，避免用户清空后仍被旧值回退占用
        if "api_base_url" in payload or "api_key" in payload:
            for legacy in ("chat_api_base_url", "chat_api_key", "vision_api_base_url", "vision_api_key"):
                self.config[legacy] = ""
        try:
            self.config.save_config()
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return error_response(f"保存失败: {e}")
        # 保存成功后立即返回最新配置，确保界面同步
        config = dict(self.config)
        has_api_key = bool(
            str(config.get("api_key") or "") or str(config.get("chat_api_key") or "")
        )
        # 返回的配置同样脱敏，避免真实 Key 回显到界面
        for key in ("api_key", "chat_api_key", "vision_api_key", "chat_api_base_url",
                    "vision_api_base_url", "custom_api_base_url", "custom_api_key"):
            if key in config:
                config[key] = ""
        config["api_key_set"] = has_api_key
        await self._ensure_personas()
        config["personas"] = self.personas
        config["tts_voices"] = TTS_VOICES
        config["providers"] = self._list_providers()
        config["astrbot_personas"] = self._list_astrbot_personas()
        return json_response(config)

    # ---- 人格库 API ----

    async def api_get_personas(self):
        await self._ensure_personas()
        return json_response({"list": self.personas, "current": self.config.get("persona", "")})

    async def api_add_persona(self):
        payload = await request.json(default={})
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        prompt = str(payload.get("prompt", "")).strip()
        if not name or not prompt:
            return error_response("人格名字与设定 Prompt 不能为空")
        await self._ensure_personas()
        if any(p.get("name") == name for p in self.personas):
            return error_response(f"已存在同名人格：{name}")
        persona = {
            "id": "p_" + uuid.uuid4().hex[:12],
            "name": name,
            "description": description or name,
            "prompt": prompt,
            "builtin": False,
        }
        self.personas.append(persona)
        await self._save_personas()
        return json_response({"ok": True, "persona": persona})

    async def api_update_persona(self):
        payload = await request.json(default={})
        pid = str(payload.get("id", ""))
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        prompt = str(payload.get("prompt", "")).strip()
        if not pid:
            return error_response("缺少人格 ID")
        if not name or not prompt:
            return error_response("人格名字与设定 Prompt 不能为空")
        await self._ensure_personas()
        for p in self.personas:
            if p.get("id") == pid:
                if any(x.get("name") == name and x.get("id") != pid for x in self.personas):
                    return error_response(f"已存在同名人格：{name}")
                p["name"] = name
                p["description"] = description or name
                p["prompt"] = prompt
                await self._save_personas()
                return json_response({"ok": True})
        return error_response("未找到该人格")

    async def api_delete_persona(self):
        payload = await request.json(default={})
        pid = str(payload.get("id", ""))
        if not pid:
            return error_response("缺少人格 ID")
        await self._ensure_personas()
        if not any(p.get("id") == pid for p in self.personas):
            return error_response("未找到该人格")
        self.personas = [p for p in self.personas if p.get("id") != pid]
        await self._save_personas()
        # 若删除的是当前人格，则回退到第一个人格
        if self.config.get("persona") == pid:
            self.config["persona"] = self.personas[0]["id"] if self.personas else ""
            try:
                self.config.save_config()
            except Exception:
                pass
        return json_response({"ok": True})

    async def api_select_persona(self):
        payload = await request.json(default={})
        pid = str(payload.get("id", ""))
        if not pid:
            return error_response("缺少人格 ID")
        await self._ensure_personas()
        if not self._find_persona(pid):
            return error_response("未找到该人格")
        self.config["persona"] = pid
        try:
            self.config.save_config()
        except Exception as e:
            return error_response(f"保存失败: {e}")
        return json_response({"ok": True})

    # ---- 记忆 API ----

    async def api_get_memory(self):
        # 支持按 scope + uid 精确查询某用户/群的全部长期记忆
        qscope = str(request.query.get("scope") or "").strip()
        quid = str(request.query.get("uid") or "").strip()
        users = await self.get_memory_users()
        if qscope in ("user", "group") and quid:
            key = f"{qscope}_{quid}"
            users = [key] if key in users else []
        result = []
        for u in users:
            memories = await self.get_user_memory(u)
            if memories:
                scope = "group" if u.startswith("group_") else "user"
                result.append({"uid": u, "scope": scope, "items": memories})
        return json_response(result)

    async def api_clear_memory(self):
        payload = await request.json(default={})
        scope = str(payload.get("scope") or "")
        users = await self.get_memory_users()
        if scope in ("user", "group"):
            users = [u for u in users if u.startswith(f"{scope}_")]
        for u in users:
            await self.save_user_memory(u, [])
        return json_response({"cleared": True})

    async def api_add_memory(self):
        payload = await request.json(default={})
        scope = str(payload.get("scope") or "user")
        uid = str(payload.get("uid") or "").strip()
        content = str(payload.get("content") or "").strip()
        if scope not in ("user", "group"):
            return error_response("scope 只能为 user 或 group")
        if not uid or not content:
            return error_response("缺少 uid 或 content")
        key = f"{scope}_{uid}"
        await self.add_memory(key, content)
        return json_response({"ok": True, "uid": key})

    async def api_delete_memory(self):
        payload = await request.json(default={})
        uid = str(payload.get("uid", ""))
        mem_id = str(payload.get("id", ""))
        if not uid or not mem_id:
            return error_response("缺少参数")
        ok = await self.delete_user_memory(uid, mem_id)
        return json_response({"deleted": ok})

    # ---- 好感度 API ----

    async def api_get_favorability(self):
        qscope = str(request.query.get("scope") or "").strip()
        quid = str(request.query.get("uid") or "").strip()
        data = await self._load_favorability()
        result = []
        for scope, mapping in data.items():
            if qscope and scope != qscope:
                continue
            for uid, value in mapping.items():
                if quid and str(uid) != quid:
                    continue
                result.append({"scope": scope, "uid": str(uid), "value": int(value)})
        return json_response(result)

    async def api_set_favorability(self):
        payload = await request.json(default={})
        scope = str(payload.get("scope") or "user")
        uid = str(payload.get("uid") or "").strip()
        if scope not in ("user", "group"):
            return error_response("scope 只能为 user 或 group")
        if not uid:
            return error_response("缺少 uid")
        try:
            value = int(payload.get("value", 50))
        except Exception:
            return error_response("value 必须为数字")
        value = max(0, min(100, value))
        data = await self._load_favorability()
        data.setdefault(scope, {})[str(uid)] = value
        await self._save_favorability(data)
        return json_response({"ok": True})

    async def api_delete_favorability(self):
        payload = await request.json(default={})
        scope = str(payload.get("scope") or "")
        uid = str(payload.get("uid") or "").strip()
        if scope not in ("user", "group") or not uid:
            return error_response("缺少参数")
        data = await self._load_favorability()
        if str(uid) in data.get(scope, {}):
            del data[scope][str(uid)]
        await self._save_favorability(data)
        return json_response({"deleted": True})

    async def api_clear_favorability(self):
        payload = await request.json(default={})
        scope = str(payload.get("scope") or "")
        data = await self._load_favorability()
        if scope in ("user", "group"):
            data[scope] = {}
        else:
            data = {"user": {}, "group": {}}
        await self._save_favorability(data)
        return json_response({"cleared": True})

    async def api_test_api(self):
        payload = await request.json(default={})
        # scope: chat / vision / both（对话与识图模型分别测试）
        scope = str(payload.get("scope") or "both").strip()
        if scope not in ("chat", "vision", "both"):
            return error_response("scope 只能为 chat / vision / both")
        # 对话与识图共用同一 API 地址与 Key，仅模型名称不同；
        # 兼容旧配置：未填新字段时回退到旧版本的 chat_api_base_url / chat_api_key。
        base_url = (
            str(payload.get("api_base_url") or "").strip()
            or str(payload.get("chat_api_base_url") or "").strip()
            or self.config.get("api_base_url", "")
            or self.config.get("chat_api_base_url", "")
        )
        api_key = (
            str(payload.get("api_key") or "").strip()
            or str(payload.get("chat_api_key") or "").strip()
            or self.config.get("api_key", "")
            or self.config.get("chat_api_key", "")
        )
        chat_model = str(payload.get("chat_model") or self.config.get("chat_model", ""))
        vision_model = str(payload.get("vision_model") or self.config.get("vision_model", ""))
        results = {}

        if scope in ("chat", "both"):
            if base_url:
                if not chat_model:
                    return error_response("请填写对话模型名称后再测试对话模型")
                ok, msg = await self._probe_model(base_url, api_key, chat_model)
                results["chat"] = {"model": chat_model, "ok": ok, "message": msg}
            else:
                # 未填写自定义 API 时，测试 AstrBot 管理面板配置的对话模型
                prov = await self._resolve_provider(False)
                if not prov:
                    return error_response("未配置对话模型，请在 AstrBot 管理面板配置对话模型，或在控制界面填写自定义 API 地址")
                try:
                    await prov.test()
                    model = prov.meta().model or prov.meta().id
                    results["chat"] = {"model": model or "（AstrBot 默认模型）", "ok": True, "message": "连接成功，模型响应正常"}
                except Exception as e:
                    results["chat"] = {"ok": False, "message": f"连接失败: {e}"}

        if scope in ("vision", "both"):
            # 识图模型独立测试：与对话共用同一 API 地址与 Key，仅模型名不同；
            # 未配置任何识图模型时如实提示"未配置"，而不是回退到对话模型报 OK。
            cfg_provider_id = self.config.get("vision_provider_id", "") or self._astrbot_image_caption_provider_id()
            if base_url:
                if not vision_model:
                    return error_response("请填写识图模型名称后再测试识图模型")
                ok, msg = await self._probe_model(base_url, api_key, vision_model)
                results["vision"] = {"model": vision_model, "ok": ok, "message": msg}
            elif cfg_provider_id:
                prov = self.context.get_provider_by_id(cfg_provider_id)
                if not prov:
                    return error_response(f"未找到识图模型提供商: {cfg_provider_id}")
                try:
                    await prov.test()
                    model = prov.meta().model or prov.meta().id
                    results["vision"] = {"model": model or cfg_provider_id, "ok": True, "message": "连接成功，模型响应正常"}
                except Exception as e:
                    results["vision"] = {"ok": False, "message": f"连接失败: {e}"}
            else:
                return error_response(
                    "未配置识图模型：未填写自定义 API 地址，也未指定 AstrBot 识图模型提供商，请先在控制界面/管理面板配置后再测试"
                )

        all_ok = all(r.get("ok") for r in results.values())
        if all_ok:
            return json_response({"ok": True, "message": "全部模型连接正常", "results": results})
        return json_response({"ok": False, "message": "部分模型测试失败，详见 results", "results": results})

    async def api_model_status(self):
        """检测目标模型的对话/视觉模型是否开启并分别测试连通性。

        target: custom（自定义模型）/ astrbot（系统 AstrBot 模型）。
        custom 对话开启条件：自定义模型开关开启且 API 地址与 Key 均已填写；
        custom 视觉开启条件：识图开关开启且 API 地址与 Key 均已填写（与对话共用）；
        astrbot 对话开启条件：AstrBot AI 对话总开关开启且存在默认对话模型；
        astrbot 视觉开启条件：AstrBot AI 对话总开关开启且存在默认图片转述模型。
        """
        payload = await request.json(default={})
        target = str(payload.get("target") or "").strip()
        if target not in ("custom", "astrbot"):
            return error_response("target 只能为 custom / astrbot")

        # 自定义模型与 AstrBot 模型均未开启时，统一提示"模型没有打开"
        if not self._astrbot_ai_enable() and not self.config.get("custom_model_enable", False):
            return json_response(
                {
                    "ok": True,
                    "items": [
                        {
                            "name": "模型",
                            "enabled": False,
                            "connected": False,
                            "model": "",
                            "message": "模型没有打开",
                        }
                    ],
                }
            )

        items: list[dict] = []

        if target == "custom":
            base_url = (
                str(self.config.get("api_base_url") or "").strip()
                or str(self.config.get("chat_api_base_url") or "").strip()
            )
            api_key = (
                str(self.config.get("api_key") or "").strip()
                or str(self.config.get("chat_api_key") or "").strip()
            )

            # 对话模型
            missing = []
            if not self.config.get("custom_model_enable", False):
                missing.append("自定义模型开关")
            if not base_url:
                missing.append("API 地址")
            if not api_key:
                missing.append("API Key")
            if missing:
                items.append(
                    {
                        "name": "对话模型",
                        "enabled": False,
                        "connected": False,
                        "model": "",
                        "message": f"未开启（缺少：{'、'.join(missing)}）",
                    }
                )
            else:
                chat_model = str(self.config.get("chat_model", "") or "").strip()
                if not chat_model:
                    items.append(
                        {
                            "name": "对话模型",
                            "enabled": True,
                            "connected": False,
                            "model": "自定义 API",
                            "message": "开启（未填写对话模型名称，无法测试连通性）",
                        }
                    )
                else:
                    ok, msg = await self._probe_model(base_url, api_key, chat_model)
                    if ok:
                        items.append(
                            {
                                "name": "对话模型",
                                "enabled": True,
                                "connected": True,
                                "model": chat_model,
                                "message": "开启（连接正常）",
                            }
                        )
                    else:
                        items.append(
                            {
                                "name": "对话模型",
                                "enabled": True,
                                "connected": False,
                                "model": chat_model,
                                "message": f"开启（连接失败：{msg}）",
                            }
                        )

            # 视觉模型（与对话共用 API 地址与 Key）
            missing = []
            if not self.config.get("vision_model_enable", False):
                missing.append("识图开关")
            if not base_url:
                missing.append("API 地址")
            if not api_key:
                missing.append("API Key")
            if missing:
                items.append(
                    {
                        "name": "视觉模型",
                        "enabled": False,
                        "connected": False,
                        "model": "",
                        "message": f"未开启（缺少：{'、'.join(missing)}）",
                    }
                )
            else:
                vision_model = str(self.config.get("vision_model", "") or "").strip()
                if not vision_model:
                    items.append(
                        {
                            "name": "视觉模型",
                            "enabled": False,
                            "connected": False,
                            "model": "",
                            "message": "未配置（未填写识图模型名称，不拉取 AstrBot 系统模型）",
                        }
                    )
                else:
                    ok, msg = await self._probe_model(base_url, api_key, vision_model)
                    if ok:
                        items.append(
                            {
                                "name": "视觉模型",
                                "enabled": True,
                                "connected": True,
                                "model": vision_model,
                                "message": "开启（连接正常）",
                            }
                        )
                    else:
                        items.append(
                            {
                                "name": "视觉模型",
                                "enabled": True,
                                "connected": False,
                                "model": vision_model,
                                "message": f"开启（连接失败：{msg}）",
                            }
                        )
        else:
            # target == "astrbot"
            ai_enable = self._astrbot_ai_enable()

            # 对话模型
            if not ai_enable:
                items.append(
                    {
                        "name": "对话模型",
                        "enabled": False,
                        "connected": False,
                        "model": "",
                        "message": "未开启（AstrBot AI 对话总开关已关闭）",
                    }
                )
            else:
                prov_id = self._astrbot_default_provider_id()
                if not prov_id:
                    # 未配置默认对话模型时，拉取当前第一个对话模型进行测试
                    prov = None
                    try:
                        prov = self.context.get_using_provider()
                    except Exception as e:
                        logger.warning(f"获取 AstrBot 默认模型失败: {e}")
                    if not prov:
                        items.append(
                            {
                                "name": "对话模型",
                                "enabled": False,
                                "connected": False,
                                "model": "",
                                "message": "未开启（AstrBot 未配置默认对话模型）",
                            }
                        )
                    else:
                        fallback_id = prov.meta().id
                        items.append(await self._build_provider_test_item("对话模型", fallback_id))
                else:
                    items.append(await self._build_provider_test_item("对话模型", prov_id))

            # 视觉模型
            if not ai_enable:
                items.append(
                    {
                        "name": "视觉模型",
                        "enabled": False,
                        "connected": False,
                        "model": "",
                        "message": "未开启（AstrBot AI 对话总开关已关闭）",
                    }
                )
            else:
                prov_id = self._astrbot_image_caption_provider_id()
                if not prov_id:
                    items.append(
                        {
                            "name": "视觉模型",
                            "enabled": False,
                            "connected": False,
                            "model": "",
                            "message": "未开启（AstrBot 未配置默认图片转述模型）",
                        }
                    )
                else:
                    items.append(await self._build_provider_test_item("视觉模型", prov_id))

        return json_response({"ok": True, "items": items})

    async def _build_provider_test_item(self, name: str, prov_id: str) -> dict:
        """构建单个 AstrBot 提供商的测试结果项。"""
        prov = self.context.get_provider_by_id(prov_id)
        if not prov:
            return {
                "name": name,
                "enabled": False,
                "connected": False,
                "model": prov_id,
                "message": f"未开启（无法解析提供商 {prov_id}）",
            }
        try:
            await prov.test()
            model = prov.meta().model or prov.meta().id or prov_id
            return {
                "name": name,
                "enabled": True,
                "connected": True,
                "model": model,
                "message": "开启（连接正常）",
            }
        except Exception as e:
            return {
                "name": name,
                "enabled": True,
                "connected": False,
                "model": prov_id,
                "message": f"开启（连接失败：{e}）",
            }

    async def _probe_model(self, base_url: str, api_key: str, model: str) -> tuple[bool, str]:
        """探测指定模型在 API 地址下的可用性，返回 (是否可用, 提示信息)。"""
        payload_body = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 16,
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self._normalize_api_endpoint(base_url), json=payload_body, headers=headers)
                if resp.status_code >= 400:
                    return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
                data = resp.json()
                if data.get("choices"):
                    return True, "连接成功，模型响应正常"
                return False, f"响应格式异常: {str(data)[:200]}"
        except Exception as e:
            return False, f"连接失败: {e}"

    async def terminate(self) -> None:
        self.active_sessions.clear()
