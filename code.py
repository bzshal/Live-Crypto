import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import sys
import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get credentials and keys from environment variables
API_KEY = os.getenv('CMC_API_KEY')
SPREADSHEET_KEY = os.getenv('SPREADSHEET_KEY')
UPDATE_INTERVAL = int(os.getenv('UPDATE_INTERVAL', '300'))  # Default to 300 seconds if not specified

# Try to parse credentials safely
try:
    CREDENTIALS = json.loads(os.getenv('CREDENTIALS', '{}'))
except json.JSONDecodeError:
    print("Invalid CREDENTIALS format in environment variable")
    sys.exit(1)

API_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'

IST = timezone(timedelta(hours=5, minutes=30))

# Validate environment variables
required_env_vars = ['CMC_API_KEY', 'SPREADSHEET_KEY', 'CREDENTIALS']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    print(f"Missing required environment variables: {', '.join(missing_vars)}")
    sys.exit(1)

def fetch_live_data():
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': API_KEY,
    }
    params = {
        'start': '1',
        'limit': '50',
        'convert': 'USD'
    }
    try:
        response = requests.get(API_URL, headers=headers, params=params)
        data = response.json()
        if response.status_code != 200:
            raise Exception(data.get('status', {}).get('error_message', 'Unknown error'))
        return data['data']
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def analyze_data(data):
    if not data:
        return None

    top_5 = sorted(data, key=lambda x: x['quote']['USD']['market_cap'], reverse=True)[:5]

    total_price = sum(item['quote']['USD']['price'] for item in data)
    average_price = total_price / len(data)

    highest_change = max(data, key=lambda x: x['quote']['USD']['percent_change_24h'])
    lowest_change = min(data, key=lambda x: x['quote']['USD']['percent_change_24h'])

    analysis = {
        'top_5': top_5,
        'average_price': average_price,
        'highest_change': highest_change,
        'lowest_change': lowest_change
    }
    return analysis

def authenticate_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(CREDENTIALS, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_KEY).sheet1
        return sheet
    except Exception as e:
        print(f"Error authenticating Google Sheets: {e}")
        return None

def update_google_sheet(sheet, data, analysis):
    if not sheet or not data or not analysis:
        print("Insufficient data to update sheet")
        return

    try:
        sheet.clear()

        # Get current timestamp in IST
        current_time = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

        # Add last updated time at the top of the sheet
        sheet.append_row(['Last Updated', current_time])
        sheet.append_row([])  # Add an empty row for spacing

        headers = [
            'Cryptocurrency Name',
            'Symbol',
            'Current Price (USD)',
            'Market Capitalization',
            '24h Trading Volume',
            'Price Change (24h)'
        ]
        sheet.append_row(headers)

        for item in data:
            row = [
                item['name'],
                item['symbol'],
                f"{item['quote']['USD']['price']:,.2f}",
                f"{item['quote']['USD']['market_cap']:,.2f}",
                f"{item['quote']['USD']['volume_24h']:,.2f}",
                item['quote']['USD']['percent_change_24h']
            ]
            sheet.append_row(row)

        sheet.append_row([])
        sheet.append_row(['Data Analysis'])

        top_5_names = ', '.join([crypto['name'] for crypto in analysis['top_5']])
        sheet.append_row(['Top 5 Cryptocurrencies by Market Cap', top_5_names])

        sheet.append_row(['Average Price of Top 50 Cryptocurrencies (USD)', f"{analysis['average_price']:,.2f}"])

        sheet.append_row([
            'Highest 24h Price Change',
            analysis['highest_change']['name'],
            analysis['highest_change']['quote']['USD']['percent_change_24h']
        ])

        sheet.append_row([
            'Lowest 24h Price Change',
            analysis['lowest_change']['name'],
            analysis['lowest_change']['quote']['USD']['percent_change_24h']
        ])

        print(f"Google Sheet updated at {current_time}")

    except Exception as e:
        print(f"Error updating Google Sheet: {e}")
def main():
    sheet = authenticate_google_sheet()
    if not sheet:
        print("Failed to authenticate Google Sheet. Exiting.")
        sys.exit(1)

    while True:
        try:
            data = fetch_live_data()
            if data:
                analysis = analyze_data(data)
                update_google_sheet(sheet, data, analysis)
            time.sleep(UPDATE_INTERVAL)
        except Exception as e:
            print(f"An error occurred: {e}")
            time.sleep(UPDATE_INTERVAL)

if __name__ == '__main__':
    main()