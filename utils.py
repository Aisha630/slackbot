from typing import List, Tuple
import os

MAX_CONCURRENT_REQUESTS = 10
ASSIGNMENT_FOLDER = "assignment_material"
ADMIN_CHANNEL = "C08NBRCUZBJ"
MODEL_SARCASM = "gemini-2.5-flash-preview-04-17"
MODEL_HELPFUL = "gemini-2.5-pro-exp-03-25"


def create_prompt(base_prompt: str, gemini_client) -> List[str]:
    """Attach assignment materials to the Gemini prompt."""
    prompt = [base_prompt]
    for file in os.listdir(ASSIGNMENT_FOLDER):
        file_path = os.path.join(ASSIGNMENT_FOLDER, file)
        try:
            material = gemini_client.files.upload(file=file_path)
            prompt.append(material)
        except Exception as e:
            print(f"Failed to upload {file_path}: {e}")
    return prompt


def build_help_prompt(user_message: str, gemini_client) -> List[str]:
    base = f"""Respond to the user query in a succinct, friendly manner based on the assignment manual, starter code (DHT.py) and test cases that I have attached with this prompt. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382 whose Head TA is Aysha. You are the CS382-bot. The students will have questions about the assignments. Your goal is to guide them without giving code. Be helpful, motivating, and guide them to the right direction.\n\nUser Query:\n{user_message}"""

    return create_prompt(base, gemini_client)


def build_sarcasm_prompt(user_message: str, gemini_client) -> List[str]:
    base = f"""Generate a short, extremely sarcastic, relevant and funny message to according to the demands of the user. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382 whose Head TA is Aysha. The students will either have questions about the course or assignemnts. We will only ask you to generate sarcastic responses to the students who it seems like have either not read the assignment manual, watched the assignment tutorial, not been attending class lectures or consulting course material like the course LMS tab to view the relevant deadlines and materials. Respond with just the message and no additional commentary.
    Here is an example for you as well. User: generate a response that tells a student who has been asking questions that should be obvious from reading the manual?
    You: Tsk tsk. Someone did not bother reading the manual. I guess you are not a fan of reading, huh? Maybe give it a try next time.\n Here is the user message that you need to respond to: Generate a short, extremely sarcastic, relevant and funny response based on the following instruction:\nUser Instruction:\n{user_message}"""

    return create_prompt(base, gemini_client)
