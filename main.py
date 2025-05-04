import os
import time
import logging
import asyncio
from collections import defaultdict
from utils import *
from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from google import genai
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))


async def fetch_replies(client, channel_id: str, ts: str):
    async with semaphore:
        try:
            replies = await client.conversations_replies(channel=channel_id, ts=ts)
            return replies.get("messages", [])
        except Exception as e:
            logger.warning(f"Error fetching replies: {e}")
            return []


async def fetch_user_info(client, user_id: str) -> Tuple[str, str]:
    async with semaphore:
        try:
            user_info = await client.users_info(user=user_id)
            return user_id, user_info["user"]["real_name"]
        except Exception:
            return user_id, user_id


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=3, min=30, max=100))
@app.command("/anon")
async def handle_anonymous_command(ack, say, command, client):
    await ack()
    user_id = command["user_id"]
    user_message = command["text"]

    await say(user_message)
    await client.chat_postMessage(
        channel=ADMIN_CHANNEL,
        text=f"Anonymous message sent by <@{user_id}>:\n{user_message}"
    )


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=60, max=200))
@sleep_and_retry
@limits(calls=5, period=60)
@app.command("/sarcasm")
async def handle_sarcasm_command(ack, say, command):
    await ack()
    user_message = command["text"]
    prompt = build_sarcasm_prompt(user_message, gemini_client)
    await say("Generating a sarcastic response... ⏳")
    ai_response = gemini_client.models.generate_content(
        model=MODEL_SARCASM,
        contents=prompt
    )
    await say(text=ai_response.text)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=60, max=200))
@sleep_and_retry
@limits(calls=5, period=60)
@app.command("/help")
async def handle_help_command(ack, say, command):
    await ack()
    user_message = command["text"]
    prompt = build_help_prompt(user_message, gemini_client)
    await respond("Fetching help... ⏳")
    ai_response = gemini_client.models.generate_content(
        model=MODEL_HELPFUL,
        contents=prompt
    )
    await say(text=ai_response.text)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=60, max=200))
@sleep_and_retry
@limits(calls=5, period=60)
@app.command("/stat")
async def handle_channel_stats_command(ack, respond, command, client):
    await ack()
    channel_id = command["channel_id"]
    await respond("Fetching stats for this channel... ⏳")
    logger.info(f"Fetching stats for channel: {channel_id}")

    user_message_count = defaultdict(int)
    msg_cursor = None
    all_messages = []

    while True:
        try:
            history = await client.conversations_history(channel=channel_id, limit=100, cursor=msg_cursor)
        except Exception as e:
            logger.error(f"Error fetching history: {e}")
            await respond(f"Failed to fetch messages: {e}")
            return

        messages = history.get("messages", [])
        if not messages:
            break

        all_messages.extend(messages)
        msg_cursor = history.get("response_metadata", {}).get("next_cursor")
        if not msg_cursor:
            break
        # await asyncio.sleep(1)

    thread_tasks = [
        fetch_replies(client, channel_id, msg["ts"])
        for msg in all_messages if "thread_ts" in msg and msg.get("reply_count", 0) > 0
    ]

    all_replies = await asyncio.gather(*thread_tasks)
    for msg in all_messages + [r for thread in all_replies for r in thread]:
        if "user" in msg:
            user_message_count[msg["user"]] += 1

    user_info = dict(await asyncio.gather(*[fetch_user_info(client, uid) for uid in user_message_count]))
    leaderboard = "*🏆 Top Contributors in This Channel:*\n"
    for uid, count in sorted(user_message_count.items(), key=lambda x: x[1], reverse=True)[:10]:
        leaderboard += f"> *{user_info[uid]}*: {count} messages\n"

    await respond(leaderboard)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=60, max=200))
@app.event("app_mention")
async def handle_app_mentions(ack, event, say, client):
    await ack()
    user_message = event["text"]
    channel_id = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])

    if thread_ts:
        response = await client.conversations_replies(channel=channel_id, ts=thread_ts)
        messages = response.get("messages", [])
        thread_context = "\n".join([msg["text"] for msg in messages])
    else:
        thread_context = user_message

    if "sarcasm" in user_message.lower():
        prompt = build_sarcasm_prompt(thread_context, gemini_client)
        ai_response = gemini_client.models.generate_content(
            model=MODEL_SARCASM, contents=prompt)
    else:
        prompt = build_help_prompt(thread_context, gemini_client)
        ai_response = gemini_client.models.generate_content(
            model=MODEL_HELPFUL, contents=prompt)

    await say(text=ai_response.text, thread_ts=thread_ts)


@app.error
async def custom_error_handler(error, body, logger):
    logger.exception(f"Error: {error}")
    logger.info(f"Request body: {body}")


async def main():
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(main())
