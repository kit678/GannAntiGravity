"""
Simple script to call the Google Gemini API.
Edit API_KEY below with your actual Gemini API key.
"""

import os
import sys

# Install and import the Gemini client
try:
    import google.generativeai as genai
except ImportError:
    print("Installing google-generativeai...")
    os.system(f"{sys.executable} -m pip install google-generativeai -q")
    import google.generativeai as genai


def main():
    # ============================================================
    # PASTE YOUR GEMINI API KEY HERE
    # ============================================================
    API_KEY = "AIzaSyD0OCtO2kp5SNNSwZPS5xYu1iRhPNkQj6s"
    # ============================================================
    
    print("\n" + "="*50)
    print("Google Gemini API Test Script")
    print("="*50)
    
    if API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\nError: Please edit this script and paste your API key!")
        print("Open gemini_test.py and replace YOUR_GEMINI_API_KEY_HERE")
        return
    
    # Configure the API with the key
    genai.configure(api_key=API_KEY)
    
    # Model: gemini-2.0-flash is the current working model
    # Note: gemini-3.1-pro does not exist in the API
    model_name = "gemini-3.1-pro-preview"
    
    print(f"\nUsing model: {model_name}")
    print("Sending request to Gemini API...")
    
    try:
        # Create the model and send request
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("what is the capital of India.")
        
        # Print the response
        print("\n" + "-"*50)
        print("RESPONSE FROM GEMINI API:")
        print("-"*50)
        print(response.text)
        print("-"*50 + "\n")
        
    except Exception as e:
        print(f"\nError calling Gemini API: {e}")


if __name__ == "__main__":
    main()
