import os
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
import requests
from google.genai import types
import random
import json

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
api_keys = os.environ.get("GEMINI_API_KEY").split(",")

app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))


def get_random_gemini_client():
    key = random.choice(api_keys)
    return genai.Client(api_key=key)

# proactive throttliing


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


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=60, max=200))
def get_images(messages):
    headers = {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}
    image_parts = []

    for msg in messages:
        for file in msg.get("files", []):
            url = file.get("url_private")
            if file.get("mimetype", "").startswith("image/") and url:
                resp = requests.get(url, headers=headers)
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "")
                if content_type.startswith("image/"):
                    part = types.Part.from_bytes(
                        data=resp.content, mime_type=content_type)
                    image_parts.append(part)
                    logger.info(f"Downloaded image from {url}")
                else:
                    logger.warning(
                        f"Skipped non-image content: {content_type} from {url}")
    return image_parts


async def open_anonymous_post_modal(client, trigger_id, user_id, initial_text, channel_id):
    rich_text_input_element = {
        "type": "rich_text_input",
        "action_id": "message_input",
        "placeholder": {"type": "plain_text", "text": "Your anonymous message..."}
    }

    if initial_text:
        rich_text_input_element["initial_value"] = {
            "type": "rich_text",
            "elements": [
                {
                    "type": "rich_text_section",
                    "elements": [
                        {
                            "type": "text",
                            "text": initial_text,
                        }
                    ]
                }
            ]
        }

    await client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "callback_id": "anonymous_post_modal_with_files",
            "title": {"type": "plain_text", "text": "Create Anonymous Post"},
            "submit": {"type": "plain_text", "text": "Post Anonymously"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "message_block",
                    "element": rich_text_input_element,
                    "label": {"type": "plain_text", "text": "Message"}
                },
                {
                    "type": "input",
                    "block_id": "file_upload_block",
                    "label": {"type": "plain_text", "text": "Upload Files (Images, PDFs, or MP4s)"},
                    "element": {
                        "type": "file_input",
                        "action_id": "file_upload_action",
                        "max_files": 10,
                        "filetypes": ["jpg", "jpeg", "png", "gif", "pdf", "mp4"]
                    },
                    "optional": True
                }
            ],
            "private_metadata": json.dumps({"user_id": user_id, "channel_id": channel_id})
        }
    )


@app.command("/anon")
async def handle_anonymous_command(ack, command, client):
    await ack()
    user_id = command["user_id"]
    initial_text = command.get("text", "")
    trigger_id = command["trigger_id"]
    channel_id = command["channel_id"]

    await open_anonymous_post_modal(client, trigger_id, user_id, initial_text, channel_id)


@app.view("anonymous_post_modal_with_files")
async def handle_anonymous_post_modal_submission(ack, body, client, view):
    await ack()

    metadata = json.loads(view["private_metadata"])
    original_user_id = metadata.get("user_id")
    original_channel_id = metadata.get("channel_id")

    values = view["state"]["values"]
    rich_text_value = values.get("message_block", {}).get(
        "message_input", {}).get("rich_text_value", {})

    try:
        await client.chat_postMessage(
            channel=original_channel_id,
            blocks=[
                {
                    "type": "rich_text",
                    "elements": rich_text_value["elements"]
                }
            ],
            text="Anonymous message"
        )
        admin_msg = f"Anonymous post by <@{original_user_id}> in <#{original_channel_id}>"
        await client.chat_postMessage(channel=ADMIN_CHANNEL, text=admin_msg)
        await client.chat_postMessage(channel=ADMIN_CHANNEL, blocks=[
            {
                "type": "rich_text",
                "elements": rich_text_value["elements"]
            }
        ],
            text=admin_msg)
    except:
        logger.exception("Failed to post anonymous message")
        await client.chat_postMessage(
            channel=original_user_id,
            text="Error posting your anonymous message."
        )

    uploaded_files_info = values.get("file_upload_block", {}).get(
        "file_upload_action", {}).get("files", [])

    if uploaded_files_info:
        await handle_file_uploads(client, original_channel_id, original_user_id, uploaded_files_info)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=3, min=3))
async def handle_file_uploads(client, original_channel_id, original_user_id, uploaded_files_info):
    for file_info in uploaded_files_info:
        download_url = file_info["url_private"]
        headers = {"Authorization": f"Bearer {os.environ['SLACK_BOT_TOKEN']}"}
        response = requests.get(download_url, headers=headers)

        if response.status_code == 200:
            file_bytes = response.content
            logger.info("Uploading file")
            upload_response = await client.files_upload_v2(
                channel=original_channel_id,
                file=file_bytes,
                filename=file_info.get("name"),
                title="Anonymous file"
            )
            if upload_response.get("ok"):
                logger.info(
                    f"File uploaded successfully: {upload_response['file']['id']}")
            else:
                logger.error(
                    f"Failed to upload file: {upload_response.get('error', 'Unknown error')}")
        else:
            logger.error(
                f"Failed to download file from <@{original_user_id}>: Status {response.status_code}")


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=60, max=200))
@sleep_and_retry
@limits(calls=5, period=60)
@app.command("/sarcasm")
async def handle_sarcasm_command(ack, say, command):
    await ack()
    user_message = command["text"]
    gemini_client = get_random_gemini_client()
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
async def handle_help_command(ack, respond, say, command):
    await ack()
    user_message = command["text"]
    gemini_client = get_random_gemini_client()
    prompt = build_help_prompt(user_message, gemini_client)
    await respond("Fetching help... ⏳")
    ai_response = gemini_client.models.generate_content(
        model=MODEL_HELPFUL,
        contents=prompt
    )
    await say(text=ai_response.text)


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=4, min=30, max=200))
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

    response = await client.conversations_replies(channel=channel_id, ts=thread_ts)
    messages = response.get("messages", [])

    def extract_text_from_blocks(blocks):
        text = []
        for block in blocks:
            if block["type"] == "section" and "text" in block:
                text.append(block["text"]["text"])
            elif block["type"] == "rich_text" and "elements" in block:
                for element in block["elements"]:
                    if element["type"] == "rich_text_section":
                        for sub_element in element["elements"]:
                            if sub_element["type"] == "text":
                                text.append(sub_element["text"])
        return " ".join(text)

    replies = []
    for msg in messages:
        reply_text = msg.get("text", "")
        if "blocks" in msg:
            reply_text = extract_text_from_blocks(msg["blocks"])
        replies.append(reply_text)

    thread_context = f"\n".join(replies)

    logger.warning(f"Full thread context: {thread_context}")

    image_parts = get_images([event]) + get_images(messages)

    gemini_client = get_random_gemini_client()

    if "sarcasm" in user_message.lower():
        prompt = build_sarcasm_prompt(
            thread_context, gemini_client) + image_parts
        ai_response = gemini_client.models.generate_content(
            model=MODEL_SARCASM, contents=prompt,
        )
    else:
        prompt = build_help_prompt(thread_context, gemini_client) + image_parts
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
