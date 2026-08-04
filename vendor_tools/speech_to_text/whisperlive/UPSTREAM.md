# WhisperLive 上游信息

- Repository: https://github.com/collabora/WhisperLive
- Purpose: 近实时 Whisper 麦克风/音频转写服务。
- Initial integration strategy: 作为独立进程、容器或 checkout 运行，由本项目 Adapter 连接。
- Version pin: 实施时固定具体 tag 或 commit，不跟随浮动 main。
- Backend candidate: faster-whisper。

实施阶段需要补充：

- 选定 commit；
- Python/CUDA/CPU 要求；
- 启动命令；
- 本地端口；
- 许可证文本或链接；
- 是否有本地补丁。
