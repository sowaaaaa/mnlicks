import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import db
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatType, ContentType
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery,
    InputMediaPhoto, InputRichMessage, InputRichBlockSlideshow, InputRichBlockPhoto, RichBlockCaption,
    RichTextCustomEmoji, BotCommand,
)
from aiohttp import ClientError, ClientSession
from aiosend import CryptoPay
from aiosend.types import Invoice
from dotenv import load_dotenv

load_dotenv()

LOG_FILE = Path(__file__).parent / "bot.log"


def setup_logging():
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, logging.StreamHandler()])


setup_logging()

dp = Dispatcher()
cp = CryptoPay(os.environ["CRYPTO_PAY_TOKEN"])
ADMIN_IDS = {int(x) for x in os.environ["ADMIN_IDS"].split(",")}
CHAT_ID = int(os.environ["CHAT_ID"]) if os.environ.get("CHAT_ID") else None
ARCHIVE_CHAT_ID = int(os.environ["ARCHIVE_CHAT_ID"])
SEASON_END_DATE = datetime.fromisoformat(os.environ["SEASON_END_DATE"])
PLATEGA_BASE_URL = os.environ.get("PLATEGA_BASE_URL", "https://app.platega.io").rstrip("/")
PLATEGA_MERCHANT_ID = os.environ.get("PLATEGA_MERCHANT_ID")
PLATEGA_SECRET = os.environ.get("PLATEGA_SECRET")
PLATEGA_RETURN_URL = os.environ.get("PLATEGA_RETURN_URL", "https://t.me/mnlicks")
PLATEGA_FAILED_URL = os.environ.get("PLATEGA_FAILED_URL", PLATEGA_RETURN_URL)
HELLO_PHOTO = str(Path(__file__).parent / "hello.jpg")
ULTIMATE_PHOTO = str(Path(__file__).parent / "ultimate.png")
STANDART_PHOTO = str(Path(__file__).parent / "standart.png")
FEEDBACK_DIR = Path(__file__).parent / "FC_slideshow"
FEEDBACK_PHOTOS = [
    str(p) for p in sorted(FEEDBACK_DIR.glob("*.jpg"), key=lambda p: int(p.stem))
]

SERVICE_CONTENT_TYPES = {
    ContentType.NEW_CHAT_MEMBERS,
    ContentType.LEFT_CHAT_MEMBER,
    ContentType.NEW_CHAT_TITLE,
    ContentType.NEW_CHAT_PHOTO,
    ContentType.DELETE_CHAT_PHOTO,
    ContentType.GROUP_CHAT_CREATED,
    ContentType.PINNED_MESSAGE,
    ContentType.MESSAGE_AUTO_DELETE_TIMER_CHANGED,
    ContentType.VIDEO_CHAT_SCHEDULED,
    ContentType.VIDEO_CHAT_STARTED,
    ContentType.VIDEO_CHAT_ENDED,
    ContentType.VIDEO_CHAT_PARTICIPANTS_INVITED,
}

DEFAULT_HELLO_TEXT = '''<tg-emoji emoji-id="5242358694049496372">🤝</tg-emoji> Приветствую , здесь ты можешь вступить в наше комьюнити по заработку монет в <b>EA FC</b>

<tg-emoji emoji-id="5424972470023104089">🔥</tg-emoji> Наши участники окупают подписку уже через три дня
В среднем профит за месяц может составлять
<b>БОЛЕЕ 5-ТИ МИЛЛИОНОВ</b>

<tg-emoji emoji-id="5377735646607610551">Ⓜ️</tg-emoji> Если ты желаешь задать вопрос или получить дополнительную информацию перед покупкой, то обращайся: @mnlicks'''


def get_hello_text() -> str:
    return db.get_setting('hello_text', DEFAULT_HELLO_TEXT)


def get_hello_photo() -> str | FSInputFile:
    photo_id = db.get_setting('hello_photo_id')
    return photo_id if photo_id else FSInputFile(HELLO_PHOTO)


def track_potential_member(user) -> None:
    if user and user.id not in ADMIN_IDS and not db.has_active_subscription(user.id):
        db.add_grandfather_members([(user.id, user.username)])


DEFAULT_TARIFFS_TEXT = '📍Главное меню » Выбор тарифа\n\n🗂 Выберите тариф:'


def get_tariffs_text() -> str:
    return db.get_setting('tariffs_text', DEFAULT_TARIFFS_TEXT)

hello_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Вступить в MnlicksTrade', callback_data='join')],
    [InlineKeyboardButton(text='Отзывы', callback_data='feedbacks')],
    [InlineKeyboardButton(text='Задать вопрос', url="https://t.me/mnlicks")],
    [InlineKeyboardButton(text='Инфо 👨‍💻', callback_data='info')],
])

plans_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='🔥 MnlicksTrade + MnlicksMentality 1 месяц', callback_data='month')],
    [InlineKeyboardButton(text='☘️ MnlicksTrade + MnlicksMentality На FC 27', callback_data='season')],
    [InlineKeyboardButton(text='« Назад', callback_data='back')],
])

PLANS = {
    'month': {'amount': 1, 'label': 'MnlicksTrade + MnlicksMentality', 'term': '1 месяц', 'short': '1 месяц'},
    'season': {'amount': 6000, 'label': 'MnlicksTrade + MnlicksMentality', 'term': 'Весь период FC 27', 'short': 'FC 27'},
}


def tariffs_screen_text() -> str:
    return get_tariffs_text()


def access_granted_text(plan_key: str, link: str) -> str:
    short = PLANS[plan_key]['short']
    return (
        f'<tg-emoji emoji-id="5278411813468269386">✅</tg-emoji> <b>Оплата</b> <i><b>подтверждена!\n'
        f'» </b>MnlicksTrade • {short} </i>\n\n'
        f'Твоя персональная ссылка:\n'
        f'<i>»</i> {link}'
    )


def payment_method_inline(plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Оплата картой', callback_data=f'card_{plan_key}', icon_custom_emoji_id='5425008221330880308')],
        [InlineKeyboardButton(text='USDT • TRC-20', callback_data=f'crypto_{plan_key}', icon_custom_emoji_id='5361914370068613491')],
        [InlineKeyboardButton(text='« Назад', callback_data='join')],
    ])


USER_AGREEMENT_URL = 'https://telegra.ph/Polzovatelskoe-soglashenie-08-27-55'
PRIVACY_POLICY_URL = 'https://telegra.ph/Politika-konfidencialnosti-08-27-76'


def info_text() -> str:
    return (
        '📍Главное меню » Инфо\n\n'
        'Документы MnlicksTrade всегда доступны здесь:'
    )


info_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Пользовательское соглашение', url=USER_AGREEMENT_URL)],
    [InlineKeyboardButton(text='Политика конфиденциальности', url=PRIVACY_POLICY_URL)],
    [InlineKeyboardButton(text='« Назад', callback_data='back')],
])


feedback_back_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='« Назад', callback_data='back')],
])


def get_feedback_photo_sources() -> list:
    cached_raw = db.get_setting('feedback_photo_ids')
    if cached_raw:
        cached = json.loads(cached_raw)
        if len(cached) == len(FEEDBACK_PHOTOS):
            return cached
    return [FSInputFile(path) for path in FEEDBACK_PHOTOS]


def feedback_rich_message() -> InputRichMessage:
    slides = [
        InputRichBlockPhoto(photo=InputMediaPhoto(media=src))
        for src in get_feedback_photo_sources()
    ]
    caption = RichBlockCaption(text=[
        RichTextCustomEmoji(custom_emoji_id='5424972470023104089', alternative_text='🔥'),
        ' Отзывы участников',
    ])
    return InputRichMessage(blocks=[InputRichBlockSlideshow(blocks=slides, caption=caption)])


def cache_feedback_photo_ids(sent: Message):
    if db.get_setting('feedback_photo_ids'):
        return
    try:
        slideshow = sent.rich_message.blocks[0]
        ids = [block.photo[-1].file_id for block in slideshow.blocks]
        if len(ids) != len(FEEDBACK_PHOTOS):
            return
    except (AttributeError, IndexError, TypeError):
        return
    db.set_setting('feedback_photo_ids', json.dumps(ids))


def plan_expiry(plan_key: str) -> datetime:
    if plan_key == 'season':
        return SEASON_END_DATE
    return datetime.now() + timedelta(days=30)


async def notify_archive(bot, text: str):
    try:
        await bot.send_message(ARCHIVE_CHAT_ID, text, parse_mode='HTML')
    except TelegramAPIError:
        logging.exception('Failed to notify archive chat')


def platega_headers() -> dict[str, str]:
    if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET:
        raise RuntimeError('Platega credentials are not configured')
    return {
        'X-MerchantId': PLATEGA_MERCHANT_ID,
        'X-Secret': PLATEGA_SECRET,
        'Content-Type': 'application/json',
    }


async def create_platega_payment(user, plan_key: str) -> tuple[str, str]:
    plan = PLANS[plan_key]
    username = user.username if user else None
    payload = json.dumps(
        {'user_id': user.id, 'plan_key': plan_key},
        ensure_ascii=False,
        separators=(',', ':'),
    )
    body = {
        'paymentDetails': {
            'amount': plan['amount'],
            'currency': 'RUB',
        },
        'description': f'MnlicksTrade - {plan["short"]}',
        'return': PLATEGA_RETURN_URL,
        'failedUrl': PLATEGA_FAILED_URL,
        'payload': payload,
        'metadata': {
            'userId': str(user.id),
            'userName': f'@{username}' if username else str(user.id),
        },
    }
    async with ClientSession() as session:
        async with session.post(
            f'{PLATEGA_BASE_URL}/v2/transaction/process',
            headers=platega_headers(),
            json=body,
        ) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f'Platega create failed: {response.status} {data}')

    transaction_id = data.get('transactionId') or data.get('id')
    payment_url = data.get('url')
    if not transaction_id or not payment_url:
        raise RuntimeError(f'Platega response is missing transaction id or url: {data}')

    db.save_platega_payment(transaction_id, user.id, username, plan_key, plan['amount'])
    return transaction_id, payment_url


async def get_platega_payment_status(transaction_id: str) -> dict:
    async with ClientSession() as session:
        async with session.get(
            f'{PLATEGA_BASE_URL}/transaction/{transaction_id}',
            headers=platega_headers(),
        ) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f'Platega status failed: {response.status} {data}')
            return data


def platega_amount_matches(value, expected: int) -> bool:
    try:
        return float(value) == float(expected)
    except (TypeError, ValueError):
        return False


async def process_platega_payment(bot, payment: tuple[str, int, str | None, str, int]):
    transaction_id, user_id, username, plan_key, amount = payment
    data = await get_platega_payment_status(transaction_id)
    status = data.get('status')

    if status == 'CONFIRMED':
        payment_details = data.get('paymentDetails') or {}
        paid_amount = payment_details.get('amount')
        currency = payment_details.get('currency')
        if not platega_amount_matches(paid_amount, amount) or currency != 'RUB':
            db.mark_platega_payment_status(transaction_id, 'AMOUNT_MISMATCH')
            await notify_archive(
                bot,
                f'⚠️ <b>Platega: сумма платежа не совпала</b>\n'
                f'ID: <code>{transaction_id}</code>\n'
                f'Пользователь: <code>{user_id}</code>\n'
                f'Ожидалось: {amount} RUB\n'
                f'Получено: {paid_amount} {currency}',
            )
            return

        link = await grant_access(bot, user_id, username, plan_key)
        db.mark_platega_payment_status(transaction_id, 'CONFIRMED')
        try:
            await bot.send_message(user_id, access_granted_text(plan_key, link), parse_mode='HTML')
        except TelegramForbiddenError:
            logging.exception('Could not confirm Platega payment to user %s (bot blocked?)', user_id)
        return

    if status in {'CANCELED', 'CHARGEBACKED'}:
        db.mark_platega_payment_status(transaction_id, status)
        try:
            await bot.send_message(
                user_id,
                'Оплата не прошла. Если деньги списались, напишите @mnlicks.',
            )
        except TelegramAPIError:
            logging.exception('Could not notify user %s about Platega status %s', user_id, status)


async def platega_payment_checker(bot):
    while True:
        for payment in db.get_pending_platega_payments():
            try:
                await process_platega_payment(bot, payment)
            except (ClientError, RuntimeError, TelegramAPIError):
                logging.exception('Failed to check Platega payment %s', payment[0])
        await asyncio.sleep(30)


async def grant_access(bot, user_id: int, username: str | None, plan_key: str) -> str:
    invite = await bot.create_chat_invite_link(
        chat_id=CHAT_ID,
        member_limit=1,
        expire_date=datetime.now() + timedelta(hours=24),
        name=f'user:{user_id}',
    )
    expires_at = plan_expiry(plan_key)
    db.upsert_subscription(user_id, username, plan_key, expires_at, invite.invite_link)
    plan = PLANS[plan_key]
    who = f'@{username}' if username else str(user_id)
    await notify_archive(
        bot,
        f'💰 <b>Новая подписка</b>\n'
        f'Пользователь: <code>{user_id}</code> ({who})\n'
        f'План: {plan["label"]} ({plan["amount"]}₽)\n'
        f'До: {expires_at:%d.%m.%Y}',
    )
    return invite.invite_link


MSK = timezone(timedelta(hours=3))
ARCHIVE_HOUR_MSK = 15


async def send_daily_archive(bot):
    now_msk = datetime.now(timezone.utc).astimezone(MSK)
    if now_msk.hour < ARCHIVE_HOUR_MSK:
        return
    today = now_msk.strftime('%Y-%m-%d')
    if db.get_setting('last_archive_date') == today:
        return
    try:
        if Path(db.DB_PATH).exists():
            await bot.send_document(
                ARCHIVE_CHAT_ID,
                FSInputFile(db.DB_PATH, filename=f'subscriptions_{today}.db'),
            )
        if LOG_FILE.exists():
            await bot.send_document(
                ARCHIVE_CHAT_ID,
                FSInputFile(str(LOG_FILE), filename=f'bot_{today}.log'),
            )
    except TelegramAPIError:
        logging.exception('Failed to send daily archive')
    db.set_setting('last_archive_date', today)


MEMBERSHIP_SWEEP_DATE = datetime(2026, 8, 31)


async def expiry_checker(bot):
    while True:
        for user_id, _ in db.get_expired(datetime.now()):
            if user_id in ADMIN_IDS:
                db.mark_status(user_id, 'expired')
                continue
            try:
                await bot.ban_chat_member(CHAT_ID, user_id)
                await bot.unban_chat_member(CHAT_ID, user_id, only_if_banned=True)
                await bot.send_message(
                    user_id,
                    '<tg-emoji emoji-id="5278578973595427038">🚫</tg-emoji> Ваша подписка на '
                    '<i>MnlicksGang | TRADE</i> <b>истекла, доступ закрыт.</b>\n\nПродлить:',
                    parse_mode='HTML',
                    reply_markup=plans_inline,
                )
            except TelegramAPIError:
                logging.exception('Failed to kick expired user %s', user_id)
            db.mark_status(user_id, 'expired')

        if datetime.now() >= MEMBERSHIP_SWEEP_DATE:
            for user_id, _ in db.get_grandfather_members():
                if user_id not in ADMIN_IDS and not db.has_active_subscription(user_id):
                    try:
                        await bot.ban_chat_member(CHAT_ID, user_id)
                        await bot.unban_chat_member(CHAT_ID, user_id, only_if_banned=True)
                        await bot.send_message(
                            user_id,
                            '<tg-emoji emoji-id="5278578973595427038">🚫</tg-emoji> У вас нет активной подписки на '
                            '<i>MnlicksGang | TRADE</i>, <b>доступ закрыт.</b>\n\nОформить:',
                            parse_mode='HTML',
                            reply_markup=plans_inline,
                        )
                    except TelegramAPIError:
                        logging.exception('Failed to kick unpaid member %s', user_id)
                db.remove_grandfather_member(user_id)

        await send_daily_archive(bot)
        await asyncio.sleep(3600)


@dp.message(CommandStart())
async def start_handler(message: Message):
    track_potential_member(message.from_user)
    await message.answer_photo(
        photo=get_hello_photo(),
        caption=get_hello_text(),
        parse_mode='HTML',
        reply_markup=hello_inline,
    )


@dp.message(F.chat.id == CHAT_ID, F.content_type.in_(SERVICE_CONTENT_TYPES))
async def delete_service_message(message: Message):
    try:
        await message.delete()
    except TelegramAPIError:
        pass


@dp.callback_query()
async def callback_handler(callback: CallbackQuery):
    await callback.answer()
    data = callback.data

    if data == 'join':
        await callback.message.answer(
            tariffs_screen_text(),
            reply_markup=plans_inline,
        )

    elif data == 'back':
        await callback.message.answer_photo(
            photo=get_hello_photo(),
            caption=get_hello_text(),
            parse_mode='HTML',
            reply_markup=hello_inline,
        )

    elif data in PLANS:
        plan = PLANS[data]
        plan_text = (
            f'📍Главное меню » Выбор тарифа » <b>Оплата:</b>\n\n'
            f'🍁 <b>{plan["label"]}</b>\n\n'
            f'⏳<b>Срок</b> —> {plan["term"]}\n\n'
            f'Цена —> {plan["amount"]}р\n\n'
            f'Выберите способ оплаты:'
        )
        plan_photo = ULTIMATE_PHOTO if data == 'season' else STANDART_PHOTO
        await callback.message.answer_photo(
            photo=FSInputFile(plan_photo),
            caption=plan_text,
            parse_mode='HTML',
            reply_markup=payment_method_inline(data),
        )

    elif data.startswith('crypto_'):
        plan_key = data[7:]
        plan = PLANS[plan_key]
        invoice = await cp.create_invoice(
            plan['amount'],
            currency_type='fiat',
            fiat='RUB',
            accepted_assets=['USDT'],
            description=f'MnlicksTrade — {plan["label"]}',
            expires_in=3600,
            payload=plan_key,
        )
        pay_inline = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Оплатить', url=invoice.mini_app_invoice_url)],
        ])
        await callback.message.answer(
            f'<tg-emoji emoji-id="5361914370068613491">👛</tg-emoji> USDT • TRC-20\n\n'
            f'Тариф: <b>{plan["label"]}</b>\n'
            f'Срок: <b>{plan["term"]}</b>\n'
            f'Сумма: <b>{plan["amount"]}₽</b> в USDT\n\n'
            f'<tg-emoji emoji-id="5258204546391351475">💰</tg-emoji> После успешной оплаты бот автоматически выдаст доступ.',
            parse_mode='HTML',
            reply_markup=pay_inline,
        )
        invoice.poll(message=callback.message)

    elif data.startswith('card_'):
        plan_key = data[5:]
        plan = PLANS[plan_key]
        try:
            transaction_id, payment_url = await create_platega_payment(callback.from_user, plan_key)
        except (ClientError, RuntimeError):
            logging.exception('Failed to create Platega payment for user %s', callback.from_user.id)
            await callback.message.answer(
                'Не удалось создать ссылку на оплату. Попробуйте ещё раз или напишите @mnlicks.',
            )
            return

        pay_inline = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Оплатить', url=payment_url)],
        ])
        await callback.message.answer(
            f'<tg-emoji emoji-id="5425008221330880308">💳</tg-emoji> Оплата картой\n\n'
            f'Тариф: <b>{plan["label"]}</b>\n'
            f'Срок: <b>{plan["term"]}</b>\n'
            f'Сумма: <b>{plan["amount"]}₽</b>\n\n'
            f'После успешной оплаты бот автоматически выдаст доступ.',
            parse_mode='HTML',
            reply_markup=pay_inline,
        )

    elif data == 'info':
        await callback.message.answer(
            info_text(),
            reply_markup=info_inline,
        )

    elif data == 'feedbacks':
        sent = await callback.message.answer_rich(
            rich_message=feedback_rich_message(),
            reply_markup=feedback_back_inline,
        )
        cache_feedback_photo_ids(sent)


@cp.invoice_paid()
async def payment_handler(invoice: Invoice, message: Message):
    try:
        link = await grant_access(message.bot, message.chat.id, message.chat.username, invoice.payload)
        await message.answer(access_granted_text(invoice.payload, link), parse_mode='HTML')
    except TelegramForbiddenError:
        logging.exception('Could not confirm payment to user %s (bot blocked?)', message.chat.id)


@dp.message(Command('getid'))
async def getid_handler(message: Message):
    await message.answer(f'chat_id: <code>{message.chat.id}</code>', parse_mode='HTML')


@dp.channel_post(Command('getid'))
async def getid_channel_handler(message: Message):
    await message.answer(f'chat_id: <code>{message.chat.id}</code>', parse_mode='HTML')


@dp.message(Command('grant'))
async def grant_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) != 3 or parts[2] not in PLANS:
        await message.answer(f'Использование: /grant <user_id> <{"|".join(PLANS)}>')
        return
    user_id = int(parts[1])
    plan_key = parts[2]
    link = await grant_access(message.bot, user_id, None, plan_key)
    await message.bot.send_message(user_id, access_granted_text(plan_key, link), parse_mode='HTML')
    await message.answer(f'Доступ выдан пользователю {user_id}.')


@dp.message(Command('addmembers'))
async def addmembers_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    if message.reply_to_message and message.reply_to_message.from_user:
        target = message.reply_to_message.from_user
        db.add_grandfather_members([(target.id, target.username)])
        await message.answer(f'Добавлен на проверку: {target.username and "@" + target.username or target.id}')
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            'Использование:\n'
            '• /addmembers <id или @username, через пробел или с новой строки>\n'
            '• либо ответьте (reply) командой /addmembers на сообщение человека в чате — самый надёжный способ,\n'
            '  так как бот не всегда может найти пользователя по @username, если тот раньше не писал боту напрямую.\n\n'
            f'Эти пользователи будут проверены на активную подписку '
            f'{MEMBERSHIP_SWEEP_DATE.strftime("%d.%m.%Y")} — у кого её нет, будут исключены из чата.'
        )
        return
    tokens = parts[1].split()
    added: list[str] = []
    failed: list[str] = []
    for token in tokens:
        handle = token.strip().lstrip('@')
        if handle.isdigit():
            db.add_grandfather_members([(int(handle), None)])
            added.append(handle)
            continue
        try:
            chat = await message.bot.get_chat(f'@{handle}')
            db.add_grandfather_members([(chat.id, handle)])
            added.append(handle)
        except TelegramAPIError:
            failed.append(handle)
    reply = f'Добавлено в список на проверку: {len(added)}'
    if failed:
        reply += (
            f'\nНе удалось найти: {", ".join(failed)}\n'
            'Для них: ответьте (reply) на сообщение этого человека в чате командой /addmembers.'
        )
    await message.answer(reply)


@dp.message(Command('setwelcome'))
async def setwelcome_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            'Использование: /setwelcome <текст>\n\n'
            'Поддерживается HTML-разметка (как в текущем приветствии).'
        )
        return
    db.set_setting('hello_text', parts[1])
    await message.answer('Приветственный текст обновлён. Вот как он теперь выглядит:')
    await message.answer_photo(
        photo=get_hello_photo(),
        caption=get_hello_text(),
        parse_mode='HTML',
        reply_markup=hello_inline,
    )


@dp.message(Command('settariffs'))
async def settariffs_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(
            'Использование: /settariffs <текст>\n\n'
            'Текст показывается на экране выбора тарифа (кнопка «Вступить в MnlicksTrade»).\n'
            'Поддерживается HTML-разметка.'
        )
        return
    db.set_setting('tariffs_text', parts[1])
    await message.answer('Текст экрана тарифов обновлён. Вот как он теперь выглядит:')
    await message.answer(tariffs_screen_text(), parse_mode='HTML', reply_markup=plans_inline)


@dp.message(Command('sethellophoto'), F.photo)
async def sethellophoto_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    db.set_setting('hello_photo_id', message.photo[-1].file_id)
    await message.answer('Фото главного меню обновлено. Вот как оно теперь выглядит:')
    await message.answer_photo(
        photo=get_hello_photo(),
        caption=get_hello_text(),
        parse_mode='HTML',
        reply_markup=hello_inline,
    )


@dp.message(Command('sethellophoto'))
async def sethellophoto_no_photo_handler(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer('Использование: отправьте фото с подписью /sethellophoto')


@dp.message(F.chat.id == CHAT_ID)
async def track_chat_activity(message: Message):
    track_potential_member(message.from_user)


@dp.message(F.chat.type == ChatType.PRIVATE)
async def unknown_private_message(message: Message):
    await message.answer('Введите /start, чтобы открыть меню.')


async def main():
    session = AiohttpSession(proxy=os.environ.get("PROXY_URL"))
    bot = Bot(token=os.environ["BOT_TOKEN"], session=session)
    await bot.set_my_commands([BotCommand(command='start', description='🏠 Открыть меню!')])
    await asyncio.gather(
        dp.start_polling(bot),
        cp.start_polling(),
        platega_payment_checker(bot),
        expiry_checker(bot),
    )


if __name__ == "__main__":
    print('bot activated')
    asyncio.run(main())
