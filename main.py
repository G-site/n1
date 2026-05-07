import asyncio
import hashlib
import hmac
import os
import xml.etree.ElementTree as ET

import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# =========================
# ENV
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")

CALLBACK_URL = os.getenv("CALLBACK_URL")

SECRET = os.getenv("SECRET", "super_secret")

PORT = int(os.getenv("PORT", 8080))

# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()

last_video_id = None

# =========================
# WEB SUB
# =========================

async def subscribe():
    hub_url = "https://pubsubhubbub.appspot.com/subscribe"

    topic = (
        "https://www.youtube.com/xml/feeds/videos.xml"
        f"?channel_id={YOUTUBE_CHANNEL_ID}"
    )

    data = {
        "hub.mode": "subscribe",
        "hub.topic": topic,
        "hub.callback": CALLBACK_URL,
        "hub.verify": "async",
        "hub.secret": SECRET,
        "hub.lease_seconds": "864000"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(hub_url, data=data) as resp:
            print("SUBSCRIBE:", resp.status)
            print(await resp.text())

# =========================
# CALLBACK
# =========================

async def callback(request: web.Request):
    global last_video_id

    # verification
    if request.method == "GET":
        challenge = request.query.get("hub.challenge")

        if challenge:
            print("VERIFIED")
            return web.Response(text=challenge)

        return web.Response(text="OK")

    # new video
    body = await request.read()

    signature = request.headers.get("X-Hub-Signature", "")

    if signature.startswith("sha1="):
        received = signature.split("=")[1]

        calculated = hmac.new(
            SECRET.encode(),
            body,
            hashlib.sha1
        ).hexdigest()

        if received != calculated:
            print("BAD SIGNATURE")
            return web.Response(status=403)

    xml = body.decode("utf-8")

    root = ET.fromstring(xml)

    namespace = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015"
    }

    entry = root.find("atom:entry", namespace)

    if entry is None:
        return web.Response(text="No video")

    video_id = entry.find("yt:videoId", namespace).text
    title = entry.find("atom:title", namespace).text

    if video_id == last_video_id:
        return web.Response(text="Duplicate")

    last_video_id = video_id

    video_url = f"https://youtu.be/{video_id}"

    text = (
        f"🎬 <b>Новое видео!</b>\n\n"
        f"📌 {title}\n"
        f"🔗 {video_url}"
    )

    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text
        )

        print("MESSAGE SENT")

    except Exception as e:
        print("SEND ERROR:", e)

    return web.Response(text="OK")

# =========================
# SERVER
# =========================

async def start_server():
    app = web.Application()

    app.router.add_get("/callback", callback)
    app.router.add_post("/callback", callback)

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    print(f"SERVER STARTED ON {PORT}")

# =========================
# MAIN
# =========================

async def main():
    await start_server()

    await asyncio.sleep(2)

    await subscribe()

    print("BOT STARTED")

    while True:
        await asyncio.sleep(3600)

# =========================

if __name__ == "__main__":
    asyncio.run(main())
