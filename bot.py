import os
import json
import requests
import base64
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import logging
import asyncio
import threading
from flask import Flask
# ========== FLASK SETUP ==========
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram Bot is running on Koyeb"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    """Run Flask web server for health checks"""
    port = int(os.getenv('PORT', 8080))
    print(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ========== BOT CONFIGURATION ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========= ENVIRONMENT VARIABLES ==========
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Safety checks
if not TELEGRAM_BOT_TOKEN:
    raise Exception("❌ TELEGRAM_BOT_TOKEN is missing! Set it in Koyeb.")

if not GITHUB_TOKEN:
    raise Exception("❌ GITHUB_TOKEN is missing! Set it in Koyeb.")
GITHUB_REPO_OWNER = "WolfT31"
GITHUB_REPO_NAME = "SPORTVIP"
GITHUB_FILE_PATH = "Users.json"
DEFAULT_DATE = "2025-12-12"

# Store user states for conversation flow
user_states = {}

# ========== GITHUB FUNCTIONS ==========
def load_users():
    """
    Load users from GitHub JSON file
    Returns: List of users or empty list if error
    """
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.raw"
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_FILE_PATH}"
    
    try:
        logger.info(f"📥 Loading users from GitHub: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            try:
                # Try to parse as JSON
                data = json.loads(response.text)
                logger.info(f"✅ JSON parsed successfully, type: {type(data)}")
                
                # Your file contains a direct JSON array, so return it as is
                if isinstance(data, list):
                    logger.info(f"✅ Successfully loaded {len(data)} users")
                    return data
                elif isinstance(data, dict):
                    # If it's a dict with 'users' key
                    if "users" in data:
                        users_list = data.get("users", [])
                        logger.info(f"✅ Loaded {len(users_list)} users from dict")
                        return users_list
                    else:
                        # If dict without 'users' key, check if it's actually an array
                        logger.warning("⚠️ JSON is dict but no 'users' key found")
                        return []
                else:
                    logger.error(f"❌ Unexpected data type: {type(data)}")
                    return []
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse JSON: {e}")
                logger.error(f"Response text (first 200 chars): {response.text[:200]}")
                return []
                
        elif response.status_code == 404:
            logger.error("❌ Users.json file not found on GitHub!")
            return []
        else:
            logger.error(f"❌ GitHub API error (HTTP {response.status_code})")
            logger.error(f"Response: {response.text[:200]}")
            return []
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error loading users: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"❌ Unexpected error loading users: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def save_users(users):
    """
    Save users to GitHub JSON file
    Returns: True if successful, False otherwise
    """
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_FILE_PATH}"
    
    try:
        # First, try to get the existing file to get its SHA
        logger.info("📤 Getting file SHA from GitHub...")
        get_response = requests.get(url, headers=headers, timeout=10)
        
        sha = ""
        if get_response.status_code == 200:
            sha = get_response.json().get("sha", "")
            logger.info(f"✅ Got file SHA: {sha[:20]}...")
        elif get_response.status_code == 404:
            logger.error("❌ File not found on GitHub. Cannot update.")
            return False
        else:
            logger.error(f"❌ Failed to get file info (HTTP {get_response.status_code})")
            logger.error(f"Error: {get_response.text[:200]}")
            return False

        # Prepare the content
        content = json.dumps(users, indent=2, ensure_ascii=False)
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        # Prepare the commit data
        commit_data = {
            "message": f"Bot update: {len(users)} users - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": encoded_content,
            "sha": sha,
            "branch": "main"
        }
        
        # Save to GitHub
        logger.info(f"💾 Uploading {len(users)} users to GitHub...")
        put_response = requests.put(url, headers=headers, json=commit_data, timeout=15)
        
        if put_response.status_code in [200, 201]:
            logger.info("✅ Successfully saved users to GitHub")
            return True
        else:
            error_msg = put_response.text[:500] if put_response.text else "No error message"
            logger.error(f"❌ Failed to save to GitHub (HTTP {put_response.status_code})")
            logger.error(f"Error: {error_msg}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error saving users: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error saving users: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# ========== HELPER FUNCTIONS ==========
def generate_random_password(length=4):
    """Generate a random password"""
    if length > 4:
        length = 4
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def generate_random_username():
    """Generate a random username"""
    prefix = "wolf_"
    max_suffix_length = 8 - len(prefix)
    if max_suffix_length <= 0:
        return prefix[:8]
    suffix = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(max_suffix_length))
    return prefix + suffix

def get_days_left(expire_str):
    """Calculate days until expiration"""
    try:
        expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        days = (expire_date - today).days
        return days
    except Exception:
        return -999

# ========== TELEGRAM HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    welcome_text = """
🏆 *ADMIN PANEL SERVER BOT* 🏆

*habari kiongozi mimi ni bot wa kukusaidia kusajiri na kumanage accounts zote za app ya aviator*

*Available Commands:*
/start - See if Bot is Online
/add - Add new user
/remove - Remove user
/list - List all users
/help - Show help information
/debug - Check bot status

      𝚃𝚞𝚖𝚒𝚊 𝙱𝚞𝚝𝚝𝚘𝚗 𝚊𝚞 𝙲𝚘𝚖𝚖𝚊𝚗𝚍𝚜
"""
    
    keyboard = [
        [InlineKeyboardButton("➕ Add User", callback_data='add_user')],
        [InlineKeyboardButton("🗑️ Remove User", callback_data='remove_user')],
        [InlineKeyboardButton("📋 List Users", callback_data='list_users')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')],
        [InlineKeyboardButton("🔍 Debug", callback_data='debug')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    help_text = """
*📖 HELP MENU*

*How to use this bot:*

1. *Add User*: Click 'Add User' button or type /add
   - You'll be prompted for:
     • Device ID
     • Username
     • Password
     • Expiration Date (YYYY-MM-DD)
     • Offline Access (yes/no)

2. *Remove User*: Click 'Remove User' or type /remove
   - Enter the username to remove
   - If multiple users exist, you'll choose which one

3. *List Users*: Click 'List Users' or type /list
   - Shows all approved users with details

4. *Debug*: Click 'Debug' or type /debug
   - Check bot and GitHub connection status

*Note:* All data is stored in GitHub repository.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to check bot status"""
    # Test GitHub connection
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_FILE_PATH}"
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        file_exists = response.status_code == 200
        file_status = response.status_code
        
        # Load users to count them
        users = load_users()
        user_count = len(users)
        
        # Test save with current data
        test_save = False
        if users:
            # Try to save the same data back
            test_save = save_users(users)
        
        debug_text = f"""
🔍 *BOT DEBUG INFORMATION*

*GitHub Status:*
• Repository: `{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}`
• File: `{GITHUB_FILE_PATH}`
• File Exists: `{file_exists}` (Status: {file_status})
• Users Loaded: `{user_count}` users
• Save Test: `{"✅ Success" if test_save else "❌ Failed"}`

*Bot Status:*
• State Storage: `{len(user_states)}` active conversations

*Environment:*
• Default Date: `{DEFAULT_DATE}`
• Platform: `Koyeb`
"""
        
    except Exception as e:
        debug_text = f"""
❌ *DEBUG ERROR*

Error: `{str(e)}`

Check if:
1. GitHub token is valid
2. Repository exists: `{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}`
3. File exists: `{GITHUB_FILE_PATH}`
"""
    
    await update.message.reply_text(debug_text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'add_user':
        user_states[user_id] = {'state': 'awaiting_device_id'}
        await query.edit_message_text(
            "Please enter the *Device ID*:",
            parse_mode='Markdown'
        )
    
    elif query.data == 'remove_user':
        user_states[user_id] = {'state': 'awaiting_remove_username'}
        await query.edit_message_text(
            "Please enter the *Username* to remove:",
            parse_mode='Markdown'
        )
    
    elif query.data == 'list_users':
        await list_users_command(update, context, query=query)
    
    elif query.data == 'help':
        await help_command(update, context)
        # Keep the original message with buttons
        await query.edit_message_text(
            query.message.text,
            parse_mode='Markdown',
            reply_markup=query.message.reply_markup
        )
    
    elif query.data == 'debug':
        await debug_command(update, context)
    
    elif query.data == 'cancel':
        if user_id in user_states:
            user_states.pop(user_id, None)
        await query.edit_message_text(
            "Operation cancelled. Use /start to see menu again.",
            parse_mode='Markdown'
        )

async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the add user process."""
    user_id = update.effective_user.id
    user_states[user_id] = {'state': 'awaiting_device_id'}
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Let's add a new user.\n\nPlease enter the *Device ID*:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the remove user process."""
    user_id = update.effective_user.id
    user_states[user_id] = {'state': 'awaiting_remove_username'}
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='cancel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Please enter the *Username* to remove:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """List all users."""
    users = load_users()
    
    if not users:
        text = "📭 *No approved users yet.*\n\nUse /add to add your first user."
    else:
        text = f"📋 *APPROVED USERS* ({len(users)} total)\n\n"
        for i, user in enumerate(users, 1):
            days_left = get_days_left(user.get('expiresAt', DEFAULT_DATE))
            status = "✅" if days_left > 0 else "❌"
            
            text += f"*User #{i}*\n"
            text += f"{status} *ID:* `{user.get('id', 'N/A')}`\n"
            text += f"👤 *Username:* `{user.get('username', 'N/A')}`\n"
            text += f"🔑 *Password:* `{user.get('password', 'N/A')}`\n"
            text += f"📅 *Expires:* `{user.get('expiresAt', DEFAULT_DATE)}` "
            text += f"({days_left} days left)\n"
            text += f"💾 *Offline Access:* `{user.get('allowOffline', False)}`\n"
            text += "━" * 20 + "\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')],
        [InlineKeyboardButton("🔄 Refresh", callback_data='list_users')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages based on state."""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    if user_id not in user_states:
        keyboard = [
            [InlineKeyboardButton("➕ Add User", callback_data='add_user')],
            [InlineKeyboardButton("🗑️ Remove User", callback_data='remove_user')],
            [InlineKeyboardButton("📋 List Users", callback_data='list_users')],
            [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Please use the buttons or commands to interact with the bot.",
            reply_markup=reply_markup
        )
        return
    
    state = user_states[user_id]['state']
    
    if state == 'awaiting_device_id':
        user_states[user_id]['device_id'] = message_text
        user_states[user_id]['state'] = 'awaiting_username'
        await update.message.reply_text(
            "Great! Now enter the *Username*:",
            parse_mode='Markdown'
        )
    
    elif state == 'awaiting_username':
        user_states[user_id]['username'] = message_text
        user_states[user_id]['state'] = 'awaiting_password'
        await update.message.reply_text(
            "Now enter the *Password*:",
            parse_mode='Markdown'
        )
    
    elif state == 'awaiting_password':
        user_states[user_id]['password'] = message_text
        user_states[user_id]['state'] = 'awaiting_expiration'
        await update.message.reply_text(
            f"⏳ Enter *Expiration Date* (YYYY-MM-DD):\nExample: `{DEFAULT_DATE}`",
            parse_mode='Markdown'
        )
    
    elif state == 'awaiting_expiration':
        expiresAt = message_text if message_text else DEFAULT_DATE
        try:
            datetime.strptime(expiresAt, "%Y-%m-%d")
            user_states[user_id]['expiresAt'] = expiresAt
            user_states[user_id]['state'] = 'awaiting_offline'
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes", callback_data='offline_yes'),
                    InlineKeyboardButton("❌ No", callback_data='offline_no')
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "Allow *Offline Access*?",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid date format. Please use YYYY-MM-DD. Try again:"
            )
    
    elif state == 'awaiting_remove_username':
        username = message_text
        users = load_users()
        
        if not users:
            await update.message.reply_text("❌ No users found in database.")
            user_states.pop(user_id, None)
            return
        
        matching_users = [user for user in users if user.get("username") == username]
        
        if not matching_users:
            await update.message.reply_text(f"❌ User with username '{username}' not found.")
            user_states.pop(user_id, None)
            return
        
        if len(matching_users) > 1:
            text = f"Found *{len(matching_users)}* users with username '{username}':\n\n"
            for i, user in enumerate(matching_users, 1):
                text += f"*Option {i}:*\n"
                text += f"Device ID: `{user.get('id', 'N/A')}`\n"
                text += f"Username: `{user.get('username', 'N/A')}`\n"
                text += f"Expiration: `{user.get('expiresAt', DEFAULT_DATE)}`\n\n"
            
            text += "Enter the number to remove, or type 'all' to remove all:"
            
            user_states[user_id]['remove_username'] = username
            user_states[user_id]['matching_users'] = matching_users
            user_states[user_id]['state'] = 'awaiting_remove_choice'
            
            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            user = matching_users[0]
            user_states[user_id]['remove_user'] = user
            user_states[user_id]['state'] = 'confirm_remove_single'
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, Remove", callback_data='confirm_remove'),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"Found user:\n\n"
            text += f"ID: `{user.get('id', 'N/A')}`\n"
            text += f"Username: `{user.get('username', 'N/A')}`\n"
            text += f"Expiration: `{user.get('expiresAt', DEFAULT_DATE)}`\n\n"
            text += "Are you sure you want to remove this user?"
            
            await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    
    elif state == 'awaiting_remove_choice':
        choice = message_text.lower()
        
        if choice == 'all':
            user_states[user_id]['state'] = 'confirm_remove_all'
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, Remove All", callback_data='confirm_remove_all'),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"⚠️ Are you sure you want to remove ALL users with username '{user_states[user_id]['remove_username']}'?",
                reply_markup=reply_markup
            )
        elif choice.isdigit():
            idx = int(choice) - 1
            matching_users = user_states[user_id]['matching_users']
            
            if 0 <= idx < len(matching_users):
                user_states[user_id]['remove_user'] = matching_users[idx]
                user_states[user_id]['state'] = 'confirm_remove_single'
                
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Yes, Remove", callback_data='confirm_remove'),
                        InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                user = matching_users[idx]
                text = f"Selected user:\n\n"
                text += f"ID: `{user.get('id', 'N/A')}`\n"
                text += f"Username: `{user.get('username', 'N/A')}`\n"
                text += f"Expiration: `{user.get('expiresAt', DEFAULT_DATE)}`\n\n"
                text += "Are you sure you want to remove this user?"
                
                await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                await update.message.reply_text("❌ Invalid choice. Please try again.")
        else:
            await update.message.reply_text("❌ Invalid input. Please enter a number or 'all'.")

async def handle_offline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle offline access choice."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id not in user_states or user_states[user_id].get('state') != 'awaiting_offline':
        return
    
    if query.data == 'offline_yes':
        allowOffline = True
    elif query.data == 'offline_no':
        allowOffline = False
    else:
        return
    
    user_data = user_states[user_id]
    
    try:
        users = load_users()
        
        # Check for duplicates
        duplicate = any(
            user.get("username") == user_data['username'] and 
            user.get("password") == user_data['password'] 
            for user in users
        )
        
        if duplicate:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes, Add Anyway", callback_data='add_anyway'),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            user_states[user_id]['allowOffline'] = allowOffline
            user_states[user_id]['state'] = 'confirm_duplicate'
            
            await query.edit_message_text(
                "⚠️ This username/password combination already exists.\n\nDo you want to add it anyway?",
                reply_markup=reply_markup
            )
            return
        
        # Add new user
        new_user = {
            "id": user_data['device_id'],
            "username": user_data['username'],
            "password": user_data['password'],
            "expiresAt": user_data['expiresAt'],
            "allowOffline": allowOffline
        }
        
        users.append(new_user)
        
        if save_users(users):
            success_text = f"""
✅ *ACCOUNT CREATION SUCCESS*

🆔 *Device ID:* `{user_data['device_id']}`
👤 *Username:* `{user_data['username']}`
🔑 *Password:* `{user_data['password']}`
📅 *Expires:* `{user_data['expiresAt']}`
💾 *Offline Access:* `{allowOffline}`

💠 *Total users in database: {len(users)}*
"""
            
            keyboard = [[InlineKeyboardButton("🏠 Back to Menu", callback_data='menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
            user_states.pop(user_id, None)
        else:
            await query.edit_message_text(
                "❌ Failed to save user to database.\n\n"
                "Possible reasons:\n"
                "1. GitHub token expired\n"
                "2. No write permissions\n"
                "3. Network issue\n\n"
                "Use /debug to check bot status."
            )
            user_states.pop(user_id, None)
            
    except Exception as e:
        logger.error(f"Error adding user: {str(e)}")
        await query.edit_message_text(f"❌ Error: {str(e)[:200]}")
        user_states.pop(user_id, None)

async def handle_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation callbacks."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'confirm_remove':
        if user_id in user_states and user_states[user_id].get('state') == 'confirm_remove_single':
            user_to_remove = user_states[user_id]['remove_user']
            users = load_users()
            users = [user for user in users if user != user_to_remove]
            
            if save_users(users):
                await query.edit_message_text("✅ User successfully removed!")
            else:
                await query.edit_message_text("❌ Failed to remove user from database.")
            
            user_states.pop(user_id, None)
    
    elif query.data == 'confirm_remove_all':
        if user_id in user_states and user_states[user_id].get('state') == 'confirm_remove_all':
            username = user_states[user_id]['remove_username']
            users = load_users()
            users = [user for user in users if user.get("username") != username]
            
            if save_users(users):
                await query.edit_message_text(f"✅ All users with username '{username}' successfully removed!")
            else:
                await query.edit_message_text("❌ Failed to remove users from database.")
            
            user_states.pop(user_id, None)
    
    elif query.data == 'add_anyway':
        if user_id in user_states and user_states[user_id].get('state') == 'confirm_duplicate':
            user_data = user_states[user_id]
            
            users = load_users()
            users.append({
                "id": user_data['device_id'],
                "username": user_data['username'],
                "password": user_data['password'],
                "expiresAt": user_data['expiresAt'],
                "allowOffline": user_data['allowOffline']
            })
            
            if save_users(users):
                success_text = f"""
✅ *ACCOUNT CREATED SUCCESSFULLY*

🆔 *User ID:* `{user_data['device_id']}`
👤 *Username:* `{user_data['username']}`
🔑 *Password:* `{user_data['password']}`
📅 *Expires:* `{user_data['expiresAt']}`
💾 *Offline Access:* `{user_data['allowOffline']}`

💠 *Coded by WOLF*
"""
                keyboard = [[InlineKeyboardButton("🏠 Back to Menu", callback_data='menu')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(success_text, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                await query.edit_message_text("❌ Failed to save user to database.")
            
            user_states.pop(user_id, None)
    
    elif query.data == 'menu':
        welcome_text = """
🏆 *ADMIN PANEL SERVER BOT* 🏆

Karibu kwenye Database Management Bot!

*Available Commands:*
/start - Show this welcome message
/add - Add new user
/remove - Remove user
/list - List all users
/help - Show help information
/debug - Check bot status
"""
        
        keyboard = [
            [InlineKeyboardButton("➕ Add User", callback_data='add_user')],
            [InlineKeyboardButton("🗑️ Remove User", callback_data='remove_user')],
            [InlineKeyboardButton("📋 List Users", callback_data='list_users')],
            [InlineKeyboardButton("ℹ️ Help", callback_data='help')],
            [InlineKeyboardButton("🔍 Debug", callback_data='debug')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(welcome_text, parse_mode='Markdown', reply_markup=reply_markup)
        if user_id in user_states:
            user_states.pop(user_id, None)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors."""
    logger.error(f"Update {update} caused error {context.error}")
    
    # Send error message to user
    if update and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ An error occurred. Please try again or use /debug to check bot status."
            )
        except:
            pass

# ========== APPLICATION SETUP ==========
async def setup_application():
    """Create and configure the bot application."""
    
    application = Application.builder() \
        .token(TELEGRAM_BOT_TOKEN) \
        .read_timeout(30.0) \
        .connect_timeout(30.0) \
        .pool_timeout(20.0) \
        .build()
    
    # Register all handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_user_command))
    application.add_handler(CommandHandler("remove", remove_user_command))
    application.add_handler(CommandHandler("list", list_users_command))
    application.add_handler(CommandHandler("debug", debug_command))
    
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(add_user|remove_user|list_users|help|debug|cancel)$'))
    application.add_handler(CallbackQueryHandler(handle_offline_callback, pattern='^(offline_yes|offline_no)$'))
    application.add_handler(CallbackQueryHandler(handle_confirm_callback, pattern='^(confirm_remove|confirm_remove_all|add_anyway|menu)$'))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    return application

# ========== MAIN FUNCTION (WEBHOOK MODE FOR KOYEB) ==========
async def main():
    print("=" * 50)
    print("🤖 STARTING BOT ON KOYEB USING WEBHOOKS")
    print("=" * 50)
    print(f"🔗 Bot token: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"🌐 GitHub Repo: {GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}")
    print(f"📁 Data file: {GITHUB_FILE_PATH}")
    print("⚡ Mode: Webhook")
    print("=" * 50)

    # Test GitHub connection
    print("🔍 Testing GitHub connection...")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/contents/{GITHUB_FILE_PATH}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ GitHub connection successful!")
            users = load_users()
            print(f"✅ Loaded {len(users)} existing users")
        else:
            print(f"❌ GitHub connection failed (HTTP {response.status_code})")
            print(f"Error: {response.text[:200]}")
    except Exception as e:
        print(f"❌ GitHub connection error: {str(e)}")

    # Start Flask health server in background
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask health server started")

    # Build bot application
    application = await setup_application()

    # Webhook URL
    KOYEB_APP = os.getenv("KOYEB_APP_NAME")  # You MUST add this in Koyeb Secrets
    if not KOYEB_APP:
        raise Exception("❌ Missing KOYEB_APP_NAME in Koyeb Secrets!")

    webhook_url = f"https://{KOYEB_APP}.koyeb.app/{TELEGRAM_BOT_TOKEN}"
    port = int(os.getenv("PORT", 8080))

    print(f"🌐 Setting webhook: {webhook_url}")

    # Set webhook
    await application.bot.set_webhook(webhook_url)

    print("📡 Webhook set successfully! Starting webhook listener...")

    # Start webhook listener
    await application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=webhook_url
    )


# ========== ENTRY POINT ==========
if __name__ == "__main__":
    print("🚀 Launching Telegram bot with Webhook mode on Koyeb")
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
