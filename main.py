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

    if thread_ts:
        response = await client.conversations_replies(channel=channel_id, ts=thread_ts)
        messages = response.get("messages", [])
    else:
        messages = [{"text": user_message}]

    thread_context = "\n".join([msg["text"] for msg in messages])

    ai_response = gemini_client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""Generate a short, extremely sarcastic and funny response to this user. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382. The students will either have questions about the course or assignemnts. We will only ask you to generate sarcastic responses to the students who it seems like have either not read the assignment manual, watched the assignment tutorial, not been attending class lectures or consulting course material like the course LMS tab to view the relevant deadlines and materials. Here is an example for you as well. User: Are we supposed to to implement the assignment in C++ or Java?
        You: Tsk tsk. Someone did not bother reading the manual. I guess you are not a fan of reading, huh? \n Here is the user message that you need to respond to:Generate a short, sarcastic and funny response based on the following conversation:\n{thread_context}"""
    )

    await say(text=ai_response.text, thread_ts=thread_ts or event["ts"])


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