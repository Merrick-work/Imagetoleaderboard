import os
import re
import json
from datetime import datetime
import streamlit as st
import requests
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv
from PIL import Image
import base64
import io

# Load environment variables from .env file if it exists
load_dotenv()

# Set page configuration
st.set_page_config(
    page_title="Crossword Leaderboard Processor",
    page_icon="🏆",
    layout="wide"
)

# Application title
st.title("Crossword Leaderboard Processor")
st.write("Upload an image of your crossword puzzle leaderboard to extract player times and send to Supabase.")

# Sidebar for configuration
st.sidebar.header("Configuration")

# Supabase credentials
with st.sidebar.expander("Supabase Settings", expanded=True):
    supabase_url = st.text_input("Supabase URL", value=os.getenv("SUPABASE_URL", ""), type="password")
    supabase_key = st.text_input("Supabase Key", value=os.getenv("SUPABASE_KEY", ""), type="password")
    
    if supabase_url and supabase_key:
        st.success("Supabase credentials provided!")
    else:
        st.warning("Please enter your Supabase credentials")

# OCR.space credentials
with st.sidebar.expander("OCR.space Settings", expanded=True):
    ocr_api_key = st.text_input("OCR.space API Key", value=os.getenv("OCR_API_KEY", ""), type="password")
    st.markdown("""
    Get a free API key at [OCR.space](https://ocr.space/ocrapi/freekey) - it only takes a minute!
    """)
    
    if ocr_api_key:
        st.success("OCR.space API Key provided!")
    else:
        st.warning("Please enter your OCR.space API Key")

# Functions
def initialize_supabase() -> Client:
    """Initialize Supabase client."""
    if not supabase_url or not supabase_key:
        st.error("Supabase URL and API Key are required")
        return None
    
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

def extract_text_from_image_ocrspace(image_bytes):
    """
    Extract text from image using OCR.space API.
    """
    if not ocr_api_key:
        st.error("OCR.space API Key is required")
        return ""
    
    try:
        # Convert image to base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # OCR.space API endpoint
        url = 'https://api.ocr.space/parse/image'
        
        # Prepare payload
        payload = {
            'apikey': ocr_api_key,
            'base64Image': f'data:image/jpeg;base64,{base64_image}',
            'language': 'eng',
            'scale': 'true',
            'isTable': 'true',
            'OCREngine': '2'  # More accurate engine
        }
        
        # Make API request
        with st.spinner("Processing image with OCR.space..."):
            response = requests.post(url, data=payload)
            
            if response.status_code != 200:
                st.error(f"OCR.space API error: {response.text}")
                return ""
            
            result = response.json()
            
            if result['OCRExitCode'] != 1:  # 1 means success
                st.error(f"OCR processing failed: {result['ErrorMessage'] if 'ErrorMessage' in result else 'Unknown error'}")
                return ""
            
            # Extract the text
            extracted_text = ""
            for page in result.get('ParsedResults', []):
                extracted_text += page.get('ParsedText', '')
                
            return extracted_text
    
    except Exception as e:
        st.error(f"Error extracting text from image: {e}")
        return ""

def parse_leaderboard_data(text: str) -> dict:
    """
    Parse the OCR text to extract player names and times.
    """
    data = {}
    
    # Common player names from your database
    player_names = ["Merrick", "Moi", "Sidney", "John", "Lauren", "Vy", "Marcus", "Chris", "Leslie"]
    
    # Look for patterns like "Name: 0.00" or "Name - 0.00" or "Name 0.00"
    for name in player_names:
        # Try different patterns that might appear in the OCR text
        patterns = [
            rf"{name}:\s*(\d+\.\d+)",
            rf"{name}\s*-\s*(\d+\.\d+)",
            rf"{name}\s+(\d+\.\d+)",
            rf"{name}'s time:\s*(\d+\.\d+)",
            rf"{name}\s*=\s*(\d+\.\d+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Convert time to string with 2 decimal places
                try:
                    time_value = float(match.group(1))
                    data[name] = str(time_value)
                    break
                except ValueError:
                    # If conversion fails, try the next pattern
                    continue
    
    return data

def get_next_id(supabase: Client) -> int:
    """Get the next available ID from the crossword_times table."""
    try:
        response = supabase.table("crossword_times").select("id").order("id.desc").limit(1).execute()
        
        if response.data and len(response.data) > 0:
            return int(response.data[0]['id']) + 1
        
        return 1
    except Exception as e:
        st.error(f"Error getting next ID: {e}")
        return 1

def update_database(supabase: Client, data: dict, date: str) -> bool:
    """Update the database with the extracted leaderboard data."""
    try:
        # Get the next ID
        next_id = get_next_id(supabase)
        
        # Prepare the data for insertion
        record = {
            "id": str(next_id),
            "date": date,
            "created_at": datetime.now().isoformat()
        }
        
        # Add player times to the record
        for player, time in data.items():
            record[player] = time
        
        # Insert the record
        response = supabase.table("crossword_times").insert(record).execute()
        
        if response.data:
            return True, next_id
        else:
            return False, None
    
    except Exception as e:
        st.error(f"Error updating database: {e}")
        return False, None

def fetch_recent_entries(supabase: Client, limit=10):
    """Fetch recent entries from the database."""
    try:
        response = supabase.table("crossword_times").select("*").order("id.desc").limit(limit).execute()
        return response.data
    except Exception as e:
        st.error(f"Error fetching recent entries: {e}")
        return []

# Allow user to manually input data
def manual_data_entry():
    st.subheader("Manual Data Entry")
    
    # Create a form for manual data entry
    player_names = ["Merrick", "Moi", "Sidney", "John", "Lauren", "Vy", "Marcus", "Chris", "Leslie"]
    
    # Initialize empty dictionary to store times
    manual_data = {}
    
    # Create 3 columns for better layout
    cols = st.columns(3)
    
    # Distribute player input fields across columns
    for i, name in enumerate(player_names):
        col_idx = i % 3
        with cols[col_idx]:
            time_value = st.text_input(f"{name}'s Time (e.g. 1.23)", key=f"manual_{name}")
            if time_value:
                try:
                    # Validate that the input is a valid number
                    float(time_value)
                    manual_data[name] = time_value
                except ValueError:
                    st.error(f"Invalid time format for {name}. Please enter a number.")
    
    return manual_data

# Main app functionality
def main():
    # Tabs for different input methods
    tab1, tab2 = st.tabs(["Upload Image", "Manual Entry"])
    
    with tab1:
        # File uploader
        uploaded_file = st.file_uploader("Upload Leaderboard Image", type=["jpg", "jpeg", "png", "bmp"])
        
        # Initialize columns for display
        col1, col2 = st.columns(2)
        
        if uploaded_file is not None:
            # Display the uploaded image
            with col1:
                st.subheader("Uploaded Image")
                image = Image.open(uploaded_file)
                st.image(image, use_column_width=True)
                
                # Process button
                process_button = st.button("Process Image", type="primary")
            
            # Process the image when the button is clicked
            if process_button:
                if not ocr_api_key:
                    st.error("Please enter your OCR.space API Key first")
                else:
                    with st.spinner("Processing image with OCR.space..."):
                        # Reset file pointer and read content
                        uploaded_file.seek(0)
                        image_bytes = uploaded_file.getvalue()
                        
                        # Extract text using OCR.space
                        extracted_text = extract_text_from_image_ocrspace(image_bytes)
                        
                        # Display raw extracted text in expander
                        with st.expander("View Raw OCR Text"):
                            st.text(extracted_text)
                        
                        # Parse the leaderboard data
                        data = parse_leaderboard_data(extracted_text)
                        
                        # Display the extracted data
                        with col2:
                            st.subheader("Extracted Data")
                            
                            if not data:
                                st.error("No valid leaderboard data found in the image.")
                            else:
                                # Display the extracted data in a table
                                df = pd.DataFrame(list(data.items()), columns=["Player", "Time"])
                                st.dataframe(df, use_container_width=True)
                                
                                # Option to edit the extracted data
                                st.subheader("Edit Data (if needed)")
                                edited_df = st.data_editor(df, use_container_width=True)
                                
                                # Update the data dictionary with edited values
                                data = {row["Player"]: row["Time"] for _, row in edited_df.iterrows()}
                                
                                # Submit button
                                submit_button = st.button("Submit to Supabase")
                                
                                if submit_button:
                                    submit_to_database(data)

    with tab2:
        # Manual data entry
        manual_data = manual_data_entry()
        
        # Submit button for manual data
        if st.button("Submit Manual Data") and manual_data:
            submit_to_database(manual_data)
    
    # Date picker (outside of tabs for both methods)
    selected_date = st.date_input("Leaderboard Date", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")
    
    # Function to submit data to database
    def submit_to_database(data):
        if not data:
            st.error("No data to submit")
            return
        
        # Initialize Supabase client
        supabase = initialize_supabase()
        
        if supabase:
            # Update the database
            success, record_id = update_database(supabase, data, date_str)
            
            if success:
                st.success(f"Successfully added record with ID {record_id} for {date_str}!")
            else:
                st.error("Failed to update leaderboard data in Supabase.")
    
    # Display recent entries
    st.subheader("Recent Entries")
    if supabase_url and supabase_key:
        supabase = initialize_supabase()
        if supabase:
            recent_data = fetch_recent_entries(supabase)
            if recent_data:
                # Transform data for better display
                df = pd.DataFrame(recent_data)
                # Keep only date and player columns
                player_columns = ["Merrick", "Moi", "Sidney", "John", "Lauren", "Vy", "Marcus", "Chris", "Leslie"]
                display_columns = ["id", "date"] + [col for col in player_columns if col in df.columns]
                df = df[display_columns].fillna("")
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No recent entries found.")
                
    # Footer with instructions
    st.markdown("---")
    with st.expander("OCR.space Setup Instructions"):
        st.markdown("""
        ## OCR.space Setup Instructions
        
        ### 1. Get a Free OCR.space API Key
        
        1. Visit [OCR.space Free API Key Registration](https://ocr.space/ocrapi/freekey)
        2. Fill in your email address
        3. You'll receive your API key immediately on the website and via email
        
        ### 2. Enter the API Key
        
        1. Copy your API key from OCR.space
        2. Paste it into the "OCR.space API Key" field in the sidebar
        
        ### 3. Use the App
        
        **Using Image Upload**:
        - Upload an image of your leaderboard
        - Click "Process Image"
        - The app will extract text and identify player times
        - Review and edit the extracted data if needed
        - Click "Submit to Supabase"
        
        **Using Manual Entry**:
        - Switch to the "Manual Entry" tab
        - Enter times for each player directly
        - Click "Submit Manual Data"
        
        ### Notes on Free API Usage
        
        - The free OCR.space API allows 25,000 requests per month
        - Each request is limited to 1 MB file size
        - For best results, upload clear, well-lit images
        """)

if __name__ == "__main__":
    main()
