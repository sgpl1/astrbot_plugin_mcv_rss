# --------------------------------------------------------
# 此功能的实现思路与部分逻辑参考了 Teahouse-Studios/akari-bot 项目。
# 原项目基于 graia 框架构建，采用 AGPL-3.0 协议。
# 特此向原作者致谢！
# 原项目地址: https://github.com/Teahouse-Studios/akari-bot
# ------

import re
import os
import json
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from google_play_scraper import app as google_play_scraper

from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent

# 定义正则匹配模式
SNAPSHOT_PATTERN = re.compile(r"^(?P<major>[\d.]+)-snapshot-?(?P<patch>\d)+$")
OLD_SNAPSHOT_PATTERN = re.compile(r"^(1\d)|(2[0-5])[w|W]\d{2}[A-Fa-f]$")
PRERELEASE_PATTERN = re.compile(r"^(?P<major>[\d.]+)-pre-?(?P<patch>\d)+$")
RELEASE_CANDIDATE_PATTERN = re.compile(r"^(?P<major>[\d.]+)-rc-?(?P<patch>\d)+$")
RELEASE_PATTERN = re.compile(r"^\d{1,2}\.\d+(\.\d+)?$")

CHANGELOG_URL_PREFIX = "https://www.minecraft.net/en-us/article/minecraft"
UTC8 = timezone(timedelta(hours=8))

def get_changelog_url(version: str) -> str:
    if m := re.match(SNAPSHOT_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-{m.group('major').replace('.', '-')}{m.group('patch')}"
    if m := re.match(PRERELEASE_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-{m.group('major').replace('.', '-')}-pre-release-{m.group('patch')}"
    if m := re.match(RELEASE_CANDIDATE_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-{m.group('major').replace('.', '-')}-release-candidate-{m.group('patch')}"
    if re.match(RELEASE_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-java-edition-{version.replace('.', '-')}"
    if re.match(OLD_SNAPSHOT_PATTERN, version):
        return f"{CHANGELOG_URL_PREFIX}-snapshot-{version}"
    return ""

@register("minecraft_rss", "TokiFloat", "Minecraft 版本更新监控推送", "1.0.0", "mcrss")
class MinecraftRSS(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.base_path = "data/mcrss_storage"
        if not os.path.exists(self.base_path): 
            os.makedirs(self.base_path)
            
        self.subs_file = os.path.join(self.base_path, "mc_subs.json")
        self.mcv_file = os.path.join(self.base_path, "mcv_rss_list.json")
        self.news_file = os.path.join(self.base_path, "mcnews_list.json")
        self.mcbv_file = os.path.join(self.base_path, "mcbv_rss_list.json")
        
        self.subs = self._get_stored_data(self.subs_file, {"mcv": [], "mcbv": []})
        self.verlist_mcv = self._get_stored_data(self.mcv_file, [])
        self.newslist = self._get_stored_data(self.news_file, [])
        self.verlist_mcbv = self._get_stored_data(self.mcbv_file, [])
        
        plugin_config = self.context.get_config() or {}
        self.check_interval = plugin_config.get("check_interval", 60)
        
        # 【新功能】支持代理。解决国内服务器无法访问 Google Play 的问题
        self.proxy = plugin_config.get("proxy", "") 
        if self.proxy:
            os.environ["HTTP_PROXY"] = self.proxy
            os.environ["HTTPS_PROXY"] = self.proxy
            print(f"[MCRSS] 已启用全局网络代理: {self.proxy}")
        
        # 【新功能】防撞车并发锁
        self._check_lock = asyncio.Lock()
        
        self.task = asyncio.create_task(self._rss_loop())

    def _get_stored_data(self, filename, default):
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e: 
                print(f"[MCRSS] 读取文件 {filename} 失败: {e}")
        return default

    # 【优化】安全的文件写入机制 (防断电/重启导致 JSON 清空)
    def _update_stored_data(self, filename, data):
        temp_filename = f"{filename}.tmp"
        try:
            with open(temp_filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_filename, filename) # 原子级替换
        except Exception as e:
            print(f"[MCRSS] 写入文件 {filename} 失败: {e}")

    @filter.command("mcsub")
    async def mcsub(self, event: AstrMessageEvent, mc_type: str = ""):
        if mc_type not in ["mcv", "mcbv"]:
            yield event.plain_result("用法: /mcsub mcv 或 mcbv")
            return
        
        umo = event.unified_msg_origin
        if umo not in self.subs[mc_type]:
            self.subs[mc_type].append(umo)
            self._update_stored_data(self.subs_file, self.subs)
            yield event.plain_result(f"✅ 成功订阅 Minecraft {'Java版' if mc_type == 'mcv' else '基岩版'} 更新推送！")
        else:
            yield event.plain_result("您已经订阅过该推送啦。")

    @filter.command("mcunsub")
    async def mcunsub(self, event: AstrMessageEvent, mc_type: str = ""):
        if mc_type not in ["mcv", "mcbv"]:
            yield event.plain_result("用法: /mcunsub mcv 或 mcbv")
            return
            
        umo = event.unified_msg_origin
        if umo in self.subs[mc_type]:
            self.subs[mc_type].remove(umo)
            self._update_stored_data(self.subs_file, self.subs)
            yield event.plain_result(f"❌ 已取消 {'Java版' if mc_type == 'mcv' else '基岩版'} 推送。")
        else:
            yield event.plain_result("尚未订阅过该推送。")

    # 【新功能】快速查询当前最新版本
    @filter.command("mclatest")
    async def mclatest(self, event: AstrMessageEvent):
        msg = "【Minecraft 当前最新版本】\n"
        
        # 提取 Java 版最新（通常最后两个一个是正式版，一个是快照）
        latest_mcv = self.verlist_mcv[-2:] if len(self.verlist_mcv) >= 2 else self.verlist_mcv
        if latest_mcv:
            msg += f"☕ Java版: {', '.join(latest_mcv)}\n"
        else:
            msg += "☕ Java版: 暂无记录\n"
            
        # 提取基岩版最新
        if self.verlist_mcbv:
            msg += f"📱 基岩版(Google Play): {self.verlist_mcbv[-1]}\n"
        else:
            msg += "📱 基岩版: 暂无记录\n"
            
        yield event.plain_result(msg.strip())

    # 【新功能】手动触发检查
    @filter.command("mccheck")
    async def mccheck(self, event: AstrMessageEvent):
        yield event.plain_result("⏳ 正在手动拉取最新状态...")
        await self._perform_checks()
        yield event.plain_result("✅ 手动检查完毕！如果有更新，已经推送到相关群聊。")

    @filter.command("mcsubtest")
    async def mcsubtest(self, event: AstrMessageEvent):
        yield event.plain_result("⏳ 开始测试各项模块，可能需要几秒钟，请稍候...")
        
        report = ["【MCRSS 模块连通性测试报告】"]
        mcv_count = len(self.subs.get('mcv', []))
        mcbv_count = len(self.subs.get('mcbv', []))
        report.append(f"📁 本地存储: 正常 (当前订阅数 mcv:{mcv_count}, mcbv:{mcbv_count})")
        
        try:
            # 兼容代理
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get("https://piston-meta.mojang.com/mc/game/version_manifest.json", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        latest_release = data["latest"]["release"]
                        report.append(f"🟢 Java版 API: 正常 (获取到最新正式版: {latest_release})")
                        link, title = await self.get_article(session, latest_release)
                        if link: report.append(f"🟢 官网日志爬虫: 正常 (抓取标题: {title})")
                        else: report.append(f"🟡 官网日志爬虫: 暂无文章或结构改变")
                    else:
                        report.append(f"🔴 Java版 API: 异常 (HTTP {resp.status})")
        except Exception as e:
            report.append(f"🔴 Java版 API 测试出错: {e}")
            
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: google_play_scraper("com.mojang.minecraftpe"))
            version = result.get("version")
            if version: report.append(f"🟢 基岩版(Google Play): 正常 (版本: {version})")
            else: report.append(f"🔴 基岩版(Google Play): 未获取到版本号")
        except Exception as e:
            report.append(f"🔴 基岩版爬虫出错 (如果国内服务器且未配置代理，此为正常现象): {e}")
            
        push_t = datetime.now(UTC8).strftime('%Y-%m-%d %H:%M:%S')
        report.append(f"\n🕒 测试完成时间: {push_t}")
        yield event.plain_result("\n".join(report))

    async def get_article(self, session: aiohttp.ClientSession, version: str):
        link = get_changelog_url(version)
        if not link: return "", ""
        try:
            async with session.get(link, timeout=10) as resp:
                if resp.status == 200:
                    soup = BeautifulSoup(await resp.text(), "html.parser")
                    title = soup.find("h1")
                    if title and title.text.strip() != "404":
                        return link, title.text.strip()
        except Exception as e: 
            print(f"[MCRSS] 获取文章 {version} 失败: {e}")
        return "", ""

    async def _rss_loop(self):
        await asyncio.sleep(5)
        while True:
            await self._perform_checks()
            await asyncio.sleep(self.check_interval)
            
    async def _perform_checks(self):
        # 加上并发锁，防止后台 loop 和前台 /mccheck 撞车导致发两条一样的内容
        if self._check_lock.locked():
            return
        async with self._check_lock:
            try:
                await self._check_mcv()
                await self._check_mcbv()
            except Exception as e:
                print(f"[MCRSS] 检查任务异常: {e}")

    async def _check_mcv(self):
        url = "https://piston-meta.mojang.com/mc/game/version_manifest.json"
        
        # trust_env=True 允许 aiohttp 使用我们上面设置的环境变量代理
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200: return
                    data = await resp.json()
            except Exception as e: 
                print(f"[MCRSS] 请求 Java 版清单失败: {e}")
                return

            targets = [
                (data["latest"]["release"], "release"),
                (data["latest"]["snapshot"], "snapshot")
            ]

            for version, v_type in targets:
                if version not in self.verlist_mcv:
                    time_ver_str = next((v["releaseTime"] for v in data["versions"] if v["id"] == version), None)
                    if time_ver_str:
                        try:
                            dt = datetime.fromisoformat(time_ver_str)
                            rec_t = dt.astimezone(UTC8).strftime('%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            rec_t = "未知"
                    else:
                        rec_t = "未知"
                        
                    v_name = "正式版" if v_type == "release" else "快照"
                    push_t = datetime.now(UTC8).strftime('%Y-%m-%d %H:%M:%S')
                    msg = f"🚀 启动器已更新 {version} {v_name}。\n更新时间：{rec_t}\n推送时间：{push_t}"
                    
                    await self._broadcast("mcv", msg)
                    self.verlist_mcv.append(version)
                    self._update_stored_data(self.mcv_file, self.verlist_mcv)

                    link, title = await self.get_article(session, version)
                    if link and title not in self.newslist:
                        self.newslist.append(title)
                        self._update_stored_data(self.news_file, self.newslist)
                        await self._broadcast("mcv", f"📰 更新日志: {title}\n版本: {version}\n链接: {link}")

    async def _check_mcbv(self):
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: google_play_scraper("com.mojang.minecraftpe"))
            version = result.get("version")
            if version and version not in self.verlist_mcbv:
                push_t = datetime.now(UTC8).strftime('%Y-%m-%d %H:%M:%S')
                await self._broadcast("mcbv", f"📱 Google Play 商店已更新基岩版 {version} 正式版。\n推送时间：{push_t}")
                
                self.verlist_mcbv.append(version)
                self._update_stored_data(self.mcbv_file, self.verlist_mcbv)
        except Exception as e:
            # 记录日志但不终止，因为网络波动是常态
            pass

    async def _broadcast(self, mc_type, message_text):
        target_subs = self.subs.get(mc_type, [])
        for umo in target_subs:
            try:
                chain = MessageChain().message(message_text)
                await self.context.send_message(umo, chain)
                print(f"[MCRSS] 发送成功 -> {umo}")
            except Exception as e:
                print(f"[MCRSS] 发送失败 -> {umo}, 原因: {e}")