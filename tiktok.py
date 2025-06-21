import sys
import requests
import json
import time
import random

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextBrowser, QLabel, QComboBox, QLineEdit, QSizePolicy,
    QMessageBox, QFrame # For custom message box and QFrame
)
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRunnable, QThreadPool, QObject

# --- Configuration ---
# You can leave the API_KEY as an empty string. Canvas will automatically provide it.
API_KEY = "YOUR GEMINI API KEY HERE" # Your Gemini API Key (if running outside Canvas, replace with your actual key)

# Supported regions for contextual LLM generation (not directly used for API calls, but for prompt)
REGIONS = {
    "United States": "US",
    "Global": "GLOBAL",
    "United Kingdom": "GB",
    "Canada": "CA",
    "Australia": "AU",
    "Germany": "DE",
    "France": "FR",
    "India": "IN",
    "Brazil": "BR",
    "Mexico": "MX"
}

# --- LLM Data Generation Functions ---

def call_gemini_api(prompt_text, response_schema=None):
    """
    Generic function to call the Gemini API with a given prompt and optional schema.
    """
    chat_history = []
    chat_history.append({ "role": "user", "parts": [{ "text": prompt_text }] })
    
    payload = {
        "contents": chat_history,
        "generationConfig": {
            "responseMimeType": "text/plain" # Default to plain text
        }
    }
    
    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
    
    try:
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload, timeout=45) # Increased timeout
        response.raise_for_status() 
        
        result = response.json()
        
        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            response_text = result["candidates"][0]["content"]["parts"][0]["text"]
            if response_schema:
                # If expecting JSON, parse it
                return json.loads(response_text)
            else:
                return response_text
        else:
            print("LLM response did not contain expected data structure.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        raise # Re-raise to be caught by worker
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from LLM response: {e}")
        print(f"Raw LLM response text (might not be valid JSON): {response.text if response else 'N/A'}")
        raise # Re-raise to be caught by worker
    except Exception as e:
        print(f"An unexpected error occurred in call_gemini_api: {e}")
        raise # Re-raise to be caught by worker

def generate_trends_with_llm(topic, region_name, region_code):
    """
    Generates simulated TikTok and Google trends using the Gemini API.
    """
    prompt = (
        f"As a social media trend analyst, generate a list of current top trending TikTok hashtags, "
        f"trending TikTok songs (with artist if possible), and top Google search trends "
        f"relevant to the topic '{topic}' in the region '{region_name}' ({region_code}). "
        f"Provide the output in a JSON format with keys: 'tiktok_hashtags' (list of strings, e.g., ['#trend1', '#trend2']), "
        f"'tiktok_songs' (list of objects with 'name' and 'artist' strings), "
        f"and 'google_trends' (list of strings). "
        f"Ensure there are at least 5-10 items for hashtags and songs, and 5 for Google trends. "
        f"Focus on recent and plausible trends. Avoid making up specific view counts, just list the names."
    )
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "tiktok_hashtags": {
                "type": "ARRAY",
                "items": {"type": "STRING"}
            },
            "tiktok_songs": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING"},
                        "artist": {"type": "STRING"}
                    },
                    "required": ["name", "artist"]
                }
            },
            "google_trends": {
                "type": "ARRAY",
                "items": {"type": "STRING"}
            }
        },
        "required": ["tiktok_hashtags", "tiktok_songs", "google_trends"]
    }
    
    return call_gemini_api(prompt, response_schema)

def generate_veo_prompt_with_llm(trend_data, current_topic, region_name):
    """
    Generates a descriptive video prompt for an AI like Veo based on trend data.
    """
    tiktok_hashtags = trend_data.get("tiktok_hashtags", [])
    tiktok_songs = trend_data.get("tiktok_songs", [])
    google_trends = trend_data.get("google_trends", [])

    prompt_parts = [
        f"Create a concise, creative, and highly descriptive text-to-video AI prompt (e.g., for Veo or similar models) "
        f"for a TikTok-style video. The video should incorporate elements from the following trends relevant to '{current_topic}' in '{region_name}'.",
        "\n\n**Trending TikTok Hashtags:**", ", ".join(tiktok_hashtags) if tiktok_hashtags else "None provided.",
        "\n\n**Trending TikTok Songs:**", ", ".join([f"'{s['name']}' by {s['artist']}" for s in tiktok_songs]) if tiktok_songs else "None provided.",
        "\n\n**Top Google Search Trends:**", ", ".join(google_trends) if google_trends else "None provided.",
        "\n\nThe video prompt should be imaginative, describe visual scenes, possible character actions, and suggest a mood or style. "
        "Keep it under 150 words. Focus on a single engaging concept."
    ]
    
    full_prompt = "".join(prompt_parts)
    
    return call_gemini_api(full_prompt) # No schema needed for plain text output

# --- Worker Classes for Asynchronous Tasks ---

class TrendWorkerSignals(QObject):
    data_generated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

class TrendWorker(QRunnable):
    """Worker for generating trend data."""
    def __init__(self, topic, region_name, region_code):
        super().__init__()
        self.topic = topic
        self.region_name = region_name
        self.region_code = region_code
        self.setAutoDelete(True)
        self.signals = TrendWorkerSignals()

    def run(self):
        try:
            print(f"Worker: Generating trends for topic '{self.topic}' in region '{self.region_name}'...")
            generated_data = generate_trends_with_llm(self.topic, self.region_name, self.region_code)
            
            if generated_data:
                self.signals.data_generated.emit(generated_data)
                print(f"Worker: Trend generation complete for '{self.topic}'.")
            else:
                self.signals.error_occurred.emit("LLM could not generate valid trend data. Please try again with a different topic or check API key.")

        except Exception as e:
            error_message = f"Error during LLM trend data generation: {e}"
            self.signals.error_occurred.emit(error_message)
            print(f"Worker: Error during trend data generation: {e}")

class VeoPromptWorkerSignals(QObject):
    prompt_generated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

class VeoPromptWorker(QRunnable):
    """Worker for generating Veo video prompt."""
    def __init__(self, trend_data, current_topic, region_name):
        super().__init__()
        self.trend_data = trend_data
        self.current_topic = current_topic
        self.region_name = region_name
        self.setAutoDelete(True)
        self.signals = VeoPromptWorkerSignals()

    def run(self):
        try:
            print(f"Worker: Generating Veo prompt for topic '{self.current_topic}'...")
            veo_prompt = generate_veo_prompt_with_llm(self.trend_data, self.current_topic, self.region_name)
            
            if veo_prompt:
                self.signals.prompt_generated.emit(veo_prompt)
                print("Worker: Veo prompt generation complete.")
            else:
                self.signals.error_occurred.emit("LLM could not generate a valid Veo prompt. Please try again.")

        except Exception as e:
            error_message = f"Error during Veo prompt generation: {e}"
            self.signals.error_occurred.emit(error_message)
            print(f"Worker: Error during Veo prompt generation: {e}")

# --- PyQt5 Application ---

class TikTokTrendApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TikTok Trend Data App (LLM-Powered with Video Prompt)")
        self.setGeometry(100, 100, 900, 800) # Adjusted window size
        
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1) # Ensure only one LLM call at a time

        self.current_trend_data = {} # Store the last fetched trend data
        self.current_topic = "general" # Store the last used topic
        self.current_region_name = "United States" # Store the last used region

        self.init_ui()
        self.apply_styles()
        
        # Initial call with default values
        self.fetch_trends()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Header ---
        header_label = QLabel("TikTok Trend Insights (AI-Generated)")
        header_label.setObjectName("headerLabel")
        main_layout.addWidget(header_label, alignment=Qt.AlignCenter)

        # --- Controls Layout ---
        controls_layout = QHBoxLayout()
        main_layout.addLayout(controls_layout)

        # Topic Input
        topic_label = QLabel("Topic/Category:")
        controls_layout.addWidget(topic_label)
        self.topic_input = QLineEdit(self.current_topic) 
        self.topic_input.setPlaceholderText("e.g., gaming, cooking, news, fashion")
        controls_layout.addWidget(self.topic_input)

        # Region Selector
        region_label = QLabel("Region:")
        controls_layout.addWidget(region_label)
        self.region_combo = QComboBox()
        self.region_combo.addItems(sorted(REGIONS.keys()))
        self.region_combo.setCurrentText(self.current_region_name) 
        controls_layout.addWidget(self.region_combo)
        
        # Generate Trends Button
        self.fetch_button = QPushButton("Generate Trends")
        self.fetch_button.clicked.connect(self.fetch_trends)
        controls_layout.addWidget(self.fetch_button)
        
        controls_layout.addStretch(1) 

        # --- Status Label ---
        self.status_label = QLabel("Enter a topic and click 'Generate Trends'.")
        self.status_label.setObjectName("statusLabel")
        main_layout.addWidget(self.status_label)

        # --- Trend Display Area ---
        self.trend_output = QTextBrowser()
        self.trend_output.setReadOnly(True)
        self.trend_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.trend_output)

        # --- Video Prompt Generation Section ---
        video_prompt_frame = QFrame()
        video_prompt_frame.setObjectName("videoPromptFrame")
        video_prompt_layout = QVBoxLayout(video_prompt_frame)
        
        video_prompt_header = QLabel("Generate AI Video Prompt")
        video_prompt_header.setObjectName("videoPromptHeader")
        video_prompt_layout.addWidget(video_prompt_header, alignment=Qt.AlignCenter)

        self.generate_veo_button = QPushButton("Create Video Prompt")
        self.generate_veo_button.setEnabled(False) # Disable until trends are fetched
        self.generate_veo_button.clicked.connect(self.generate_veo_prompt)
        video_prompt_layout.addWidget(self.generate_veo_button)

        self.veo_prompt_output = QTextBrowser()
        self.veo_prompt_output.setReadOnly(True)
        self.veo_prompt_output.setPlaceholderText("AI video prompt will appear here...")
        self.veo_prompt_output.setFixedHeight(120) # Fixed height for prompt
        video_prompt_layout.addWidget(self.veo_prompt_output)

        self.copy_prompt_button = QPushButton("Copy Prompt to Clipboard")
        self.copy_prompt_button.setEnabled(False) # Disable until a prompt is generated
        self.copy_prompt_button.clicked.connect(self.copy_veo_prompt)
        video_prompt_layout.addWidget(self.copy_prompt_button)

        main_layout.addWidget(video_prompt_frame)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: #e0e0e0; }
            QLabel { color: #e0e0e0; font-size: 14px; }
            #headerLabel { font-size: 28px; font-weight: bold; color: #64ffda; margin-bottom: 10px; }
            #statusLabel { font-size: 13px; color: #aaaaaa; padding-left: 5px; margin-top: 5px; }
            QLineEdit { background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #555555; border-radius: 5px; padding: 5px; font-size: 14px; }
            QPushButton { background-color: #00796b; color: white; border-radius: 8px; padding: 10px 15px; font-size: 15px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #004d40; }
            QPushButton:pressed { background-color: #00251a; }
            QPushButton:disabled { background-color: #555555; color: #b0b0b0; } /* Disabled state */
            QComboBox { background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #555555; border-radius: 5px; padding: 5px; font-size: 14px; }
            QComboBox::drop-down { border: 0px; }
            QComboBox::down-arrow { image: url(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IArs4c6QAAADhJREFUOE9jZKAyYKSx+Q/qHwyOQcIBg3/I/k8GMjAwi1GkggFwQxAYg4gKGDjA4ADrI4A5EABGDAAAz/k5m6E6z/4AAAAASUVORK5CYII=); width: 16px; height: 16px; }
            QTextBrowser { background-color: #1e1e1e; color: #f0f0f0; border: 1px solid #444444; border-radius: 8px; padding: 10px; font-family: "Inter", sans-serif; font-size: 14px; }
            QTextBrowser a { color: #64ffda; text-decoration: underline; }
            QScrollBar:vertical { border: none; background: #3c3c3c; width: 10px; margin: 0px; border-radius: 5px; }
            QScrollBar::handle:vertical { background: #64ffda; border-radius: 5px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { border: none; }
            #videoPromptFrame { border: 1px solid #444444; border-radius: 8px; padding: 10px; margin-top: 20px; }
            #videoPromptHeader { font-size: 20px; font-weight: bold; color: #64ffda; margin-bottom: 10px; }
        """)

    def fetch_trends(self):
        self.fetch_button.setEnabled(False)
        self.generate_veo_button.setEnabled(False) # Disable video prompt button too
        self.copy_prompt_button.setEnabled(False)
        self.status_label.setText("Generating trends... This may take a moment.")
        self.trend_output.clear()
        self.veo_prompt_output.clear()
        self.trend_output.setHtml("<p style='color:#aaaaaa;'>Asking the AI for trend insights...</p>")
        self.veo_prompt_output.setPlaceholderText("AI video prompt will appear here...")

        self.current_region_name = self.region_combo.currentText()
        selected_region_code = REGIONS.get(self.current_region_name, "US")
        self.current_topic = self.topic_input.text().strip()
        if not self.current_topic:
            self.current_topic = "general" # Default if user leaves it empty
            self.topic_input.setText("general")

        worker = TrendWorker(self.current_topic, self.current_region_name, selected_region_code)
        worker.signals.data_generated.connect(self.display_trends)
        worker.signals.error_occurred.connect(self.display_error_message_box)
        self.threadpool.start(worker)

    def display_trends(self, trend_data):
        self.fetch_button.setEnabled(True)
        self.generate_veo_button.setEnabled(True) # Enable video prompt button
        self.status_label.setText("Trends generated successfully. Now you can generate a video prompt.")
        
        self.current_trend_data = trend_data # Store the fetched data

        tiktok_hashtags = trend_data.get("tiktok_hashtags", [])
        tiktok_songs = trend_data.get("tiktok_songs", [])
        google_trends = trend_data.get("google_trends", [])

        html_output = "<h2>TikTok Trend Analysis & Video Recommendations (AI-Generated)</h2>"
        html_output += "<hr style='border: 1px solid #444;'>"

        # --- TikTok Hashtags ---
        html_output += "<h3>Current Top Trending TikTok Hashtags:</h3>"
        if tiktok_hashtags:
            html_output += "<ul>"
            for i, h in enumerate(tiktok_hashtags):
                html_output += f"<li><strong>{h}</strong></li>"
            html_output += "</ul>"
        else:
            html_output += "<p><i>No trending hashtags generated for this topic/region.</i></p>"

        # --- TikTok Songs ---
        html_output += "<h3>Current Top Trending TikTok Songs:</h3>"
        if tiktok_songs:
            html_output += "<ul>"
            for i, s in enumerate(tiktok_songs):
                html_output += f"<li><strong>\"{s['name']}\"</strong> by {s['artist']}</li>"
            html_output += "</ul>"
        else:
            html_output += "<p><i>No trending songs generated for this topic/region.</i></p>"

        # --- Google Trends ---
        html_output += "<h3>Current Top Google Trending Searches (Broader Context):</h3>"
        if google_trends:
            html_output += "<ul>"
            for i, gt in enumerate(google_trends):
                html_output += f"<li>{gt}</li>"
            html_output += "</ul>"
        else:
            html_output += "<p><i>No Google trending searches generated for this topic/region.</i></p>"

        # --- Recommendations ---
        html_output += "<hr style='border: 1px solid #444;'>"
        html_output += "<h2>Best Video to Create Based on These Trends</h2>"
        html_output += "<p>To create a successful TikTok video, combine these AI-generated trends with your unique content:</p>"

        if tiktok_hashtags or tiktok_songs or google_trends:
            if tiktok_hashtags:
                top_hash_name = tiktok_hashtags[0] if tiktok_hashtags else ""
                html_output += "<h3>1. Leverage Top TikTok-Specific Elements:</h3>"
                html_output += f"<p>   - <b>Hashtag Focus:</b> Create content that directly relates to <b>{top_hash_name}</b>. Think about challenges, POVs, or skits that fit this theme. Use it prominently in your caption.</p>"
            
            if tiktok_songs:
                top_song_name = tiktok_songs[0]['name'] if tiktok_songs else ""
                top_song_artist = tiktok_songs[0]['artist'] if tiktok_songs else ""
                if not tiktok_hashtags: 
                    html_output += "<h3>1. Leverage Top TikTok-Specific Elements:</h3>"
                html_output += f"<p>   - <b>Sound Sync:</b> Use the trending song <b>\"{top_song_name}\"</b> by {top_song_artist}. Find how others are using it and put your own creative spin on the trend or pair it with relevant visuals.</p>"
            
            if len(tiktok_hashtags) > 1:
                html_output += f"<p>   - <b>Secondary Hashtags:</b> Also consider including {tiktok_hashtags[1]} or {tiktok_hashtags[2]} if they are relevant to broaden your reach.</p>"

            if google_trends:
                html_output += "<h3>2. Connect with Broader Google Search Trends:</h3>"
                top_google_trend = google_trends[0] if google_trends else "a general topic"
                html_output += f"<p>   - <b>Topical Relevance:</b> If your content can subtly or directly connect to a high-interest Google search like <b>\"{top_google_trend}\"</b>, you can tap into a wider audience.</p>"
                html_output += "<p>     <i>Example:</i> If a new movie is trending on Google, create a meme using a TikTok trending sound about that movie.<br>"
                html_output += "     <i>Example:</i> If a 'how-to' topic is trending on Google, make a quick, engaging tutorial on TikTok using a trending sound.</p>"
        else:
            html_output += "<p>No trend data could be generated for the given topic/region. Please try a different input or check your API key/network connection.</p>"

        html_output += "<h3>General TikTok Video Creation Strategy:</h3>"
        html_output += "<ul>"
        html_output += "<li><b>Identify your Niche:</b> How can you apply these general trends to your specific content area (e.g., gaming, cooking, fashion, education)?</li>"
        html_output += "<li><b>Hook Viewers Instantly:</b> The first 1-3 seconds are critical. Start with something captivating.</li>"
        html_output += "<li><b>Keep it Concise:</b> TikTok favors shorter videos (7-15 seconds) for higher completion rates.</li>"
        html_output += "<li><b>Authenticity and Relatability:</b> Raw, genuine content often outperforms highly produced videos.</li>"
        html_output += "<li><b>Visuals & Text:</b> Good lighting, clear audio, and on-screen text or captions are essential.</li>"
        html_output += "<li><b>Call to Action:</b> Encourage likes, comments, shares, or duets.</li>"
        html_output += "<li><b>Consistency:</b> Regular posting helps your content get seen by the algorithm.</li>"
        html_output += "<li><b>Engage with Comments:</b> Build a community around your content.</li>"
        html_output += "</ul>"
        
        html_output += "<hr style='border: 1px solid #444;'>"
        html_output += "<p style='font-size:12px; color:#aaa;'><i>Disclaimer: This app generates trend ideas using AI and is not connected to real-time TikTok or Google data. Always verify actual trends on the TikTok app itself or official trend sites.</i></p>"

        self.trend_output.setHtml(html_output)

    def generate_veo_prompt(self):
        if not self.current_trend_data:
            self.display_error_message_box("No trend data available to generate a video prompt. Please generate trends first.")
            return

        self.generate_veo_button.setEnabled(False)
        self.copy_prompt_button.setEnabled(False)
        self.veo_prompt_output.clear()
        self.veo_prompt_output.setPlaceholderText("Generating video prompt...")
        self.status_label.setText("Generating AI video prompt... This might take a bit longer.")

        worker = VeoPromptWorker(self.current_trend_data, self.current_topic, self.current_region_name)
        worker.signals.prompt_generated.connect(self.display_veo_prompt)
        worker.signals.error_occurred.connect(self.display_error_message_box)
        self.threadpool.start(worker)

    def display_veo_prompt(self, prompt_text):
        self.generate_veo_button.setEnabled(True)
        self.copy_prompt_button.setEnabled(True)
        self.veo_prompt_output.setText(prompt_text)
        self.status_label.setText("AI video prompt generated successfully!")
        QMessageBox.information(self, "Prompt Generated", "AI video prompt has been generated and is displayed below. You can copy it to your clipboard.")


    def copy_veo_prompt(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.veo_prompt_output.toPlainText())
        QMessageBox.information(self, "Copied!", "Video prompt copied to clipboard!")

    def display_error_message_box(self, message):
        self.fetch_button.setEnabled(True)
        self.generate_veo_button.setEnabled(True) # Re-enable if error
        self.copy_prompt_button.setEnabled(False) # Disable copy if error
        self.status_label.setText("Error occurred.")
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Operation Error")
        msg_box.setText("An error occurred during AI processing.")
        msg_box.setInformativeText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()
        print(f"Error displayed in GUI: {message}")

# --- Main Application Entry Point ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    font = QFont("Inter", 10)
    app.setFont(font)

    window = TikTokTrendApp()
    window.show()
    sys.exit(app.exec_())

