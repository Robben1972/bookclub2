import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import TOKEN, GROUP_CHAT_ID
from database import Database
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot and Dispatcher initialization
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
db = Database()

# States for FSM
class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_book_name = State()
    waiting_for_last_page = State()
    waiting_for_book_status = State()
    waiting_for_confirmation = State()
    waiting_for_admin_delete = State()

# Keyboards
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Today have read 📚"), KeyboardButton(text="Log out 🚪")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Today have read 📚"), KeyboardButton(text="Log out 🚪")],
            [KeyboardButton(text="Overall result 📊"), KeyboardButton(text="Delete users 🗑")]
        ],
        resize_keyboard=True
    )
    return keyboard

async def get_books_keyboard(user_id):
    books = db.get_user_books(user_id)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=book[1])] for book in books if not book[4]  # Add buttons for unfinished books
        ] + [[KeyboardButton(text="+ add new one  📕")]],  # Add the "+ add new one  📕" button as a separate row
        resize_keyboard=True
    )
    return keyboard

# Handlers
@dp.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if str(message.chat.id) == GROUP_CHAT_ID:
        return
    if db.get_user(user_id):
        if db.is_user_active(user_id):
            if db.is_admin(user_id):
                await message.answer("👋 Welcome back, Admin!", reply_markup=get_admin_keyboard())
                return
            await message.answer("<b>👋 Welcome back!</b>", reply_markup=get_main_keyboard())
        else:
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Join again 💠")]
                ],
                resize_keyboard=True
            )
            await message.answer("You have logged out. Would you like to join again? 🥹", reply_markup=keyboard)
    else:
        await message.answer("Welcome to the Book Club! Please enter your name:")
        await state.set_state(UserStates.waiting_for_name)

@dp.message(UserStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    name = message.text
    db.add_user(user_id, name, message.from_user.username or "N/A")
    await message.answer(f"Nice to meet you, {name}!", reply_markup=get_main_keyboard())
    await bot.send_message(GROUP_CHAT_ID, f"Oopppaaaa, yangi kitobxon qo'shildi! 🎉\n\n Kutib olilar: <b>{name}</b>")
    await state.clear()

@dp.message(lambda message: message.text == "Join again")
async def join_again(message: types.Message):
    user_id = message.from_user.id
    db.activate_user(user_id)
    await message.answer("👋 Welcome back!", reply_markup=get_main_keyboard())
    await bot.send_message(GROUP_CHAT_ID, f"Kimlarni ko'ryapmiz! \n\n<b>{db.get_user()[1]}</b> qaytib keldilar! 🎉")

@dp.message(lambda message: message.text == "Log out 🚪")
async def log_out(message: types.Message):
    user_id = message.from_user.id
    db.deactivate_user(user_id)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Join again")]
        ],
        resize_keyboard=True
    )
    await message.answer("You have logged out.", reply_markup=keyboard)
    await bot.send_message(GROUP_CHAT_ID, f"Og'ir judolik \n\n<b>{db.get_user(user_id)[1]}</b> bizni tark etdilar, umid qilamiz tez orada qaytadilar 👋")

@dp.message(lambda message: message.text == "Today have read 📚")
async def today_read(message: types.Message):
    user_id = message.from_user.id
    if not db.is_user_active(user_id):
        await message.answer("Please join again first.")
        return
    await message.answer("Select a book or add a new one:", reply_markup=await get_books_keyboard(user_id))

@dp.message(lambda message: message.text == "+ add new one  📕")
async def add_new_book(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not db.is_user_active(user_id):
        await message.answer("Please join again first.")
        return
    await message.answer("Enter the name of the book you started:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(UserStates.waiting_for_book_name)

@dp.message(UserStates.waiting_for_book_name)
async def process_book_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    book_name = message.text
    books = db.get_user_books(user_id)
    book = next((b for b in books if b[1] == book_name), None)
    if book is not None and book[-1]:
        await message.answer(f"You have already finished reading '{book_name}'. Please select another book or add a new one.", reply_markup=await get_books_keyboard(user_id))
        await state.clear()
        return
    if book:
        await message.answer(f"You selected the book: {book_name}\nEnter the last page you read (minimum 10 pages more than {book[3]}):")
    else:
        await message.answer("Enter the last page you read (minimum 10 pages):")
    await state.update_data(book_name=book_name)
    await state.set_state(UserStates.waiting_for_last_page)

@dp.message(UserStates.waiting_for_last_page)
async def process_last_page(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    try:
        last_page = int(message.text)
        data = await state.get_data()
        book_name = data.get("book_name")
        books = db.get_user_books(user_id)
        book = next((b for b in books if b[1] == book_name), None)
        
        if book:  # Existing book
            if (last_page - book[3]) < 10:  # Check against previous last_page
                await message.answer(f"Please enter a valid page number that is at least 10 pages more than {book[3]}.")
                return
            await state.update_data(start_page=book[3], last_page=last_page)
        else:  # New book
            if last_page < 10:
                await message.answer("You must read at least 10 pages.")
                return
            await state.update_data(start_page=1, last_page=last_page)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Finished", callback_data="book_finished"),
             InlineKeyboardButton(text="Not finished", callback_data="book_not_finished")]
        ])
        await message.answer("Is this book finished?", reply_markup=keyboard)
        await state.set_state(UserStates.waiting_for_book_status)
        
    except ValueError:
        await message.answer("Please enter a valid page number.")
        await state.set_state(UserStates.waiting_for_last_page)

@dp.callback_query(lambda c: c.data in ["book_finished", "book_not_finished"])
async def process_book_status(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    book_name = data.get("book_name")
    start_page = data.get("start_page")
    last_page = data.get("last_page")
    
    user = db.get_user(user_id)
    finished = callback.data == "book_finished"
    report = (f"👤 Reader name: {user[1]}\n"
              f"📚 Book name: {book_name}\n"
              f"💣 From Page: {start_page}\n"
              f"💣 To Page: {last_page}\n"
              f"💣 Overall: {last_page - start_page}\n"
              f"📅 {datetime.now().strftime('%d.%m.%Y')}\n"
              f"Finished: {'✅ Yes' if finished else '❌ No'}\n"
              f"📩 @shuhrat9111\n"
              f"#challange")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Yes", callback_data="send_to_group"),
         InlineKeyboardButton(text="No", callback_data="dont_send")]
    ])
    await callback.message.edit_text(f"Do you want to send this to the group?\n\n{report}", reply_markup=keyboard)
    await state.update_data(finished=finished)
    await state.set_state(UserStates.waiting_for_confirmation)

@dp.callback_query(lambda c: c.data in ["send_to_group", "dont_send"])
async def process_group_send(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    book_name = data.get("book_name")
    start_page = data.get("start_page")
    last_page = data.get("last_page")
    finished = data.get("finished")
    message = "Done!"
    
    if callback.data == "send_to_group":
        user = db.get_user(user_id)
        report = (f"👤 Reader name: {user[1]}\n"
                  f"📚 Book name: {book_name}\n"
                  f"💣 From Page: {start_page}\n"
                  f"💣 To Page: {last_page}\n"
                  f"💣 Overall: {last_page - start_page}\n"
                  f"📅 {datetime.now().strftime('%d.%m.%Y')}\n"
                  f"Finished: {'✅ Yes' if finished else '❌ No'}\n"
                  f"📩 @shuhrat9111\n"
                  f"#challange")
        await bot.send_message(GROUP_CHAT_ID, report)
        if finished:
            message += "Good luck dude, keep it up! 💪"
        
        # Update database only if sent to group
        books = db.get_user_books(user_id)
        book = next((b for b in books if b[1] == book_name), None)
        if book:
            db.update_book_progress(user_id, book_name, last_page, finished)
        else:
            db.add_book(user_id, book_name, start_page, last_page, finished)
    
    await callback.message.delete()
    await callback.message.answer(message, reply_markup=get_main_keyboard())
    await state.clear()

@dp.message(lambda message: message.text == "Overall result 📊")
async def overall_result(message: types.Message):
    user_id = message.from_user.id
    if not db.is_admin(user_id):
        await message.answer("You don't have permission to view this.")
        return
    
    users = db.get_all_users()
    messages = []
    current_message = "Overall result 📊s:\n\n"
    
    for user in users:
        books = db.get_user_books(user[0])
        user_info = f"User: {user[1]} (@{user[2]})\n"
        if books:
            user_info += "Books:\n"
            for book in books:
                status = "Finished" if book[4] else "In Progress"
                user_info += f"- {book[1]}: {book[2]}-{book[3]} ({status})\n"
        else:
            user_info += "No books recorded.\n"
        user_info += "\n"
        
        if len(current_message + user_info) > 4000:  # Telegram message limit
            messages.append(current_message)
            current_message = user_info
        else:
            current_message += user_info
    
    if current_message:
        messages.append(current_message)
    
    for msg in messages:
        await message.answer(msg)

@dp.message(lambda message: message.text == "Delete users 🗑")
async def delete_users(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not db.is_admin(user_id):
        await message.answer("You don't have permission to do this.")
        return
    
    users = db.get_all_users()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"{user[1]} (@{user[2]})")] for user in users
        ] + [[KeyboardButton(text="Cancel")]],  # Add a "Cancel" button as a separate row
        resize_keyboard=True
    )
    await message.answer("Select a user to delete:", reply_markup=keyboard)
    await state.set_state(UserStates.waiting_for_admin_delete)

@dp.message(UserStates.waiting_for_admin_delete)
async def process_delete_user(message: types.Message, state: FSMContext):
    if message.text == "Cancel":
        await message.answer("Cancelled.", reply_markup=get_admin_keyboard())
        await state.clear()
        return
    
    users = db.get_all_users()
    selected_user = next((u for u in users if f"{u[1]} (@{u[2]})" == message.text), None)
    if selected_user:
        db.delete_user(selected_user[0])
        await message.answer(f"User {selected_user[1]} deleted.", reply_markup=get_admin_keyboard())
    else:
        await message.answer("Invalid selection.", reply_markup=get_admin_keyboard())
    await state.clear()


@dp.message(lambda message: message.text)
async def select_book(message: types.Message, state: FSMContext):
    if message.text in [book[1] for book in db.get_user_books(message.from_user.id)]:
        user_id = message.from_user.id
        book_name = message.text
        books = db.get_user_books(user_id)
        book = next((b for b in books if b[1] == book_name), None)
        if book and book[4]:
            await message.answer(f"You have already finished reading '{book_name}'. Please select another book or add a new one.", reply_markup=await get_books_keyboard(user_id))
            await state.clear()
            return
        if book:
            await message.answer(f"You selected the book: {book_name}\nEnter the last page you read (minimum 10 pages more than {book[3]}):")
        else:
            await message.answer("Enter the last page you read (minimum 10 pages):")
        await state.update_data(book_name=book_name)
        await state.set_state(UserStates.waiting_for_last_page)
# Scheduled tasks
async def daily_report():
    db.clear_daily()
    users = db.get_all_users()
    report = "Daily Reading Report:\n\n"
    for user in users:
        if not db.is_user_active(user[0]):
            continue
        pages_read = db.get_daily_reading(user[0])
        report += f"{user[1]} (@{user[2]}) - {'Read ' + str(pages_read) + ' pages' if pages_read else 'Did not read'}\n"
    await bot.send_message(GROUP_CHAT_ID, report)

async def weekly_report():
    db.clear_weekly()
    top_reader = db.get_top_reader()
    if top_reader:
        await bot.send_message(GROUP_CHAT_ID, f"Congratulations to @{top_reader[2]} for reading the most pages this week!")

async def main():
    # Initialize scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_report, 'cron', hour=0, minute=0)
    scheduler.add_job(weekly_report, 'cron', day_of_week='sat', hour=9, minute=0)
    scheduler.start()
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())