import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from google import genai
import logging

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
# Initializes your app with your bot token and socket mode handler
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
logger  = logging.basicConfig(level=logging.DEBUG)

@app.message("hello")
def message_hello(message, say):
    print(f"Received message: {message}")
    # say() sends a message to the channel where the event was triggered
    say(f"Hey there <@{message['user']}>!")


@app.command("/anon")
def handle_anonymous_command(ack, say, command, client):
    ack()

    user_id = command['user_id']
    user_message = command['text']

    say(f"{user_message}")

    client.chat_postMessage(
        channel="C08MDUL7D8E",  
        text=f"Anonymous message sent by <@{user_id}>:\n{user_message}"
    )

'''contents="""Generate a short, sarcastic and funny response to this user. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382. The students will either have questions about the course or assignemnts. We will only ask you to generate sarcastic responses to the students who it seems like have either not read the assignment manual, watched the assignment tutorial, not eben attending class lectures or consulting course material like the course LMS tab to view the relevant deadlines and materials. Here is an exmaple for you as well. 
    User: Are we supposed to to implement the assignment in C++ or Java?
    You: Tsk tsk. Someone did not bother reading the manual. I guess you are not a fan of reading, huh?
    "Here is the user message that you need to respond to: \n""" + user_message)'''


@app.event("app_mention")
def handle_sarcasm_command(event, say, client):
    thread_ts = event.get("thread_ts")
    user_id = event["user"]
    channel_id = event["channel"]
    user_message = event["text"]
    logger.debug(f"Received event: {event}")

    if thread_ts:
        response = client.conversations_replies(channel=channel_id, ts=thread_ts)
        messages = response.get("messages", [])
    else:
        messages = [{"text": user_message}]

    thread_context = "\n".join([msg["text"] for msg in messages])

    ai_response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=f"""Generate a short, sarcastic and funny response to this user. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382. The students will either have questions about the course or assignemnts. We will only ask you to generate sarcastic responses to the students who it seems like have either not read the assignment manual, watched the assignment tutorial, not eben attending class lectures or consulting course material like the course LMS tab to view the relevant deadlines and materials. Here is an exmaple for you as well. User: Are we supposed to to implement the assignment in C++ or Java?
        You: Tsk tsk. Someone did not bother reading the manual. I guess you are not a fan of reading, huh? \n Here is the user message that you need to respond to:Generate a short, sarcastic and funny response based on the following conversation:\n{thread_context}"""
    )

    say(text=ai_response.generated_contents[0].text, thread_ts=thread_ts or event["ts"])



@app.event("message")
def handle_message_events(body, logger):
    pass

@app.error
def custom_error_handler(error, body, logger):
    logger.exception(f"Error: {error}")
    logger.info(f"Request body: {body}")

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()