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
# function to get an answer from OpenAI
def openai_answer():
    global total_characters, conversation
    total_characters = sum(len(d['content']) for d in conversation)
    while total_characters > 4000:
        try:
            # print(total_characters)
            # print(len(conversation))
            conversation.pop(2)
            total_characters = sum(len(d['content']) for d in conversation)
        except Exception as e:
            print("Error removing old messages: {0}".format(e))
    with open("conversation.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)
    prompt = getPrompt()
    if use_local_api:
        message = local_chat(prompt)
    else:
        try:
            response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            # model= "gpt-4o-mini",
            messages=prompt,
            max_tokens=128,
            temperature=1,
            top_p=0.9
        )
            message = response['choices'][0]['message']['content']
        except openai.error.RateLimitError:
            print("⚠️ Đã vượt giới hạn API OpenAI. Vui lòng kiểm tra quota hoặc dùng model local.")
            message = "[LỖI]: Vượt quota OpenAI."
        except Exception as e:
            print("❌ Lỗi gọi OpenAI:", e)
            message = "[LỖI]: Không phản hồi từ OpenAI."
    conversation.append({'role': 'assistant', 'content': message})
    translate_text(message)
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
# translating is optional
def translate_text(text):
    global is_Speaking
    # subtitle will act as subtitle for the viewer
    # subtitle = translate_google(text, "ID")

    # tts will be the string to be converted to audio
    detect = detect_google(text)
    tts = translate_google(text, f"{detect}", "JA")
    tts_en = translate_google(text, f"{detect}", "EN")
    try:
        # print("ID Answer: " + subtitle)

        print("JP Answer:", tts)
        print("EN Answer:", tts_en)
    except Exception as e:
        print("Error printing text:", e)
        return
    # Choose between the available TTS engines
    # Japanese TTS
    # voicevox_tts(tts)

    # Silero TTS, Silero TTS can generate English, Russian, French, Hindi, Spanish, German, etc. Uncomment the line below. Make sure the input is in that language
    silero_tts(tts_en, "en", "v3_en", "en_21")

    # Generate Subtitle
    generate_subtitle(chat_now, text)

    time.sleep(1)

    # is_Speaking is used to prevent the assistant speaking more than one audio at a time
    is_Speaking = True
    try:
        winsound.PlaySound("test.wav", winsound.SND_FILENAME)
    except:
        print("⚠️ Sound playback error")
    is_Speaking = False

    # Clear the text files after the assistant has finished speaking
    time.sleep(1)
    with open("output.txt", "w") as f:
        f.truncate(0)
    with open("chat.txt", "w") as f:
        f.truncate(0)

def preparation():
    global conversation, chat_now, chat, chat_prev
    while running:
          # If the assistant is not speaking, and the chat is not empty, and the chat is not the same as the previous chat
        # then the assistant will answer the chat
        chat_now = chat
        if not is_Speaking and chat_now != chat_prev:
                        # Saving chat history

            conversation.append({'role': 'user', 'content': chat_now})
            chat_prev = chat_now
            openai_answer()
        time.sleep(1)

if __name__ == "__main__":
    try:
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
