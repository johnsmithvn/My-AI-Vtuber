import openai
import winsound
import sys
import pytchat
import time
import re
import pyaudio
import keyboard
import wave
import threading
import json
import socket
import signal
from emoji import demojize
from config import *
from utils.translate import *
from utils.TTS import *
from utils.subtitle import *
from utils.promptMaker import *
from utils.twitch_config import *
from utils.local_llm import local_chat
import requests
from utils.speech_pipeline import now, process_ai_response_async, playback_worker
from utils.speech_pipeline import audio_queue  # nếu bạn muốn tự xử lý queue ngoài

use_memory_audio = True  # True = phát trực tiếp từ bộ nhớ, False = phát từ file test.wav

# to help the CLI write unicode characters to the terminal
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
# use your own API Key, you can get it from https://openai.com/. I place my API Key in a separate file called config.py

openai.api_key = api_key

conversation = []
# Create a dictionary to hold the message data
history = {"history": conversation}

mode = 0
total_characters = 0
chat = ""
chat_now = ""
chat_prev = ""
is_Speaking = False
owner_name = "Ardha"
blacklist = ["Nightbot", "streamelements"]
use_username_prefix = True
running = True  # Flag điều khiển dừng chương trình

import asyncio
import concurrent.futures
from queue import Queue
from threading import Thread

# Hàng đợi phát âm thanh
# audio_queue = Queue()



def handle_exit(sig, frame):
    global running
    print("\n⛔ Đang thoát chương trình...")
    running = False

signal.signal(signal.SIGINT, handle_exit)

def build_chat_input(username, message):
    lang = detect_google(message)
    if lang == "VI":
        said_word = "nói"
    elif lang == "EN":
        said_word = "said"
    elif lang == "JA":
        said_word = "が言った"
    else:
        said_word = ""
    return f"{username} {said_word} {message}" if use_username_prefix and said_word else message


# function to get the user's input audio

def record_audio():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    WAVE_OUTPUT_FILENAME = "input.wav"
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    frames = []
    print("Recording...")
    try:
        while keyboard.is_pressed('RIGHT_SHIFT') and running:
            data = stream.read(CHUNK)
            frames.append(data)
    finally:
        print("Stopped recording.")
        stream.stop_stream()
        stream.close()
        p.terminate()
    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    transcribe_audio("input.wav")
# function to transcribe the user's audio

def transcribe_audio(file):
    global chat_now
    try:
        with open(file, "rb") as audio_file:
             # Translating the audio to English
        # transcript = openai.Audio.translate("whisper-1", audio_file)
        # Transcribe the audio to detected language
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
        chat_now = transcript.text
        print("Question:", chat_now)
    except Exception as e:
        print("Error transcribing audio:", e)
        return
    result = build_chat_input(owner_name, chat_now)
    conversation.append({'role': 'user', 'content': result})
    openai_answer()

import tiktoken
# tinh token
def count_tokens(messages, model="gpt-4o-mini"):
    try:
        encoding = tiktoken.encoding_for_model(model)
    except:
        encoding = tiktoken.get_encoding("cl100k_base")  # fallback

    tokens = 0
    for message in messages:
        tokens += 4  # default tokens per message
        for key, value in message.items():
            tokens += len(encoding.encode(value))
    tokens += 2  # every reply is primed with <im_start>assistant
    return tokens

# function to get an answer from OpenAI
def openai_answer():
    max_prompt_tokens = 6000 
    total_tokens = count_tokens(conversation, model="gpt-4o-mini")
    while total_tokens > max_prompt_tokens:
        try:
            conversation.pop(2)  # bỏ bớt message cũ nhất (sau system)
            total_tokens = count_tokens(conversation, model="gpt-4o-mini")
        except Exception as e:
            print("Error removing old messages:", e)
            break

    with open("conversation.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)
    prompt = getPrompt()
    if use_local_api:
        message = local_chat(prompt)
    else:
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "model": "gpt-4o-mini",  # hoặc gpt-3.5-turbo nếu muốn
                "messages": prompt,
                "max_tokens": 128,
                "temperature": 1,
                "top_p": 0.9,
            }
            res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            if res.status_code == 200:
                message = res.json()['choices'][0]['message']['content']
            else:
                print("❌ Lỗi HTTP:", res.status_code, res.text)
                message = "[LỖI]: OpenAI HTTP Error."
        except openai.error.RateLimitError:
            print("⚠️ Đã vượt giới hạn API OpenAI. Vui lòng kiểm tra quota hoặc dùng model local.")
            message = "[LỖI]: Vượt quota OpenAI."
        except Exception as e:
            print("❌ Lỗi gọi OpenAI:", e)
            message = "[LỖI]: Không phản hồi từ OpenAI."
    conversation.append({'role': 'assistant', 'content': message})
    print(f"{now()} [🤖 AI RESPONSE] {message}")

     # Thay vì gọi translate_text, ta gọi hàm async mới
    try:
        asyncio.run(process_ai_response_async(message, chat_now))
    except Exception as e:
        print("❌ Async processing error:", e)
# function to capture livechat from youtube

def yt_livechat(video_id):
    global chat
    live = pytchat.create(video_id=video_id)

    while live.is_alive() and running:
    # while True:

        try:
            for c in live.get().sync_items():
                # Ignore chat from the streamer and Nightbot, change this if you want to include the streamer's chat
                if c.author.name in blacklist:
                    continue
                # if not c.message.startswith("!") and c.message.startswith('#'):
                if not c.message.startswith("!"):
                    # Remove emojis from the chat
                    chat_raw = re.sub(r':[^\s]+:', '', c.message)
                    chat_raw = chat_raw.replace('#', '')
                    # chat_author makes the chat look like this: "Nightbot: Hello". So the assistant can respond to the user's name

                    chat = build_chat_input(c.author.name, chat_raw)
                    print(chat)
                time.sleep(1)
        except Exception as e:
                print("Error receiving chat: {0}".format(e))

def twitch_livechat():
    global chat
    sock = socket.socket()
    sock.connect((server, port))
    sock.send(f"PASS {token}\n".encode('utf-8'))
    sock.send(f"NICK {nickname}\n".encode('utf-8'))
    sock.send(f"JOIN {channel}\n".encode('utf-8'))
    regex = r":(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)"
    while running:
        try:
            resp = sock.recv(2048).decode('utf-8')
            if resp.startswith('PING'):
                sock.send("PONG\n".encode('utf-8'))
            elif user not in resp:
                resp = demojize(resp)
                match = re.match(regex, resp)
                if not match:
                    continue
                username, message = match.groups()
                if username in blacklist:
                    continue
                chat = build_chat_input(username, message)
                print(chat)
        except Exception as e:
            print("Error receiving chat: {0}".format(e))

def preparation():
    global conversation, chat_now, chat, chat_prev
    while running:
          # If the assistant is not speaking, and the chat is not empty, and the chat is not the same as the previous chat
        # then the assistant will answer the chat
        chat_now = chat
        if not is_Speaking and chat_now != chat_prev:
            # Saving chat history
            print(f"{now()} [🎧 NEW MESSAGE] {chat_now}")
            conversation.append({'role': 'user', 'content': chat_now})
            chat_prev = chat_now
            openai_answer()
        time.sleep(1)





def start_playback_worker():
    Thread(target=playback_worker, args=(lambda: running,), daemon=True).start()

if __name__ == "__main__":
    try:
         # Khởi động playback worker thread
        start_playback_worker()
        # You can change the mode to 1 if you want to record audio from your microphone
        # or change the mode to 2 if you want to capture livechat from youtube
        api_mode = input("Chọn API (1 - Local model, 2 - OpenAI API): ")
        use_local_api = api_mode.strip() == "1"
        mode = input("Mode (1-Mic, 2-Youtube Live, 3-Twitch Live): ")

        if mode == "1":
            print("Press and Hold Right Shift to record audio")
            while running:
                if keyboard.is_pressed('RIGHT_SHIFT'):
                    record_audio()

        elif mode == "2":
            live_id = input("Livestream ID: ")
                        # Threading is used to capture livechat and answer the chat at the same time

            t = threading.Thread(target=preparation)
            t.daemon = True
            t.start()
            yt_livechat(live_id)

        elif mode == "3":
                        # Threading is used to capture livechat and answer the chat at the same time

            print("To use this mode, make sure to change twitch_config.py")
            t = threading.Thread(target=preparation)
            t.daemon = True
            t.start()
            twitch_livechat()

    except Exception as e:
        print("❌ Lỗi chương trình:", e)
    finally:
        print("✅ Đã thoát chương trình.")

