import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import db
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ContentType
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery,
    InputMediaPhoto, InputRichMessage, InputRichBlockSlideshow, InputRichBlockPhoto, RichBlockCaption,
    RichTextCustomEmoji,
)
from aiosend import CryptoPay
from aiosend.types import Invoice
from dotenv import load_dotenv

load_dotenv()

dp = Dispatcher()
cp = CryptoPay(os.environ["CRYPTO_PAY_TOKEN"])
ADMIN_IDS = {int(x) for x in os.environ["ADMIN_IDS"].split(",")}
CHAT_ID = int(os.environ["CHAT_ID"]) if os.environ.get("CHAT_ID") else None
SEASON_END_DATE = datetime.fromisoformat(os.environ["SEASON_END_DATE"])
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


DEFAULT_TARIFFS_TEXT = '📍Главное меню » Выбор тарифа\n\n🗂 Выберите тариф:'


def get_tariffs_text() -> str:
    return db.get_setting('tariffs_text', DEFAULT_TARIFFS_TEXT)

hello_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Вступить в MnlicksTrade', callback_data='join')],
    [InlineKeyboardButton(text='Отзывы', callback_data='feedbacks')],
    [InlineKeyboardButton(text='Задать вопрос', url="https://t.me/mnlicks")],
])

plans_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='Standart Edition', callback_data='month')],
    [InlineKeyboardButton(text='Ultimate Edition', callback_data='season')],
    [InlineKeyboardButton(text='« Назад', callback_data='back')],
])

PLANS = {
    'month': {'amount': 1000, 'label': 'Standart Edition', 'desc': 'на 1 месяц', 'short': 'Standart Edition'},
    'season': {'amount': 6000, 'label': 'Ultimate Edition', 'desc': 'до конца FC 27', 'short': 'Ultimate Edition'},
}


def access_granted_text(plan_key: str, link: str) -> str:
    short = PLANS[plan_key]['short']
    return (
        f'<tg-emoji emoji-id="5278411813468269386">✅</tg-emoji> <b>Оплата</b> <i><b>подтверждена!\n'
        f'» </b>MnlicksTrade • {short} </i>\n\n'
        f'Твоя персональная ссылка:\n'
        f'<i>»</i> {link}'
    )


def payment_method_inline(plan_key: str) -> InlineKeyboardMarkup:
    plan = PLANS[plan_key]
    card_text = quote(f'Здравствуйте! Хочу оплатить тариф «{plan["label"]}» ({plan["amount"]}₽) картой РФ.')
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text='Карта • РУ', url=f'https://t.me/mnlicks?text={card_text}', icon_custom_emoji_id='5425008221330880308'),
            InlineKeyboardButton(text='USDT • TRC-20', callback_data=f'crypto_{plan_key}', icon_custom_emoji_id='5361914370068613491'),
        ],
        [InlineKeyboardButton(text='« Назад', callback_data='join')],
    ])


feedback_back_inline = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='« Назад', callback_data='back')],
])


def feedback_rich_message() -> InputRichMessage:
    slides = [
        InputRichBlockPhoto(photo=InputMediaPhoto(media=FSInputFile(path)))
        for path in FEEDBACK_PHOTOS
    ]
    caption = RichBlockCaption(text=[
        RichTextCustomEmoji(custom_emoji_id='5424972470023104089', alternative_text='🔥'),
        ' Отзывы участников',
    ])
    return InputRichMessage(blocks=[InputRichBlockSlideshow(blocks=slides, caption=caption)])


def plan_expiry(plan_key: str) -> datetime:
    if plan_key == 'season':
        return SEASON_END_DATE
    return datetime.now() + timedelta(days=30)


async def grant_access(bot, user_id: int, username: str | None, plan_key: str) -> str:
    invite = await bot.create_chat_invite_link(
        chat_id=CHAT_ID,
        member_limit=1,
        expire_date=datetime.now() + timedelta(hours=24),
        name=f'user:{user_id}',
    )
    expires_at = plan_expiry(plan_key)
    db.upsert_subscription(user_id, username, plan_key, expires_at, invite.invite_link)
    return invite.invite_link


async def expiry_checker(bot):
    while True:
        for user_id, _ in db.get_expired(datetime.now()):
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
                pass
            db.mark_status(user_id, 'expired')
        await asyncio.sleep(3600)


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer_photo(
        photo=FSInputFile(HELLO_PHOTO),
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
            get_tariffs_text(),
            reply_markup=plans_inline,
        )

    elif data == 'back':
        await callback.message.answer_photo(
            photo=FSInputFile(HELLO_PHOTO),
            caption=get_hello_text(),
            parse_mode='HTML',
            reply_markup=hello_inline,
        )

    elif data in PLANS:
        plan = PLANS[data]
        plan_text = (
            f'📍Главное меню » Выбор тарифа » <b>{plan["label"]}</b>\n\n'
            f'<blockquote>⚽️ Полный доступ в <b>MnlicksGang | TRADE</b> {plan["desc"]} — <b>{plan["amount"]}₽</b></blockquote>\n\n'
            f'<tg-emoji emoji-id="5258204546391351475">💰</tg-emoji> Выберите способ оплаты:'
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
            f'Тариф: <b>{plan["desc"]}</b>\n'
            f'Сумма: <b>{plan["amount"]}₽</b> в USDT\n\n'
            f'<tg-emoji emoji-id="5258204546391351475">💰</tg-emoji> После успешной оплаты бот автоматически выдаст доступ.',
            parse_mode='HTML',
            reply_markup=pay_inline,
        )
        invoice.poll(message=callback.message)

    elif data == 'feedbacks':
        await callback.message.answer_rich(
            rich_message=feedback_rich_message(),
            reply_markup=feedback_back_inline,
        )


@cp.invoice_paid()
async def payment_handler(invoice: Invoice, message: Message):
    try:
        link = await grant_access(message.bot, message.chat.id, message.chat.username, invoice.payload)
        await message.answer(access_granted_text(invoice.payload, link), parse_mode='HTML')
    except TelegramForbiddenError:
        pass


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
        photo=FSInputFile(HELLO_PHOTO),
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
    await message.answer(get_tariffs_text(), parse_mode='HTML', reply_markup=plans_inline)


async def main():
    session = AiohttpSession(proxy=os.environ.get("PROXY_URL"))
    bot = Bot(token=os.environ["BOT_TOKEN"], session=session)
    await asyncio.gather(
        dp.start_polling(bot),
        cp.start_polling(),
        expiry_checker(bot),
    )


if __name__ == "__main__":
    print('bot activated')
    asyncio.run(main())
