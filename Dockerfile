# Edge_TTS 插件 Docker 适配
# 基于 AstrBot 官方镜像，显式安装 ffmpeg（语音发送依赖）与本插件 Python 依赖，
# 确保任意 tag 的官方镜像开箱即用（部分官方镜像 tag 未内置 ffmpeg）。
FROM soulter/astrbot:latest

# 幂等安装 ffmpeg：若基础镜像已内置则跳过
RUN if ! command -v ffmpeg >/dev/null 2>&1; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ffmpeg \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# 补齐本插件 Python 依赖（edge-tts / httpx 等，均为跨平台纯 Python 包）
RUN pip install --no-cache-dir -r requirements.txt
