import os
import time
import logging
from collections import defaultdict
from dotenv import load_dotenv
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from google import genai
import asyncio

load_dotenv()
logging.basicConfig(level=logging.DEBUG)

gemini_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))

@app.command("/anon")
async def handle_anonymous_command(ack, say, command, client):
    await ack()

    user_id = command["user_id"]
    user_message = command["text"]

    await say(f"{user_message}")

    await client.chat_postMessage(
        channel="C08NBRCUZBJ",
        text=f"Anonymous message sent by <@{user_id}>:\n{user_message}"
    )


@app.event("app_mention")
async def handle_sarcasm_command(ack, event, say, client):
    await ack()
    thread_ts = event.get("thread_ts")
    channel_id = event["channel"]
    user_message = event["text"]

    manual = gemini_client.files.upload(file="PA4.pdf")
    starter_code = gemini_client.files.upload(file="DHT.py")

    if thread_ts:
        response = await client.conversations_replies(channel=channel_id, ts=thread_ts)
        messages = response.get("messages", [])
    else:
        messages = [{"text": user_message}]

    thread_context = "\n".join([msg["text"] for msg in messages])

    ai_response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[f"""Generate a short, extremely sarcastic, relevant and funny response to this user. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382. The students will either have questions about the course or assignemnts. We will only ask you to generate sarcastic responses to the students who it seems like have either not read the assignment manual, watched the assignment tutorial, not been attending class lectures or consulting course material like the course LMS tab to view the relevant deadlines and materials. I have attached the assignment manual and starter code for your reference as well. Here is an example for you as well. User: Are we supposed to to implement the assignment in C++ or Java?
        You: Tsk tsk. Someone did not bother reading the manual. I guess you are not a fan of reading, huh? \n Here is the user message that you need to respond to:Generate a short, sarcastic, relevant and funny response based on the following conversation:\n{thread_context}""", manual, starter_code],
    )

    await say(text=ai_response.text, thread_ts=thread_ts or event["ts"])


import asyncio
from collections import defaultdict

MAX_CONCURRENT_REQUESTS = 10  # Tune this to avoid rate limits
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

async def fetch_replies(client, channel_id, ts):
    async with semaphore:
        try:
            replies = await client.conversations_replies(channel=channel_id, ts=ts)
            return replies.get("messages", [])
        except Exception as e:
            return []

async def fetch_user_info(client, user_id):
    async with semaphore:
        try:
            user_info = await client.users_info(user=user_id)
            return user_id, user_info["user"]["real_name"]
        except:
            return user_id, user_id

@app.command("/stat")
async def handle_channel_stats_command(ack, respond, command, client, logger):
    await ack()
    channel_id = command["channel_id"]
    await respond("Fetching stats for this channel... ⏳")
    logger.info(f"Fetching stats for channel: {channel_id}")

    user_message_count = defaultdict(int)
    msg_cursor = None
    all_messages = []

    while True:
        try:
            history = await client.conversations_history(channel=channel_id, limit=200, cursor=msg_cursor)
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
        await asyncio.sleep(1) # rate limit cuz i was hitting errors with slack api. i also reduced limit to 100 for this reason

    thread_tasks = []
    for msg in all_messages:
        if "user" in msg:
            user_message_count[msg["user"]] += 1
        if msg.get("thread_ts") and msg.get("reply_count", 0) > 0:
            thread_tasks.append(fetch_replies(client, channel_id, msg["ts"]))

    all_replies = await asyncio.gather(*thread_tasks)
    for replies in all_replies:
        for reply in replies:
            if "user" in reply:
                user_message_count[reply["user"]] += 1

    unique_user_ids = list(user_message_count.keys())
    user_info_tasks = [fetch_user_info(client, uid) for uid in unique_user_ids]
    user_names = dict(await asyncio.gather(*user_info_tasks))

    user_stats = [{"User ID": uid, "Name": user_names[uid], "Messages": count}
                  for uid, count in user_message_count.items()]
    user_stats.sort(key=lambda x: x["Messages"], reverse=True)
    top_contributors = user_stats[:10]

    leaderboard = "*🏆 Top Contributors in This Channel:*\n"
    for u in top_contributors:
        leaderboard += f"> *{u['Name']}*: {u['Messages']} messages\n"

    await respond(leaderboard)


@app.command("/stat")
async def handle_channel_stats_command(ack, respond, command, client, logger):
    await ack()
    channel_id = command["channel_id"]
    await respond("Fetching stats for this channel... this might take a moment ⏳")
    logger.info(f"Fetching stats for channel: {channel_id}")

    user_message_count = defaultdict(int)
    msg_cursor = None

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

        logger.info(f"Fetched {len(messages)} messages from channel {channel_id}")

        for msg in messages:
            if "user" in msg:
                user_message_count[msg["user"]] += 1
            # we also need to individually get replies to each message
            if msg.get("thread_ts") and msg.get("reply_count", 0) > 0:
                try:
                    replies = await client.conversations_replies(channel=channel_id, ts=msg["ts"])
                    for reply in replies.get("messages", []):
                        if "user" in reply:
                            user_message_count[reply["user"]] += 1
                except Exception as e:
                    logger.warning(f"Skipping thread replies due to: {e}")

        msg_cursor = history.get("response_metadata", {}).get("next_cursor")
        if not msg_cursor:
            break
        await asyncio.sleep(2)

    user_stats = []
    for user_id, count in user_message_count.items():
        try:
            user_info = await client.users_info(user=user_id)
            username = user_info["user"]["real_name"]
        except Exception:
            username = user_id
        user_stats.append({"User ID": user_id, "Name": username, "Messages": count})

    user_stats.sort(key=lambda x: x["Messages"], reverse=True)
    top_contributors = user_stats[:10]

    leaderboard = "*🏆 Top Contributors in This Channel:*\n"
    for u in top_contributors:
        leaderboard += f"> *{u['Name']}*: {u['Messages']} messages\n"

    await respond(leaderboard)


@app.error
async def custom_error_handler(error, body, logger):
    logger.exception(f"Error: {error}")
    logger.info(f"Request body: {body}")


async def main():
    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())