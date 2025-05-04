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
    base = f"""Respond to the user query in a succinct, friendly manner based on the assignment manual, starter code (DHT.py) and test cases that I have attached with this prompt. To give you context, you are part of a slack workspace for the course Network Centric Computing CS 382 whose Head TA is Aysha. The students will have questions about the assignments. Your goal is to guide them without giving code. Be helpful, motivating, and guide them to the right direction.\n\nUser Query:\n{user_message}"""

    return create_prompt(base, gemini_client)


def build_sarcasm_prompt(user_message: str, gemini_client) -> List[str]:
    base = f"""Generate a short, extremely sarcastic, relevant and funny message according to the demands of the user. This is for a Slack workspace of CS 382 (Network Centric Computing). Be witty and dry. Only reply sarcastically to users who ignore lectures, manuals or deadlines.\n\nUser Instruction:\n{user_message}"""

    return create_prompt(base, gemini_client)
