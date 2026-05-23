# astrbot-plugin-mcrss

AstrBot 的 Minecraft (Java/基岩) 版本更新监控与自动推送插件 / An AstrBot plugin for monitoring Minecraft updates.

> [!NOTE]
> This repo is a plugin of [AstrBot](https://github.com/AstrBotDevs/AstrBot).
> 
> [AstrBot](https://github.com/AstrBotDevs/AstrBot) is an agentic assistant for both personal and group conversations. It can be deployed across dozens of mainstream instant messaging platforms, including QQ, Telegram, Feishu, DingTalk, Slack, LINE, Discord, Matrix, etc. In addition, it provides a reliable and extensible conversational AI infrastructure for individuals, developers, and teams. Whether you need a personal AI companion, an intelligent customer support agent, an automation assistant, or an enterprise knowledge base, AstrBot enables you to quickly build AI applications directly within your existing messaging workflows.

## ✨ 功能特点

- **双端版本监控**：
  - **Java 版**：通过 Mojang 官方 API 监控 Release (正式版) 与 Snapshot (快照版)。
  - **基岩版**：通过抓取 Google Play 页面数据，监控基岩版正式版更新。
- **更新日志抓取**：除了推送版本号，还会自动解析官网对应文章的标题与更新日志链接。
- **时区转换**：自动将官方 API 返回的 ISO 时间转换为 UTC+8 (北京时间)。
- **支持网络代理**：内置代理配置项，方便国内服务器访问 Google Play 等境外接口。
- **稳定性与数据保护**：
  - **减少 I/O**：使用内存缓存机制，避免频繁读写硬盘。
  - **防数据损坏**：写入 JSON 数据时采用临时文件再原子替换的方式，防止意外中断或重启导致文件清空损坏。
  - **并发控制**：使用异步锁防止后台定时检查与手动触发检查同时运行，避免重复推送。

## 📥 安装与配置

1. 确保环境已安装所需的 Python 依赖库：
   ```bash
   pip install aiohttp beautifulsoup4 google-play-scraper
   ```
2. 将本项目克隆或下载到 AstrBot 的 `data/plugins/` 目录下。
3. 重启 AstrBot 即可加载插件。

## 💻 指令列表

| 指令 | 参数 | 说明 |
| :--- | :--- | :--- |
| `/mcsub` | `mcv` 或 `mcbv` | 在当前会话（群聊/私聊）订阅 Java 版 (mcv) 或基岩版 (mcbv) 推送。 |
| `/mcunsub` | `mcv` 或 `mcbv` | 取消当前会话的对应推送订阅。 |
| `/mclatest` | 无 | 快速查询当前的最新版本号（无缓存，直接返回本地记录的最新值）。 |
| `/mccheck` | 无 | 手动强制触发一次更新检查。 |
| `/mcsubtest` | 无 | **连通性测试**：一键检查机器人的网络状态、API 连通性以及爬虫解析是否正常。 |

## ⚙️ 插件设置

在 AstrBot 的控制面板中，你可以对本插件进行配置：
- `check_interval` (整数): 检查更新的频率，单位为秒，默认为 `60`。
- `proxy` (字符串): 网络代理地址，用于解决网络受限问题。
  - 示例：`http://127.0.0.1:7890`

# Supports

- [AstrBot Repo](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot Plugin Development Docs (Chinese)](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot Plugin Development Docs (English)](https://docs.astrbot.app/en/dev/star/plugin-new.html)

## 鸣谢 / Acknowledgments

* 本项目中的 [某某功能] 灵感来源于 [akari-bot](https://github.com/Teahouse-Studios/akari-bot)，参考了其原有的业务逻辑并针对 AstrBot 框架进行了重写。感谢 Teahouse-Studios 团队的优秀开源工作！