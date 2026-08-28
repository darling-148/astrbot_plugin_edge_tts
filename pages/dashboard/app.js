const bridge = window.AstrBotPluginPage;

const $ = (id) => document.getElementById(id);

let context = null;
let toastTimer = null;
let personas = [];
let editingPersonaId = null;
let ttsVoices = [];
let astrbotCurrentPersonaName = "";

// 兜底音色表（后端未返回时使用，与后端 TTS_VOICES 保持一致的中文描述）
const FALLBACK_TTS_VOICES = [
  { value: "af-ZA-AdriNeural", label: "阿德里 · 南非荷兰语(南非) 女声", group: "国外" },
  { value: "af-ZA-WillemNeural", label: "威廉 · 南非荷兰语(南非) 男声", group: "国外" },
  { value: "sq-AL-AnilaNeural", label: "阿妮拉 · 阿尔巴尼亚语(阿尔巴尼亚) 女声", group: "国外" },
  { value: "sq-AL-IlirNeural", label: "伊利尔 · 阿尔巴尼亚语(阿尔巴尼亚) 男声", group: "国外" },
  { value: "am-ET-AmehaNeural", label: "阿梅哈 · 阿姆哈拉语(埃塞俄比亚) 男声", group: "国外" },
  { value: "am-ET-MekdesNeural", label: "梅克德斯 · 阿姆哈拉语(埃塞俄比亚) 女声", group: "国外" },
  { value: "ar-DZ-AminaNeural", label: "阿米娜 · 阿拉伯语(阿尔及利亚) 女声", group: "国外" },
  { value: "ar-DZ-IsmaelNeural", label: "伊斯梅尔 · 阿拉伯语(阿尔及利亚) 男声", group: "国外" },
  { value: "ar-BH-AliNeural", label: "阿里 · 阿拉伯语(巴林) 男声", group: "国外" },
  { value: "ar-BH-LailaNeural", label: "莱拉 · 阿拉伯语(巴林) 女声", group: "国外" },
  { value: "ar-EG-SalmaNeural", label: "萨尔玛 · 阿拉伯语(埃及) 女声", group: "国外" },
  { value: "ar-EG-ShakirNeural", label: "沙基尔 · 阿拉伯语(埃及) 男声", group: "国外" },
  { value: "ar-IQ-BasselNeural", label: "巴塞尔 · 阿拉伯语(伊拉克) 男声", group: "国外" },
  { value: "ar-IQ-RanaNeural", label: "拉娜 · 阿拉伯语(伊拉克) 女声", group: "国外" },
  { value: "ar-JO-SanaNeural", label: "萨娜 · 阿拉伯语(约旦) 女声", group: "国外" },
  { value: "ar-JO-TaimNeural", label: "塔伊姆 · 阿拉伯语(约旦) 男声", group: "国外" },
  { value: "ar-KW-FahedNeural", label: "法赫德 · 阿拉伯语(科威特) 男声", group: "国外" },
  { value: "ar-KW-NouraNeural", label: "努拉 · 阿拉伯语(科威特) 女声", group: "国外" },
  { value: "ar-LB-LaylaNeural", label: "蕾拉 · 阿拉伯语(黎巴嫩) 女声", group: "国外" },
  { value: "ar-LB-RamiNeural", label: "拉米 · 阿拉伯语(黎巴嫩) 男声", group: "国外" },
  { value: "ar-LY-ImanNeural", label: "伊曼 · 阿拉伯语(利比亚) 女声", group: "国外" },
  { value: "ar-LY-OmarNeural", label: "奥马尔 · 阿拉伯语(利比亚) 男声", group: "国外" },
  { value: "ar-MA-JamalNeural", label: "贾马尔 · 阿拉伯语(摩洛哥) 男声", group: "国外" },
  { value: "ar-MA-MounaNeural", label: "穆娜 · 阿拉伯语(摩洛哥) 女声", group: "国外" },
  { value: "ar-OM-AbdullahNeural", label: "阿卜杜拉 · 阿拉伯语(阿曼) 男声", group: "国外" },
  { value: "ar-OM-AyshaNeural", label: "艾莎 · 阿拉伯语(阿曼) 女声", group: "国外" },
  { value: "ar-QA-AmalNeural", label: "阿马尔 · 阿拉伯语(卡塔尔) 女声", group: "国外" },
  { value: "ar-QA-MoazNeural", label: "莫阿兹 · 阿拉伯语(卡塔尔) 男声", group: "国外" },
  { value: "ar-SA-HamedNeural", label: "哈米德 · 阿拉伯语(沙特阿拉伯) 男声", group: "国外" },
  { value: "ar-SA-ZariyahNeural", label: "扎里娅 · 阿拉伯语(沙特阿拉伯) 女声", group: "国外" },
  { value: "ar-SY-AmanyNeural", label: "阿曼妮 · 阿拉伯语(叙利亚) 女声", group: "国外" },
  { value: "ar-SY-LaithNeural", label: "莱斯 · 阿拉伯语(叙利亚) 男声", group: "国外" },
  { value: "ar-TN-HediNeural", label: "赫迪 · 阿拉伯语(突尼斯) 男声", group: "国外" },
  { value: "ar-TN-ReemNeural", label: "蕾姆 · 阿拉伯语(突尼斯) 女声", group: "国外" },
  { value: "ar-AE-FatimaNeural", label: "法蒂玛 · 阿拉伯语(阿联酋) 女声", group: "国外" },
  { value: "ar-AE-HamdanNeural", label: "哈姆丹 · 阿拉伯语(阿联酋) 男声", group: "国外" },
  { value: "ar-YE-MaryamNeural", label: "玛丽亚姆 · 阿拉伯语(也门) 女声", group: "国外" },
  { value: "ar-YE-SalehNeural", label: "萨利赫 · 阿拉伯语(也门) 男声", group: "国外" },
  { value: "az-AZ-BabekNeural", label: "巴贝克 · 阿塞拜疆语(阿塞拜疆) 男声", group: "国外" },
  { value: "az-AZ-BanuNeural", label: "巴努 · 阿塞拜疆语(阿塞拜疆) 女声", group: "国外" },
  { value: "bn-BD-NabanitaNeural", label: "纳巴尼塔 · 孟加拉语(孟加拉国) 女声", group: "国外" },
  { value: "bn-BD-PradeepNeural", label: "普拉迪普 · 孟加拉语(孟加拉国) 男声", group: "国外" },
  { value: "bn-IN-BashkarNeural", label: "巴什卡尔 · 孟加拉语(印度) 男声", group: "国外" },
  { value: "bn-IN-TanishaaNeural", label: "塔妮莎 · 孟加拉语(印度) 女声", group: "国外" },
  { value: "bs-BA-VesnaNeural", label: "韦斯娜 · 波斯尼亚语(波黑) 女声", group: "国外" },
  { value: "bs-BA-GoranNeural", label: "戈兰 · 波斯尼亚语(波黑) 男声", group: "国外" },
  { value: "bg-BG-BorislavNeural", label: "博里斯拉夫 · 保加利亚语(保加利亚) 男声", group: "国外" },
  { value: "bg-BG-KalinaNeural", label: "卡琳娜 · 保加利亚语(保加利亚) 女声", group: "国外" },
  { value: "my-MM-NilarNeural", label: "尼拉尔 · 缅甸语(缅甸) 女声", group: "国外" },
  { value: "my-MM-ThihaNeural", label: "提哈 · 缅甸语(缅甸) 男声", group: "国外" },
  { value: "ca-ES-EnricNeural", label: "恩里克 · 加泰罗尼亚语(西班牙) 男声", group: "国外" },
  { value: "ca-ES-JoanaNeural", label: "若阿娜 · 加泰罗尼亚语(西班牙) 女声", group: "国外" },
  { value: "zh-HK-HiuGaaiNeural", label: "曉佳 · 粤语女声，清亮利落", group: "中国" },
  { value: "zh-HK-HiuMaanNeural", label: "曉曼 · 粤语女声，温柔知性", group: "中国" },
  { value: "zh-HK-WanLungNeural", label: "雲龍 · 粤语男声，沉稳大气", group: "中国" },
  { value: "zh-CN-XiaoxiaoNeural", label: "晓晓 · 温柔甜美的女声，亲和治愈，适合贴心陪护", group: "中国" },
  { value: "zh-CN-XiaoyiNeural", label: "晓伊 · 清甜活泼的女声，元气满满，适合日常聊天", group: "中国" },
  { value: "zh-CN-YunjianNeural", label: "云健 · 成熟稳重的男声，值得信赖的知性大叔感", group: "中国" },
  { value: "zh-CN-YunxiNeural", label: "云希 · 阳光清爽的少年男声，温暖而充满朝气", group: "中国" },
  { value: "zh-CN-YunxiaNeural", label: "云夏 · 稚嫩可爱的男童声，天真灵动", group: "中国" },
  { value: "zh-CN-YunyangNeural", label: "云扬 · 专业权威的男声，沉稳大方，适合讲解播报", group: "中国" },
  { value: "zh-CN-liaoning-XiaobeiNeural", label: "晓北 · 辽宁方言女声，地道东北味", group: "中国" },
  { value: "zh-TW-HsiaoChenNeural", label: "曉臻 · 台湾国语女声，清澈甜美", group: "中国" },
  { value: "zh-TW-YunJheNeural", label: "雲哲 · 台湾国语男声，温和清爽", group: "中国" },
  { value: "zh-TW-HsiaoYuNeural", label: "曉雨 · 台湾国语女声，俏皮灵动", group: "中国" },
  { value: "zh-CN-shaanxi-XiaoniNeural", label: "晓妮 · 陕西方言女声，亲切朴实", group: "中国" },
  { value: "hr-HR-GabrijelaNeural", label: "加布里耶拉 · 克罗地亚语(克罗地亚) 女声", group: "国外" },
  { value: "hr-HR-SreckoNeural", label: "斯雷奇科 · 克罗地亚语(克罗地亚) 男声", group: "国外" },
  { value: "cs-CZ-AntoninNeural", label: "安东宁 · 捷克语(捷克) 男声", group: "国外" },
  { value: "cs-CZ-VlastaNeural", label: "弗拉斯塔 · 捷克语(捷克) 女声", group: "国外" },
  { value: "da-DK-ChristelNeural", label: "克里斯特尔 · 丹麦语(丹麦) 女声", group: "国外" },
  { value: "da-DK-JeppeNeural", label: "耶珀 · 丹麦语(丹麦) 男声", group: "国外" },
  { value: "nl-BE-ArnaudNeural", label: "阿尔诺 · 荷兰语(比利时) 男声", group: "国外" },
  { value: "nl-BE-DenaNeural", label: "德娜 · 荷兰语(比利时) 女声", group: "国外" },
  { value: "nl-NL-ColetteNeural", label: "科莱特 · 荷兰语(荷兰) 女声", group: "国外" },
  { value: "nl-NL-FennaNeural", label: "芬娜 · 荷兰语(荷兰) 女声", group: "国外" },
  { value: "nl-NL-MaartenNeural", label: "马尔滕 · 荷兰语(荷兰) 男声", group: "国外" },
  { value: "en-AU-WilliamMultilingualNeural", label: "威廉 · 英语(澳大利亚) 男声", group: "国外" },
  { value: "en-AU-NatashaNeural", label: "娜塔莎 · 英语(澳大利亚) 女声", group: "国外" },
  { value: "en-CA-ClaraNeural", label: "克拉拉 · 英语(加拿大) 女声", group: "国外" },
  { value: "en-CA-LiamNeural", label: "利亚姆 · 英语(加拿大) 男声", group: "国外" },
  { value: "en-HK-YanNeural", label: "燕 · 英语(香港) 女声", group: "国外" },
  { value: "en-HK-SamNeural", label: "山姆 · 英语(香港) 男声", group: "国外" },
  { value: "en-IN-NeerjaExpressiveNeural", label: "尼拉 · 英语(印度) 女声", group: "国外" },
  { value: "en-IN-NeerjaNeural", label: "尼拉 · 英语(印度) 女声", group: "国外" },
  { value: "en-IN-PrabhatNeural", label: "普拉巴特 · 英语(印度) 男声", group: "国外" },
  { value: "en-IE-ConnorNeural", label: "康纳 · 英语(爱尔兰) 男声", group: "国外" },
  { value: "en-IE-EmilyNeural", label: "艾米丽 · 英语(爱尔兰) 女声", group: "国外" },
  { value: "en-KE-AsiliaNeural", label: "阿西莉亚 · 英语(肯尼亚) 女声", group: "国外" },
  { value: "en-KE-ChilembaNeural", label: "奇伦巴 · 英语(肯尼亚) 男声", group: "国外" },
  { value: "en-NZ-MitchellNeural", label: "米切尔 · 英语(新西兰) 男声", group: "国外" },
  { value: "en-NZ-MollyNeural", label: "莫莉 · 英语(新西兰) 女声", group: "国外" },
  { value: "en-NG-AbeoNeural", label: "阿贝奥 · 英语(尼日利亚) 男声", group: "国外" },
  { value: "en-NG-EzinneNeural", label: "艾辛内 · 英语(尼日利亚) 女声", group: "国外" },
  { value: "en-PH-JamesNeural", label: "詹姆斯 · 英语(菲律宾) 男声", group: "国外" },
  { value: "en-PH-RosaNeural", label: "罗莎 · 英语(菲律宾) 女声", group: "国外" },
  { value: "en-US-AvaNeural", label: "艾娃 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-AndrewNeural", label: "安德鲁 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-EmmaNeural", label: "艾玛 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-BrianNeural", label: "布莱恩 · 英语(美国) 男声", group: "国外" },
  { value: "en-SG-LunaNeural", label: "露娜 · 英语(新加坡) 女声", group: "国外" },
  { value: "en-SG-WayneNeural", label: "韦恩 · 英语(新加坡) 男声", group: "国外" },
  { value: "en-ZA-LeahNeural", label: "莉亚 · 英语(南非) 女声", group: "国外" },
  { value: "en-ZA-LukeNeural", label: "卢克 · 英语(南非) 男声", group: "国外" },
  { value: "en-TZ-ElimuNeural", label: "埃利穆 · 英语(坦桑尼亚) 男声", group: "国外" },
  { value: "en-TZ-ImaniNeural", label: "伊玛尼 · 英语(坦桑尼亚) 女声", group: "国外" },
  { value: "en-GB-LibbyNeural", label: "莉比 · 英语(英国) 女声", group: "国外" },
  { value: "en-GB-MaisieNeural", label: "梅西 · 英语(英国) 女声", group: "国外" },
  { value: "en-GB-RyanNeural", label: "瑞恩 · 英语(英国) 男声", group: "国外" },
  { value: "en-GB-SoniaNeural", label: "索尼娅 · 英语(英国) 女声", group: "国外" },
  { value: "en-GB-ThomasNeural", label: "托马斯 · 英语(英国) 男声", group: "国外" },
  { value: "en-US-AnaNeural", label: "安娜 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-AndrewMultilingualNeural", label: "安德鲁 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-AriaNeural", label: "艾瑞亚 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-AvaMultilingualNeural", label: "艾娃 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-BrianMultilingualNeural", label: "布莱恩 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-ChristopherNeural", label: "克里斯托弗 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-EmmaMultilingualNeural", label: "艾玛 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-EricNeural", label: "埃里克 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-GuyNeural", label: "盖伊 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-JennyNeural", label: "珍妮 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-MichelleNeural", label: "米歇尔 · 英语(美国) 女声", group: "国外" },
  { value: "en-US-RogerNeural", label: "罗杰 · 英语(美国) 男声", group: "国外" },
  { value: "en-US-SteffanNeural", label: "斯蒂芬 · 英语(美国) 男声", group: "国外" },
  { value: "et-EE-AnuNeural", label: "阿努 · 爱沙尼亚语(爱沙尼亚) 女声", group: "国外" },
  { value: "et-EE-KertNeural", label: "凯尔特 · 爱沙尼亚语(爱沙尼亚) 男声", group: "国外" },
  { value: "fil-PH-AngeloNeural", label: "安杰洛 · 菲律宾语(菲律宾) 男声", group: "国外" },
  { value: "fil-PH-BlessicaNeural", label: "布莱西卡 · 菲律宾语(菲律宾) 女声", group: "国外" },
  { value: "fi-FI-HarriNeural", label: "哈里 · 芬兰语(芬兰) 男声", group: "国外" },
  { value: "fi-FI-NooraNeural", label: "诺拉 · 芬兰语(芬兰) 女声", group: "国外" },
  { value: "fr-BE-CharlineNeural", label: "夏琳 · 法语(比利时) 女声", group: "国外" },
  { value: "fr-BE-GerardNeural", label: "杰拉德 · 法语(比利时) 男声", group: "国外" },
  { value: "fr-CA-ThierryNeural", label: "蒂埃里 · 法语(加拿大) 男声", group: "国外" },
  { value: "fr-CA-AntoineNeural", label: "安托万 · 法语(加拿大) 男声", group: "国外" },
  { value: "fr-CA-JeanNeural", label: "让 · 法语(加拿大) 男声", group: "国外" },
  { value: "fr-CA-SylvieNeural", label: "西尔维 · 法语(加拿大) 女声", group: "国外" },
  { value: "fr-FR-VivienneMultilingualNeural", label: "维维恩 · 法语(法国) 女声", group: "国外" },
  { value: "fr-FR-RemyMultilingualNeural", label: "雷米 · 法语(法国) 男声", group: "国外" },
  { value: "fr-FR-DeniseNeural", label: "丹妮丝 · 法语(法国) 女声", group: "国外" },
  { value: "fr-FR-EloiseNeural", label: "埃洛伊丝 · 法语(法国) 女声", group: "国外" },
  { value: "fr-FR-HenriNeural", label: "亨利 · 法语(法国) 男声", group: "国外" },
  { value: "fr-CH-ArianeNeural", label: "阿丽亚娜 · 法语(瑞士) 女声", group: "国外" },
  { value: "fr-CH-FabriceNeural", label: "法布里斯 · 法语(瑞士) 男声", group: "国外" },
  { value: "gl-ES-RoiNeural", label: "罗伊 · 加利西亚语(西班牙) 男声", group: "国外" },
  { value: "gl-ES-SabelaNeural", label: "萨贝拉 · 加利西亚语(西班牙) 女声", group: "国外" },
  { value: "ka-GE-EkaNeural", label: "埃卡 · 格鲁吉亚语(格鲁吉亚) 女声", group: "国外" },
  { value: "ka-GE-GiorgiNeural", label: "乔吉 · 格鲁吉亚语(格鲁吉亚) 男声", group: "国外" },
  { value: "de-AT-IngridNeural", label: "英格丽德 · 德语(奥地利) 女声", group: "国外" },
  { value: "de-AT-JonasNeural", label: "约纳斯 · 德语(奥地利) 男声", group: "国外" },
  { value: "de-DE-SeraphinaMultilingualNeural", label: "塞拉菲娜 · 德语(德国) 女声", group: "国外" },
  { value: "de-DE-FlorianMultilingualNeural", label: "弗洛里安 · 德语(德国) 男声", group: "国外" },
  { value: "de-DE-AmalaNeural", label: "阿玛拉 · 德语(德国) 女声", group: "国外" },
  { value: "de-DE-ConradNeural", label: "康拉德 · 德语(德国) 男声", group: "国外" },
  { value: "de-DE-KatjaNeural", label: "卡蒂娅 · 德语(德国) 女声", group: "国外" },
  { value: "de-DE-KillianNeural", label: "基利安 · 德语(德国) 男声", group: "国外" },
  { value: "de-CH-JanNeural", label: "扬 · 德语(瑞士) 男声", group: "国外" },
  { value: "de-CH-LeniNeural", label: "莱妮 · 德语(瑞士) 女声", group: "国外" },
  { value: "el-GR-AthinaNeural", label: "雅典娜 · 希腊语(希腊) 女声", group: "国外" },
  { value: "el-GR-NestorasNeural", label: "内斯托拉斯 · 希腊语(希腊) 男声", group: "国外" },
  { value: "gu-IN-DhwaniNeural", label: "德瓦尼 · 古吉拉特语(印度) 女声", group: "国外" },
  { value: "gu-IN-NiranjanNeural", label: "尼兰詹 · 古吉拉特语(印度) 男声", group: "国外" },
  { value: "he-IL-AvriNeural", label: "阿夫里 · 希伯来语(以色列) 男声", group: "国外" },
  { value: "he-IL-HilaNeural", label: "希拉 · 希伯来语(以色列) 女声", group: "国外" },
  { value: "hi-IN-MadhurNeural", label: "马杜尔 · 印地语(印度) 男声", group: "国外" },
  { value: "hi-IN-SwaraNeural", label: "斯瓦拉 · 印地语(印度) 女声", group: "国外" },
  { value: "hu-HU-NoemiNeural", label: "诺埃米 · 匈牙利语(匈牙利) 女声", group: "国外" },
  { value: "hu-HU-TamasNeural", label: "塔马斯 · 匈牙利语(匈牙利) 男声", group: "国外" },
  { value: "is-IS-GudrunNeural", label: "古德伦 · 冰岛语(冰岛) 女声", group: "国外" },
  { value: "is-IS-GunnarNeural", label: "贡纳尔 · 冰岛语(冰岛) 男声", group: "国外" },
  { value: "id-ID-ArdiNeural", label: "阿尔迪 · 印尼语(印度尼西亚) 男声", group: "国外" },
  { value: "id-ID-GadisNeural", label: "加迪斯 · 印尼语(印度尼西亚) 女声", group: "国外" },
  { value: "iu-Latn-CA-SiqiniqNeural", label: "西奇尼克 · 因纽特语(加拿大) 女声", group: "国外" },
  { value: "iu-Latn-CA-TaqqiqNeural", label: "塔奇克 · 因纽特语(加拿大) 男声", group: "国外" },
  { value: "iu-Cans-CA-SiqiniqNeural", label: "西奇尼克 · 因纽特语(加拿大) 女声", group: "国外" },
  { value: "iu-Cans-CA-TaqqiqNeural", label: "塔奇克 · 因纽特语(加拿大) 男声", group: "国外" },
  { value: "ga-IE-ColmNeural", label: "科尔姆 · 爱尔兰语(爱尔兰) 男声", group: "国外" },
  { value: "ga-IE-OrlaNeural", label: "奥拉 · 爱尔兰语(爱尔兰) 女声", group: "国外" },
  { value: "it-IT-GiuseppeMultilingualNeural", label: "朱塞佩 · 意大利语(意大利) 男声", group: "国外" },
  { value: "it-IT-DiegoNeural", label: "迭戈 · 意大利语(意大利) 男声", group: "国外" },
  { value: "it-IT-ElsaNeural", label: "艾尔莎 · 意大利语(意大利) 女声", group: "国外" },
  { value: "it-IT-IsabellaNeural", label: "伊莎贝拉 · 意大利语(意大利) 女声", group: "国外" },
  { value: "ja-JP-KeitaNeural", label: "凯塔 · 日语(日本) 男声", group: "国外" },
  { value: "ja-JP-NanamiNeural", label: "奈奈美 · 日语(日本) 女声", group: "国外" },
  { value: "jv-ID-DimasNeural", label: "迪马斯 · 爪哇语(印度尼西亚) 男声", group: "国外" },
  { value: "jv-ID-SitiNeural", label: "西蒂 · 爪哇语(印度尼西亚) 女声", group: "国外" },
  { value: "kn-IN-GaganNeural", label: "加根 · 卡纳达语(印度) 男声", group: "国外" },
  { value: "kn-IN-SapnaNeural", label: "萨普娜 · 卡纳达语(印度) 女声", group: "国外" },
  { value: "kk-KZ-AigulNeural", label: "爱古尔 · 哈萨克语(哈萨克斯坦) 女声", group: "国外" },
  { value: "kk-KZ-DauletNeural", label: "道莱特 · 哈萨克语(哈萨克斯坦) 男声", group: "国外" },
  { value: "km-KH-PisethNeural", label: "皮塞特 · 高棉语(柬埔寨) 男声", group: "国外" },
  { value: "km-KH-SreymomNeural", label: "斯雷莫姆 · 高棉语(柬埔寨) 女声", group: "国外" },
  { value: "ko-KR-HyunsuMultilingualNeural", label: "贤洙 · 韩语(韩国) 男声", group: "国外" },
  { value: "ko-KR-InJoonNeural", label: "仁俊 · 韩语(韩国) 男声", group: "国外" },
  { value: "ko-KR-SunHiNeural", label: "善熙 · 韩语(韩国) 女声", group: "国外" },
  { value: "lo-LA-ChanthavongNeural", label: "占塔冯 · 老挝语(老挝) 男声", group: "国外" },
  { value: "lo-LA-KeomanyNeural", label: "乔玛妮 · 老挝语(老挝) 女声", group: "国外" },
  { value: "lv-LV-EveritaNeural", label: "埃维丽塔 · 拉脱维亚语(拉脱维亚) 女声", group: "国外" },
  { value: "lv-LV-NilsNeural", label: "尼尔斯 · 拉脱维亚语(拉脱维亚) 男声", group: "国外" },
  { value: "lt-LT-LeonasNeural", label: "莱昂纳斯 · 立陶宛语(立陶宛) 男声", group: "国外" },
  { value: "lt-LT-OnaNeural", label: "奥娜 · 立陶宛语(立陶宛) 女声", group: "国外" },
  { value: "mk-MK-AleksandarNeural", label: "亚历山大 · 马其顿语(北马其顿) 男声", group: "国外" },
  { value: "mk-MK-MarijaNeural", label: "玛丽娅 · 马其顿语(北马其顿) 女声", group: "国外" },
  { value: "ms-MY-OsmanNeural", label: "奥斯曼 · 马来语(马来西亚) 男声", group: "国外" },
  { value: "ms-MY-YasminNeural", label: "亚斯明 · 马来语(马来西亚) 女声", group: "国外" },
  { value: "ml-IN-MidhunNeural", label: "米杜恩 · 马拉雅拉姆语(印度) 男声", group: "国外" },
  { value: "ml-IN-SobhanaNeural", label: "索巴娜 · 马拉雅拉姆语(印度) 女声", group: "国外" },
  { value: "mt-MT-GraceNeural", label: "格蕾丝 · 马耳他语(马耳他) 女声", group: "国外" },
  { value: "mt-MT-JosephNeural", label: "约瑟夫 · 马耳他语(马耳他) 男声", group: "国外" },
  { value: "mr-IN-AarohiNeural", label: "阿罗希 · 马拉地语(印度) 女声", group: "国外" },
  { value: "mr-IN-ManoharNeural", label: "马诺哈尔 · 马拉地语(印度) 男声", group: "国外" },
  { value: "mn-MN-BataaNeural", label: "巴塔 · 蒙古语(蒙古) 男声", group: "国外" },
  { value: "mn-MN-YesuiNeural", label: "耶苏伊 · 蒙古语(蒙古) 女声", group: "国外" },
  { value: "ne-NP-HemkalaNeural", label: "赫姆卡拉 · 尼泊尔语(尼泊尔) 女声", group: "国外" },
  { value: "ne-NP-SagarNeural", label: "萨加尔 · 尼泊尔语(尼泊尔) 男声", group: "国外" },
  { value: "nb-NO-FinnNeural", label: "芬恩 · 挪威语(挪威) 男声", group: "国外" },
  { value: "nb-NO-PernilleNeural", label: "佩妮莱 · 挪威语(挪威) 女声", group: "国外" },
  { value: "ps-AF-GulNawazNeural", label: "古尔纳瓦兹 · 普什图语(阿富汗) 男声", group: "国外" },
  { value: "ps-AF-LatifaNeural", label: "拉蒂法 · 普什图语(阿富汗) 女声", group: "国外" },
  { value: "fa-IR-DilaraNeural", label: "迪拉娜 · 波斯语(伊朗) 女声", group: "国外" },
  { value: "fa-IR-FaridNeural", label: "法里德 · 波斯语(伊朗) 男声", group: "国外" },
  { value: "pl-PL-MarekNeural", label: "马雷克 · 波兰语(波兰) 男声", group: "国外" },
  { value: "pl-PL-ZofiaNeural", label: "佐菲娅 · 波兰语(波兰) 女声", group: "国外" },
  { value: "pt-BR-ThalitaMultilingualNeural", label: "塔莉塔 · 葡萄牙语(巴西) 女声", group: "国外" },
  { value: "pt-BR-AntonioNeural", label: "安东尼奥 · 葡萄牙语(巴西) 男声", group: "国外" },
  { value: "pt-BR-FranciscaNeural", label: "弗朗西斯卡 · 葡萄牙语(巴西) 女声", group: "国外" },
  { value: "pt-PT-DuarteNeural", label: "杜阿尔特 · 葡萄牙语(葡萄牙) 男声", group: "国外" },
  { value: "pt-PT-RaquelNeural", label: "拉克尔 · 葡萄牙语(葡萄牙) 女声", group: "国外" },
  { value: "ro-RO-AlinaNeural", label: "阿丽娜 · 罗马尼亚语(罗马尼亚) 女声", group: "国外" },
  { value: "ro-RO-EmilNeural", label: "埃米尔 · 罗马尼亚语(罗马尼亚) 男声", group: "国外" },
  { value: "ru-RU-DmitryNeural", label: "德米特里 · 俄语(俄罗斯) 男声", group: "国外" },
  { value: "ru-RU-SvetlanaNeural", label: "斯维特兰娜 · 俄语(俄罗斯) 女声", group: "国外" },
  { value: "sr-RS-NicholasNeural", label: "尼古拉斯 · 塞尔维亚语(塞尔维亚) 男声", group: "国外" },
  { value: "sr-RS-SophieNeural", label: "索菲 · 塞尔维亚语(塞尔维亚) 女声", group: "国外" },
  { value: "si-LK-SameeraNeural", label: "萨米拉 · 僧伽罗语(斯里兰卡) 男声", group: "国外" },
  { value: "si-LK-ThiliniNeural", label: "蒂利尼 · 僧伽罗语(斯里兰卡) 女声", group: "国外" },
  { value: "sk-SK-LukasNeural", label: "卢卡斯 · 斯洛伐克语(斯洛伐克) 男声", group: "国外" },
  { value: "sk-SK-ViktoriaNeural", label: "维多利亚 · 斯洛伐克语(斯洛伐克) 女声", group: "国外" },
  { value: "sl-SI-PetraNeural", label: "佩特拉 · 斯洛文尼亚语(斯洛文尼亚) 女声", group: "国外" },
  { value: "sl-SI-RokNeural", label: "罗克 · 斯洛文尼亚语(斯洛文尼亚) 男声", group: "国外" },
  { value: "so-SO-MuuseNeural", label: "穆塞 · 索马里语(索马里) 男声", group: "国外" },
  { value: "so-SO-UbaxNeural", label: "乌巴克斯 · 索马里语(索马里) 女声", group: "国外" },
  { value: "es-AR-ElenaNeural", label: "埃琳娜 · 西班牙语(阿根廷) 女声", group: "国外" },
  { value: "es-AR-TomasNeural", label: "托马什 · 西班牙语(阿根廷) 男声", group: "国外" },
  { value: "es-BO-MarceloNeural", label: "马塞洛 · 西班牙语(玻利维亚) 男声", group: "国外" },
  { value: "es-BO-SofiaNeural", label: "索菲亚 · 西班牙语(玻利维亚) 女声", group: "国外" },
  { value: "es-CL-CatalinaNeural", label: "卡塔琳娜 · 西班牙语(智利) 女声", group: "国外" },
  { value: "es-CL-LorenzoNeural", label: "洛伦佐 · 西班牙语(智利) 男声", group: "国外" },
  { value: "es-CO-GonzaloNeural", label: "冈萨洛 · 西班牙语(哥伦比亚) 男声", group: "国外" },
  { value: "es-CO-SalomeNeural", label: "萨洛梅 · 西班牙语(哥伦比亚) 女声", group: "国外" },
  { value: "es-ES-XimenaNeural", label: "希梅娜 · 西班牙语(西班牙) 女声", group: "国外" },
  { value: "es-CR-JuanNeural", label: "胡安 · 西班牙语(哥斯达黎加) 男声", group: "国外" },
  { value: "es-CR-MariaNeural", label: "玛丽亚 · 西班牙语(哥斯达黎加) 女声", group: "国外" },
  { value: "es-CU-BelkysNeural", label: "贝尔基斯 · 西班牙语(古巴) 女声", group: "国外" },
  { value: "es-CU-ManuelNeural", label: "曼努埃尔 · 西班牙语(古巴) 男声", group: "国外" },
  { value: "es-DO-EmilioNeural", label: "埃米利奥 · 西班牙语(多米尼加) 男声", group: "国外" },
  { value: "es-DO-RamonaNeural", label: "拉莫娜 · 西班牙语(多米尼加) 女声", group: "国外" },
  { value: "es-EC-AndreaNeural", label: "安德烈娅 · 西班牙语(厄瓜多尔) 女声", group: "国外" },
  { value: "es-EC-LuisNeural", label: "路易斯 · 西班牙语(厄瓜多尔) 男声", group: "国外" },
  { value: "es-SV-LorenaNeural", label: "洛雷娜 · 西班牙语(萨尔瓦多) 女声", group: "国外" },
  { value: "es-SV-RodrigoNeural", label: "罗德里戈 · 西班牙语(萨尔瓦多) 男声", group: "国外" },
  { value: "es-GQ-JavierNeural", label: "哈维尔 · 西班牙语(赤道几内亚) 男声", group: "国外" },
  { value: "es-GQ-TeresaNeural", label: "特蕾莎 · 西班牙语(赤道几内亚) 女声", group: "国外" },
  { value: "es-GT-AndresNeural", label: "安德烈斯 · 西班牙语(危地马拉) 男声", group: "国外" },
  { value: "es-GT-MartaNeural", label: "玛尔塔 · 西班牙语(危地马拉) 女声", group: "国外" },
  { value: "es-HN-CarlosNeural", label: "卡洛斯 · 西班牙语(洪都拉斯) 男声", group: "国外" },
  { value: "es-HN-KarlaNeural", label: "卡拉 · 西班牙语(洪都拉斯) 女声", group: "国外" },
  { value: "es-MX-DaliaNeural", label: "达利娅 · 西班牙语(墨西哥) 女声", group: "国外" },
  { value: "es-MX-JorgeNeural", label: "豪尔赫 · 西班牙语(墨西哥) 男声", group: "国外" },
  { value: "es-NI-FedericoNeural", label: "费德里科 · 西班牙语(尼加拉瓜) 男声", group: "国外" },
  { value: "es-NI-YolandaNeural", label: "约兰达 · 西班牙语(尼加拉瓜) 女声", group: "国外" },
  { value: "es-PA-MargaritaNeural", label: "玛格丽塔 · 西班牙语(巴拿马) 女声", group: "国外" },
  { value: "es-PA-RobertoNeural", label: "罗伯托 · 西班牙语(巴拿马) 男声", group: "国外" },
  { value: "es-PY-MarioNeural", label: "马里奥 · 西班牙语(巴拉圭) 男声", group: "国外" },
  { value: "es-PY-TaniaNeural", label: "塔尼娅 · 西班牙语(巴拉圭) 女声", group: "国外" },
  { value: "es-PE-AlexNeural", label: "亚历克斯 · 西班牙语(秘鲁) 男声", group: "国外" },
  { value: "es-PE-CamilaNeural", label: "卡米拉 · 西班牙语(秘鲁) 女声", group: "国外" },
  { value: "es-PR-KarinaNeural", label: "卡里娜 · 西班牙语(波多黎各) 女声", group: "国外" },
  { value: "es-PR-VictorNeural", label: "维克托 · 西班牙语(波多黎各) 男声", group: "国外" },
  { value: "es-ES-AlvaroNeural", label: "阿尔瓦罗 · 西班牙语(西班牙) 男声", group: "国外" },
  { value: "es-ES-ElviraNeural", label: "埃尔维拉 · 西班牙语(西班牙) 女声", group: "国外" },
  { value: "es-US-AlonsoNeural", label: "阿隆索 · 西班牙语(美国) 男声", group: "国外" },
  { value: "es-US-PalomaNeural", label: "帕洛玛 · 西班牙语(美国) 女声", group: "国外" },
  { value: "es-UY-MateoNeural", label: "马特奥 · 西班牙语(乌拉圭) 男声", group: "国外" },
  { value: "es-UY-ValentinaNeural", label: "瓦伦蒂娜 · 西班牙语(乌拉圭) 女声", group: "国外" },
  { value: "es-VE-PaolaNeural", label: "保拉 · 西班牙语(委内瑞拉) 女声", group: "国外" },
  { value: "es-VE-SebastianNeural", label: "塞巴斯蒂安 · 西班牙语(委内瑞拉) 男声", group: "国外" },
  { value: "su-ID-JajangNeural", label: "贾姜 · 巽他语(印度尼西亚) 男声", group: "国外" },
  { value: "su-ID-TutiNeural", label: "图蒂 · 巽他语(印度尼西亚) 女声", group: "国外" },
  { value: "sw-KE-RafikiNeural", label: "拉菲基 · 斯瓦希里语(肯尼亚) 男声", group: "国外" },
  { value: "sw-KE-ZuriNeural", label: "祖里 · 斯瓦希里语(肯尼亚) 女声", group: "国外" },
  { value: "sw-TZ-DaudiNeural", label: "达乌迪 · 斯瓦希里语(坦桑尼亚) 男声", group: "国外" },
  { value: "sw-TZ-RehemaNeural", label: "蕾赫玛 · 斯瓦希里语(坦桑尼亚) 女声", group: "国外" },
  { value: "sv-SE-MattiasNeural", label: "马蒂亚斯 · 瑞典语(瑞典) 男声", group: "国外" },
  { value: "sv-SE-SofieNeural", label: "苏菲 · 瑞典语(瑞典) 女声", group: "国外" },
  { value: "ta-IN-PallaviNeural", label: "帕拉维 · 泰米尔语(印度) 女声", group: "国外" },
  { value: "ta-IN-ValluvarNeural", label: "瓦卢瓦尔 · 泰米尔语(印度) 男声", group: "国外" },
  { value: "ta-MY-KaniNeural", label: "卡尼 · 泰米尔语(马来西亚) 女声", group: "国外" },
  { value: "ta-MY-SuryaNeural", label: "苏里亚 · 泰米尔语(马来西亚) 男声", group: "国外" },
  { value: "ta-SG-AnbuNeural", label: "安布 · 泰米尔语(新加坡) 男声", group: "国外" },
  { value: "ta-SG-VenbaNeural", label: "文巴 · 泰米尔语(新加坡) 女声", group: "国外" },
  { value: "ta-LK-KumarNeural", label: "库马尔 · 泰米尔语(斯里兰卡) 男声", group: "国外" },
  { value: "ta-LK-SaranyaNeural", label: "萨拉尼亚 · 泰米尔语(斯里兰卡) 女声", group: "国外" },
  { value: "te-IN-MohanNeural", label: "莫汉 · 泰卢固语(印度) 男声", group: "国外" },
  { value: "te-IN-ShrutiNeural", label: "什鲁蒂 · 泰卢固语(印度) 女声", group: "国外" },
  { value: "th-TH-NiwatNeural", label: "尼瓦特 · 泰语(泰国) 男声", group: "国外" },
  { value: "th-TH-PremwadeeNeural", label: "普雷姆瓦迪 · 泰语(泰国) 女声", group: "国外" },
  { value: "tr-TR-EmelNeural", label: "埃梅尔 · 土耳其语(土耳其) 女声", group: "国外" },
  { value: "tr-TR-AhmetNeural", label: "艾哈迈德 · 土耳其语(土耳其) 男声", group: "国外" },
  { value: "uk-UA-OstapNeural", label: "奥斯塔普 · 乌克兰语(乌克兰) 男声", group: "国外" },
  { value: "uk-UA-PolinaNeural", label: "波琳娜 · 乌克兰语(乌克兰) 女声", group: "国外" },
  { value: "ur-IN-GulNeural", label: "古尔 · 乌尔都语(印度) 女声", group: "国外" },
  { value: "ur-IN-SalmanNeural", label: "萨勒曼 · 乌尔都语(印度) 男声", group: "国外" },
  { value: "ur-PK-AsadNeural", label: "阿萨德 · 乌尔都语(巴基斯坦) 男声", group: "国外" },
  { value: "ur-PK-UzmaNeural", label: "乌兹玛 · 乌尔都语(巴基斯坦) 女声", group: "国外" },
  { value: "uz-UZ-MadinaNeural", label: "玛迪娜 · 乌兹别克语(乌兹别克斯坦) 女声", group: "国外" },
  { value: "uz-UZ-SardorNeural", label: "萨尔多尔 · 乌兹别克语(乌兹别克斯坦) 男声", group: "国外" },
  { value: "vi-VN-HoaiMyNeural", label: "怀美 · 越南语(越南) 女声", group: "国外" },
  { value: "vi-VN-NamMinhNeural", label: "南明 · 越南语(越南) 男声", group: "国外" },
  { value: "cy-GB-AledNeural", label: "阿莱德 · 威尔士语(英国) 男声", group: "国外" },
  { value: "cy-GB-NiaNeural", label: "妮娅 · 威尔士语(英国) 女声", group: "国外" },
  { value: "zu-ZA-ThandoNeural", label: "坦多 · 祖鲁语(南非) 女声", group: "国外" },
  { value: "zu-ZA-ThembaNeural", label: "森巴 · 祖鲁语(南非) 男声", group: "国外" },
  { value: "zh-CN-XiaobeiNeural", label: "晓北 · 普通话女声，爽朗大方", group: "中国" },
  { value: "zh-CN-XiaoxuanNeural", label: "晓萱 · 娇俏可爱的女声，软糯甜美", group: "中国" },
];

function showToast(msg, isError = false, isSuccess = false, redText = false) {
  const toast = $("toast");
  let text = msg;
  let bg = isError ? "var(--red)" : "var(--card)";
  let color = isError ? "#fff" : "var(--text)";
  if (isSuccess) {
    text = "✅ " + msg;
    bg = "var(--green)";
    color = "#fff";
  } else if (redText) {
    text = "❌ " + msg;
    color = "var(--red)";
  }
  toast.textContent = text;
  toast.style.background = bg;
  toast.style.color = color;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setSwitch(id, on) {
  const el = $(id);
  if (el) el.checked = Boolean(on);
}

function syncPersonaSelectionDisabled() {
  const disabled = $("use_astrbot_default_persona").checked;
  $("btnSelectPersona").disabled = disabled;
  $("persona").disabled = disabled;
}

function confirmDialog(message) {
  return new Promise((resolve) => {
    const modal = $("confirmModal");
    $("confirmText").textContent = message;
    modal.classList.add("show");
    const ok = $("confirmOk");
    const cancel = $("confirmCancel");
    const finish = (result) => {
      modal.classList.remove("show");
      ok.removeEventListener("click", onOk);
      cancel.removeEventListener("click", onCancel);
      resolve(result);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    ok.addEventListener("click", onOk);
    cancel.addEventListener("click", onCancel);
  });
}

function renderStatus(status) {
  const pills = $("statusPills");
  pills.innerHTML = "";
  const ffmpegWarn = $("ffmpegWarn");
  if (ffmpegWarn) ffmpegWarn.style.display = status.ffmpeg_installed ? "none" : "block";
  const eff = $("effectiveModel");
  if (eff) eff.textContent = status.chat_model || status.model || "未配置";
  const effV = $("effectiveVisionModel");
  if (effV) effV.textContent = status.vision_model || "未配置";
  const items = [
    { label: "总开关", on: status.chat_enable },
    { label: "TTS 语音", on: status.tts_enable },
    { label: "ffmpeg", on: status.ffmpeg_installed },
    { label: "长期记忆", on: status.long_memory },
    { label: `人格 · ${status.persona_name || "未设置"}`, on: true },
    { label: "好感度", on: status.favorability },
  ];
  items.forEach((it) => {
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.innerHTML = `<span class="dot ${it.on ? "on" : "off"}"></span>${escapeHtml(it.label)}`;
    pills.appendChild(pill);
  });
}

// ===================== 人格库管理 =====================

function fillAstrbotPersonaSelect(selected, list) {
  const sel = $("astrbot_persona");
  sel.innerHTML = "";
  const follow = document.createElement("option");
  follow.value = "";
  follow.textContent = "跟随AstrBot配置文件当前人格";
  sel.appendChild(follow);
  (Array.isArray(list) ? list : []).forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.name || "(未命名)";
    sel.appendChild(opt);
  });
  if (selected) sel.value = selected;
}

function fillPersonaSelect(selected) {
  const sel = $("persona");
  sel.innerHTML = "";
  personas.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name}${p.description ? "（" + p.description + "）" : ""}`;
    sel.appendChild(opt);
  });
  if (selected) sel.value = selected;
  if (!sel.value && personas.length) sel.value = personas[0].id;
}

function updateCurrentPersonaName(name) {
  const el = $("currentPersonaName");
  if (el) el.textContent = name || "-";
}

function refreshCurrentPersonaName(config) {
  const c = config || {};
  astrbotCurrentPersonaName = c.astrbot_current_persona || "";
  if (c.use_astrbot_default_persona) {
    if (!c.astrbot_persona) {
      updateCurrentPersonaName(astrbotCurrentPersonaName || "跟随AstrBot配置（当前人格）");
      return;
    }
    const sel = $("astrbot_persona");
    updateCurrentPersonaName(sel && sel.value ? sel.value : astrbotCurrentPersonaName || "跟随AstrBot配置（当前人格）");
    return;
  }
  const pid = c.persona;
  const p = (Array.isArray(c.personas) ? c.personas : []).find((x) => x.id === pid);
  updateCurrentPersonaName(p ? p.name : "-");
}

function renderPersonas(current) {
  const list = $("personaList");
  if (!personas.length) {
    list.innerHTML = '<div class="empty">暂无人格，点击下方按钮新增</div>';
    return;
  }
  list.innerHTML = "";
  personas.forEach((p) => {
    const row = document.createElement("div");
    row.className = "persona-row";
    const badges = [];
    if (p.builtin) badges.push('<span class="badge">预设</span>');
    if (p.id === current) badges.push('<span class="badge current-badge">当前</span>');
    const delBtn = `<button class="btn danger small" data-del="${p.id}">删除</button>`;
    const editBtn = `<button class="btn secondary small" data-edit="${p.id}">编辑</button>`;
    row.innerHTML = `
      <div class="top">
        <div>
          <span class="pname">${escapeHtml(p.name)}${badges.join("")}</span>
          <div class="desc">${escapeHtml(p.description || "")}</div>
        </div>
        <div class="opts">${editBtn}${delBtn}</div>
      </div>`;
    list.appendChild(row);
  });
  list.querySelectorAll("[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => openPersonaForm(btn.dataset.edit));
  });
  list.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", () => deletePersona(btn.dataset.del));
  });
}

function openPersonaForm(id = null) {
  editingPersonaId = id;
  const form = $("personaForm");
  form.classList.add("show");
  if (id) {
    const p = personas.find((x) => x.id === id);
    if (p) {
      $("pf_name").value = p.name || "";
      $("pf_desc").value = p.description || "";
      $("pf_prompt").value = p.prompt || "";
    }
  } else {
    $("pf_name").value = "";
    $("pf_desc").value = "";
    $("pf_prompt").value = "";
  }
  $("pf_name").focus();
}

function closePersonaForm() {
  $("personaForm").classList.remove("show");
  editingPersonaId = null;
}

async function loadPersonas() {
  try {
    const data = await bridge.apiGet("personas");
    personas = (data && data.list) || [];
    fillPersonaSelect(data && data.current);
    renderPersonas(data && data.current);
    if ($("use_astrbot_default_persona").checked) {
      if (!$("astrbot_persona").value) {
        updateCurrentPersonaName(astrbotCurrentPersonaName || "跟随AstrBot配置（当前人格）");
      }
    } else {
      const p = personas.find((x) => x.id === (data && data.current));
      updateCurrentPersonaName(p ? p.name : "-");
    }
  } catch (e) {
    $("personaList").innerHTML = `<div class="empty">人格加载失败：${escapeHtml(e.message)}</div>`;
  }
}

async function deletePersona(id) {
  const p = personas.find((x) => x.id === id);
  const ok = await confirmDialog(`确定删除人格「${p ? p.name : id}」吗？`);
  if (!ok) return;
  try {
    await bridge.apiPost("personas/delete", { id });
    showToast("✅ 人格已删除");
    await Promise.all([loadPersonas(), loadStatus()]);
  } catch (e) {
    showToast("删除失败：" + e.message, true);
  }
}

// ===================== 配置 =====================

function collectConfig() {
  return {
    chat_model_enable: $("chat_model_enable").checked,
    custom_model_enable: $("custom_model_enable").checked,
    vision_model_enable: $("vision_model_enable").checked,
    api_base_url: $("api_base_url").value.trim(),
    api_key: $("api_key").value.trim(),
    chat_model: $("chat_model").value.trim(),
    vision_model: $("vision_model").value.trim(),
    persona: $("persona").value,
    hide_ai_identity: $("hide_ai_identity").checked,
    use_astrbot_default_persona: $("use_astrbot_default_persona").checked,
    astrbot_persona: $("astrbot_persona").value,
    enable_long_memory: $("enable_long_memory").checked,
    auto_save_memory: $("auto_save_memory").checked,
    group_image_reply: $("group_image_reply").checked,
    enable_emoji_analysis: $("enable_emoji_analysis").checked,
    enable_facial_expression: $("enable_facial_expression").checked,
    ignore_mention_others: $("ignore_mention_others").checked,
    enable_proactive_chat: $("enable_proactive_chat").checked,
    enable_favorability: $("enable_favorability").checked,
    enable_private_companion: $("enable_private_companion").checked,
    master_user_ids: ($("master_user_ids").value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    avoid_intimate_non_master: $("avoid_intimate_non_master").checked,
    tts_enable: $("tts_enable").checked,
    tts_mode: $("tts_mode").value,
    tts_voice: $("tts_voice").value,
    tts_speed: parseFloat($("tts_speed").value) || 1.0,
    tts_max_length: parseInt($("tts_max_length").value, 10) || 300,
    memory_recall_count: parseInt($("memory_recall_count").value, 10) || 3,
    session_expire_seconds: parseInt($("session_expire_seconds").value, 10) || 120,
    max_log: parseInt($("max_log").value, 10) || 14,
    on_thinking: $("on_thinking").value === "true",
    proactive_chat_frequency: parseInt($("proactive_chat_frequency").value, 10) || 10,
    favorability_default: parseInt($("favorability_default").value, 10) || 50,
  };
}

function fillVoices(selected) {
  const sel = $("tts_voice");
  sel.innerHTML = "";
  const list = ttsVoices.length ? ttsVoices : FALLBACK_TTS_VOICES;
  const groups = {};
  list.forEach((v) => {
    const g = v.group || (v.value.startsWith("zh-") ? "中国" : "国外");
    (groups[g] = groups[g] || []).push(v);
  });
  ["中国", "国外"].forEach((g) => {
    const arr = groups[g] || [];
    if (!arr.length) return;
    const og = document.createElement("optgroup");
    og.label = g;
    arr.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.value;
      opt.textContent = v.label || v.value;
      og.appendChild(opt);
    });
    sel.appendChild(og);
  });
  if (selected) sel.value = selected;
}

async function saveConfigKeys(keys, btn) {
  const all = collectConfig();
  const payload = {};
  keys.forEach((k) => {
    if (k in all) payload[k] = all[k];
  });
  btn.disabled = true;
  try {
    await bridge.apiPost("config/save", payload);
    showToast("✅ 配置已保存");
    loadStatus();
  } catch (e) {
    showToast("保存失败：" + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

function applyConfig(config) {
  $("api_base_url").value = config.api_base_url || config.chat_api_base_url || "";
  $("api_key").value = config.api_key || config.chat_api_key || "";
  $("chat_model").value = config.chat_model || "";
  $("vision_model").value = config.vision_model || "";
  setSwitch("chat_model_enable", config.chat_model_enable);
  setSwitch("custom_model_enable", config.custom_model_enable);
  setSwitch("vision_model_enable", config.vision_model_enable);
  updateCustomModelFields();
  if (Array.isArray(config.personas)) {
    personas = config.personas;
    fillPersonaSelect(config.persona);
    renderPersonas(config.persona);
  }
  setSwitch("hide_ai_identity", config.hide_ai_identity);
  setSwitch("use_astrbot_default_persona", config.use_astrbot_default_persona);
  fillAstrbotPersonaSelect(config.astrbot_persona, config.astrbot_personas);
  refreshCurrentPersonaName(config);
  syncPersonaSelectionDisabled();
  setSwitch("enable_long_memory", config.enable_long_memory);
  setSwitch("auto_save_memory", config.auto_save_memory);
  setSwitch("group_image_reply", config.group_image_reply);
  setSwitch("enable_emoji_analysis", config.enable_emoji_analysis);
  setSwitch("enable_facial_expression", config.enable_facial_expression);
  setSwitch("ignore_mention_others", config.ignore_mention_others);
  setSwitch("enable_proactive_chat", config.enable_proactive_chat);
  setSwitch("enable_favorability", config.enable_favorability);
  setSwitch("enable_private_companion", config.enable_private_companion);
  $("master_user_ids").value = (config.master_user_ids || []).join(",");
  setSwitch("avoid_intimate_non_master", config.avoid_intimate_non_master);
  if (Array.isArray(config.tts_voices)) {
    ttsVoices = config.tts_voices;
  }
  setSwitch("tts_enable", config.tts_enable);
  $("tts_mode").value = config.tts_mode || "text_voice";
  fillVoices(config.tts_voice);
  $("tts_speed").value = config.tts_speed || 1.0;
  $("tts_max_length").value = config.tts_max_length || 300;
  $("memory_recall_count").value = config.memory_recall_count || 3;
  $("session_expire_seconds").value = config.session_expire_seconds || 120;
  $("max_log").value = config.max_log || 14;
  $("on_thinking").value = config.on_thinking ? "true" : "false";
  $("proactive_chat_frequency").value = config.proactive_chat_frequency || 10;
  $("favorability_default").value = config.favorability_default || 50;
}

function updateCustomModelFields() {
  const enabled = $("custom_model_enable").checked;
  ["api_base_url", "api_key", "chat_model", "vision_model"].forEach((id) => {
    $(id).disabled = !enabled;
  });
  const btn = $("btnTestAstrbot");
  if (btn) btn.disabled = enabled;
}

async function loadStatus() {
  try {
    const status = await bridge.apiGet("status");
    renderStatus(status);
  } catch (e) {
    console.error(e);
    const eff = $("effectiveModel");
    if (eff) eff.textContent = "加载失败";
    const effV = $("effectiveVisionModel");
    if (effV) effV.textContent = "加载失败";
  }
}

// ===================== 记忆管理 =====================

async function refreshMemory() {
  try {
    const data = await bridge.apiGet("memory");
    renderMemory(data);
  } catch (e) {
    $("memoryList").innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

async function queryMemory() {
  const scope = $("mem_scope").value;
  const uid = $("mem_uid").value.trim();
  if (!uid) {
    showToast("请先填写用户ID/群ID", true);
    return;
  }
  try {
    const data = await bridge.apiGet("memory", { scope, uid });
    if (!Array.isArray(data) || data.length === 0) {
      $("memoryList").innerHTML = `<div class="empty">未查询到 ${scope === "group" ? "群" : "用户"} ${escapeHtml(uid)} 的长期记忆</div>`;
      return;
    }
    renderMemory(data);
  } catch (e) {
    $("memoryList").innerHTML = `<div class="empty">查询失败：${escapeHtml(e.message)}</div>`;
  }
}

function renderMemory(data) {
  const list = $("memoryList");
  if (!Array.isArray(data) || data.length === 0) {
    list.innerHTML = '<div class="empty">暂无长期记忆</div>';
    return;
  }
  list.innerHTML = "";
  data.forEach((user) => {
    const isGroup = user.scope === "group";
    const ownerLabel = isGroup
      ? escapeHtml(`群聊 · ${user.uid.replace(/^group_/, "")}`)
      : escapeHtml(`私聊 · ${user.uid.replace(/^user_/, "")}`);
    (user.items || []).forEach((item) => {
      const div = document.createElement("div");
      div.className = "memory-item";
      const timeStr = item.createTime
        ? new Date(item.createTime).toLocaleString()
        : "";
      div.innerHTML = `
          <div class="body">
            <div>${escapeHtml(item.content || "")}</div>
            <div class="uid">${ownerLabel}${timeStr ? " · " + escapeHtml(timeStr) : ""}</div>
          </div>
          <button class="btn danger small del" data-uid="${escapeHtml(user.uid)}" data-id="${escapeHtml(item.id || "")}">删除</button>`;
      list.appendChild(div);
    });
  });
  list.querySelectorAll(".del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ok = await confirmDialog("确定删除这条记忆吗？");
      if (!ok) return;
      try {
        await bridge.apiPost("memory/delete", {
          uid: btn.dataset.uid,
          id: btn.dataset.id,
        });
        showToast("✅ 记忆已删除");
        refreshMemory();
        loadStatus();
      } catch (e) {
        showToast("删除失败：" + e.message, true);
      }
    });
  });
}

// ===================== 好感度管理 =====================

async function refreshFavorability() {
  try {
    const scope = $("fav_scope").value;
    const data = await bridge.apiGet("favorability", { scope });
    renderFavorability(data);
  } catch (e) {
    $("favorabilityList").innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

async function queryFavorability() {
  const scope = $("fav_scope").value;
  const uid = $("fav_uid").value.trim();
  if (!uid) {
    showToast("请先填写用户ID/群ID", true);
    return;
  }
  try {
    const data = await bridge.apiGet("favorability", { scope, uid });
    if (!Array.isArray(data) || data.length === 0) {
      $("favorabilityList").innerHTML = `<div class="empty">未查询到 ${scope === "group" ? "群" : "用户"} ${escapeHtml(uid)} 的好感度</div>`;
      return;
    }
    renderFavorability(data);
  } catch (e) {
    $("favorabilityList").innerHTML = `<div class="empty">查询失败：${escapeHtml(e.message)}</div>`;
  }
}

function renderFavorability(data) {
  const list = $("favorabilityList");
  if (!Array.isArray(data) || data.length === 0) {
    list.innerHTML = '<div class="empty">暂无好感度记录</div>';
    return;
  }
  list.innerHTML = "";
  data.forEach((item) => {
    const div = document.createElement("div");
    div.className = "memory-item";
    const scopeLabel = item.scope === "group" ? "群聊" : "私聊";
    const ownerLabel = scopeLabel === "group"
      ? `群 · ${escapeHtml(item.uid)}`
      : `用户 · ${escapeHtml(item.uid)}`;
    div.innerHTML = `
        <div class="body">
          <div>${ownerLabel} · 好感度: ${escapeHtml(item.value)}</div>
          <div class="uid">
            <button class="btn small adjust" data-scope="${escapeHtml(item.scope)}" data-uid="${escapeHtml(item.uid)}" data-value="${escapeHtml(item.value)}">调整</button>
            <button class="btn small danger del" data-scope="${escapeHtml(item.scope)}" data-uid="${escapeHtml(item.uid)}">删除</button>
          </div>
        </div>
      `;
    list.appendChild(div);
  });
  list.querySelectorAll(".del").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const ok = await confirmDialog("确定删除这条好感度记录吗？");
      if (!ok) return;
      try {
        await bridge.apiPost("favorability/delete", {
          scope: btn.dataset.scope,
          uid: btn.dataset.uid,
        });
        showToast("✅ 好感度已删除");
        refreshFavorability();
      } catch (e) {
        showToast("删除失败：" + e.message, true);
      }
    });
  });
  list.querySelectorAll(".adjust").forEach((btn) => {
    btn.addEventListener("click", () => {
      const newValue = prompt(
        "请输入新的好感度值 (0-100):",
        btn.dataset.value
      );
      if (newValue === null) return;
      const num = parseInt(newValue.trim());
      if (isNaN(num) || num < 0 || num > 100) {
        showToast("好感度值必须在 0-100 之间", true);
        return;
      }
      (async () => {
        try {
          await bridge.apiPost("favorability/set", {
            scope: btn.dataset.scope,
            uid: btn.dataset.uid,
            value: num,
          });
          showToast("✅ 好感度已更新");
          refreshFavorability();
        } catch (e) {
          showToast("更新失败：" + e.message, true);
        }
      })();
    });
  });
}

// ===================== 底部菜单栏分页 =====================

function setupBottomNav() {
  const navItems = Array.from(document.querySelectorAll(".nav-item"));
  const views = Array.from(document.querySelectorAll(".view"));
  if (navItems.length === 0 || views.length === 0) return;

  const showView = (name) => {
    views.forEach((v) => v.classList.toggle("active", v.dataset.view === name));
    navItems.forEach((n) => n.classList.toggle("active", n.dataset.view === name));
    const target = views.find((v) => v.dataset.view === name);
    if (target) target.scrollIntoView({ block: "start" });
  };

  navItems.forEach((n) => n.addEventListener("click", () => showView(n.dataset.view)));
}

// ===================== 事件绑定 =====================

async function init() {
  setupBottomNav();
  context = await bridge.ready();
  document.title = bridge.t("pages.dashboard.title", "Edge_TTS");
  fillVoices();
  await Promise.all([loadStatus(), loadPersonas()]);
  try {
    const config = await bridge.apiGet("config");
    applyConfig(config);
  } catch (e) {
    showToast("加载配置失败：" + e.message, true);
  }
  refreshMemory();
}

const MODEL_KEYS = [
  "chat_model_enable",
  "custom_model_enable",
  "vision_model_enable",
  "api_base_url",
  "api_key",
  "chat_model",
  "vision_model",
];

const VOICE_KEYS = [
  "tts_enable",
  "tts_mode",
  "tts_voice",
  "tts_speed",
  "tts_max_length",
];



const MEMORY_KEYS = [
  "memory_recall_count",
  "group_image_reply",
  "enable_emoji_analysis",
  "enable_facial_expression",
  "ignore_mention_others",
  "enable_proactive_chat",
  "proactive_chat_frequency",
  "session_expire_seconds",
  "max_log",
  "on_thinking",
];

$("btnSaveModel").addEventListener("click", async () => {
  await saveConfigKeys(MODEL_KEYS, $("btnSaveModel"));
});

async function testModelStatus(target, btn) {
  btn.disabled = true;
  try {
    const res = await bridge.apiPost("model_status", { target });
    const items = res.items || [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const ok = Boolean(it.enabled && it.connected);
      if (ok) {
        showToast(`${it.name}：${it.message}`, false, true);
      } else {
        showToast(`${it.name}：${it.message}`, false, false, true);
      }
      if (i < items.length - 1) {
        await new Promise((r) => setTimeout(r, 1600));
      }
    }
  } catch (e) {
    showToast("测试失败：" + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

$("btnTestCustom").addEventListener("click", async () => {
  await testModelStatus("custom", $("btnTestCustom"));
});

$("btnTestAstrbot").addEventListener("click", async () => {
  await testModelStatus("astrbot", $("btnTestAstrbot"));
});

$("custom_model_enable").addEventListener("change", updateCustomModelFields);

const COMPANION_KEYS = [
  "enable_favorability",
  "favorability_default",
  "enable_private_companion",
  "master_user_ids",
  "avoid_intimate_non_master",
];

$("btnSaveCompanion").addEventListener("click", async () => {
  await saveConfigKeys(COMPANION_KEYS, $("btnSaveCompanion"));
});

$("btnSaveVoice").addEventListener("click", async () => {
  await saveConfigKeys(VOICE_KEYS, $("btnSaveVoice"));
});



$("btnSaveIdentity").addEventListener("click", async () => {
  await saveConfigKeys(
    ["persona", "hide_ai_identity", "use_astrbot_default_persona", "astrbot_persona"],
    $("btnSaveIdentity")
  );
});

$("btnSaveMemory").addEventListener("click", async () => {
  await saveConfigKeys(MEMORY_KEYS, $("btnSaveMemory"));
});

const LONGMEM_KEYS = ["enable_long_memory", "auto_save_memory"];

$("btnSaveLongMem").addEventListener("click", async () => {
  await saveConfigKeys(LONGMEM_KEYS, $("btnSaveLongMem"));
});

$("btnSelectPersona").addEventListener("click", async () => {
  const id = $("persona").value;
  if (!id) return;
  try {
    await bridge.apiPost("personas/select", { id });
    showToast("✅ 已切换当前人格");
    renderPersonas(id);
    loadStatus();
    const p = personas.find((x) => x.id === id);
    updateCurrentPersonaName(p ? p.name : "-");
  } catch (e) {
    showToast("切换失败：" + e.message, true);
  }
});

$("btnNewPersona").addEventListener("click", () => openPersonaForm());

$("btnSavePersonaConfig").addEventListener("click", async () => {
  await saveConfigKeys(
    ["persona", "hide_ai_identity", "use_astrbot_default_persona", "astrbot_persona"],
    $("btnSavePersonaConfig")
  );
  await loadPersonas();
  if ($("use_astrbot_default_persona").checked) {
    updateCurrentPersonaName($("astrbot_persona").value || astrbotCurrentPersonaName || "跟随AstrBot配置（当前人格）");
  } else {
    const p = personas.find((x) => x.id === $("persona").value);
    updateCurrentPersonaName(p ? p.name : "-");
  }
});

$("persona").addEventListener("change", () => {
  const p = personas.find((x) => x.id === $("persona").value);
  if (!$("use_astrbot_default_persona").checked) updateCurrentPersonaName(p ? p.name : "-");
});
$("astrbot_persona").addEventListener("change", () => {
  if ($("use_astrbot_default_persona").checked) {
    updateCurrentPersonaName($("astrbot_persona").value || astrbotCurrentPersonaName || "跟随AstrBot配置（当前人格）");
  }
});
$("use_astrbot_default_persona").addEventListener("change", () => {
  syncPersonaSelectionDisabled();
  if ($("use_astrbot_default_persona").checked) {
    updateCurrentPersonaName($("astrbot_persona").value || astrbotCurrentPersonaName || "跟随AstrBot配置（当前人格）");
  } else {
    const p = personas.find((x) => x.id === $("persona").value);
    updateCurrentPersonaName(p ? p.name : "-");
  }
});

$("btnCancelPersona").addEventListener("click", closePersonaForm);

$("btnSavePersona").addEventListener("click", async () => {
  const name = $("pf_name").value.trim();
  const description = $("pf_desc").value.trim();
  const prompt = $("pf_prompt").value.trim();
  if (!name || !prompt) {
    showToast("人格名字与设定 Prompt 不能为空", true);
    return;
  }
  try {
    if (editingPersonaId) {
      await bridge.apiPost("personas/update", {
        id: editingPersonaId,
        name,
        description,
        prompt,
      });
      showToast("✅ 人格已更新");
    } else {
      await bridge.apiPost("personas/add", { name, description, prompt });
      showToast("✅ 人格已新增");
    }
    closePersonaForm();
    await Promise.all([loadPersonas(), loadStatus()]);
  } catch (e) {
    showToast("保存人格失败：" + e.message, true);
  }
});

$("btnRefreshMemory").addEventListener("click", async () => {
  await refreshMemory();
  showToast("✅ 记忆列表已刷新");
});

$("btnQueryMemory").addEventListener("click", queryMemory);
$("mem_uid").addEventListener("keydown", (e) => {
  if (e.key === "Enter") queryMemory();
});

$("btnClearMemory").addEventListener("click", async () => {
  const ok = await confirmDialog("确定清空全部长期记忆吗？此操作不可恢复。");
  if (!ok) return;
  try {
    await bridge.apiPost("memory/clear", {});
    showToast("✅ 已清空全部长期记忆");
    refreshMemory();
    loadStatus();
  } catch (e) {
    showToast("清空失败：" + e.message, true);
  }
});

$("btnRefreshFavorability").addEventListener("click", async () => {
  await refreshFavorability();
  showToast("✅ 好感度列表已刷新");
});

$("btnSetFavorability").addEventListener("click", async () => {
  const scope = $("fav_scope").value;
  const uid = $("fav_uid").value.trim();
  const value = parseInt($("fav_value").value, 10);
  if (!uid) {
    showToast("请先填写用户ID/群ID", true);
    return;
  }
  if (isNaN(value) || value < 0 || value > 100) {
    showToast("好感度值必须在 0-100 之间", true);
    return;
  }
  try {
    await bridge.apiPost("favorability/set", { scope, uid, value });
    showToast("✅ 好感度已设置");
    $("fav_uid").value = "";
    $("fav_value").value = "";
    refreshFavorability();
  } catch (e) {
    showToast("设置失败：" + e.message, true);
  }
});

$("fav_scope").addEventListener("change", refreshFavorability);
$("fav_uid").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("btnSetFavorability").click();
});

$("btnClearFavorability").addEventListener("click", async () => {
  const scope = $("fav_scope").value;
  const scopeLabel = scope === "group" ? "群聊" : "私聊";
  const ok = await confirmDialog(`确定清空全部${scopeLabel}好感度吗？此操作不可恢复。`);
  if (!ok) return;
  try {
    await bridge.apiPost("favorability/clear", { scope });
    showToast("✅ 好感度已清空");
    refreshFavorability();
  } catch (e) {
    showToast("清空失败：" + e.message, true);
  }
});

init();
