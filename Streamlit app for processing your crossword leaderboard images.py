import os
import sys
import re
from datetime import datetime
import streamlit as st
import pytesseract
from PIL import Image
import io
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

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

def extract_text_from_image(image) -> str:
    """Extract text from image using OCR."""
    try:
        text = pytesseract.image_to_string(image)
        return text
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
            rf"{name}\s+(\d+\.\d+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Convert time to string with 2 decimal places
                time_value = float(match.group(1))
                data[name] = str(time_value)
                break
    
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

# Main app functionality
def main():
    # File uploader
    uploaded_file = st.file_uploader("Upload Leaderboard Image", type=["jpg", "jpeg", "png", "bmp"])
    
    # Date picker
    selected_date = st.date_input("Leaderboard Date", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")
    
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
            with st.spinner("Processing image..."):
                # Extract text using OCR
                extracted_text = extract_text_from_image(image)
                
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

if __name__ == "__main__":
    main()
