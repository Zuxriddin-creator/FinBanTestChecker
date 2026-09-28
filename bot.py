import asyncio
import json
import logging
import os
import re
import time

from PIL import Image, ImageOps, ImageEnhance

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from google import genai
from google.genai import types


# ============================================================
# CONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = "8418170279:AAEKr8LhRESc_2jOZIVGgO4VBjGyCrAGTt8"

GEMINI_API_KEY = "AQ.Ab8RN6J0vgvilx9KJzPwRdQrvqAYuGmWtqtGHEWBcu37UegpKQ"

# Current Gemini model
MODEL_NAME = "gemini-3.8-flash"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# ============================================================
# ANSWER NORMALIZATION
# ============================================================

CYRILLIC_TO_LATIN = {
    "А": "A",
    "Б": "B",
    "В": "C",
    "Г": "D",
    "Д": "E",

    "а": "A",
    "б": "B",
    "в": "C",
    "г": "D",
    "д": "E",

    "A": "A",
    "B": "B",
    "C": "C",
    "D": "D",
    "E": "E",

    "a": "A",
    "b": "B",
    "c": "C",
    "d": "D",
    "e": "E",
}


VALID_ANSWERS = {
    "A",
    "B",
    "C",
    "D",
    "E",
}


def normalize_answer(answer: str) -> str:

    if not answer:
        return ""

    answer = str(answer).strip()

    return CYRILLIC_TO_LATIN.get(
        answer,
        answer.upper()
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    await update.message.reply_text(
        "Ассалому алайкум!\n\n"
        "🤖 Fin-Ban Test Checker\n\n"
        "1️⃣ Аввал мастер-калитни юборинг:\n"
        "/key 1-A, 2-C, 3-B...\n\n"
        "2️⃣ Кейин номзоднинг тест варағини расм қилиб юборинг.\n\n"
        "Калитни ўчириш:\n"
        "/resetkey"
    )


# ============================================================
# GEMINI PROMPT
# ============================================================

def build_prompt(is_key: bool) -> str:

    if is_key:

        return """
You are an extremely accurate OCR system for a multiple-choice
test answer key.

This image is an OFFICIAL MASTER ANSWER KEY.

Your ONLY job is to READ the answer key.

DO NOT solve any questions.

DO NOT infer answers.

DO NOT guess.

Read every visible question number and its marked correct answer.

The answer choices can be Latin:

A B C D E

or Cyrillic:

А Б В Г Д

Convert Cyrillic to Latin:

А = A
Б = B
В = C
Г = D
Д = E

For EVERY visible question return:

question number
answer

If the answer is genuinely impossible to read, return UNCLEAR.

Return all visible questions.

Return ONLY JSON matching the requested schema.
"""

    return """
You are an extremely accurate OCR system for a multiple-choice
candidate answer sheet.

Your ONLY job is to READ what the candidate physically marked.

DO NOT solve the questions.

DO NOT determine which answer is correct.

DO NOT use your own knowledge.

DO NOT guess.

==================================================
CANDIDATE NAME
==================================================

Look for:

Ф.И.Ш.
ФИШ
F.I.Sh.
FISH
Name
Ном

Read the candidate's name if clearly visible.

If blank or unreadable:

Кўрсатилмаган

==================================================
ANSWER GRID
==================================================

Read the answer grid from question 1 onward.

Possible choices:

A
B
C
D
E

The paper may use Cyrillic:

А Б В Г Д

Convert:

А = A
Б = B
В = C
Г = D
Д = E

==================================================
MARK DETECTION
==================================================

A selected answer may be indicated by:

- filled circle
- shaded bubble
- checkmark
- tick
- cross
- circled option
- clearly marked option

Only report an answer when there is visible evidence.

If there is NO selected answer:

BLANK

If there is a mark but it is genuinely impossible to determine
which option was selected:

UNCLEAR

DO NOT GUESS.

==================================================
IMPORTANT
==================================================

Return EVERY question visible on the sheet.

Do not skip blank questions.

Do not invent questions.

Do not solve questions.

Return ONLY JSON matching the requested schema.
"""


# ============================================================
# GEMINI REQUEST WITH RETRIES
# ============================================================

def call_gemini_with_retry(
    prompt: str,
    image
):

    max_attempts = 5

    for attempt in range(1, max_attempts + 1):

        try:

            print(
                f"\nGemini attempt {attempt}/{max_attempts}"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,

                contents=[
                    prompt,
                    image
                ],

                config=types.GenerateContentConfig(

                    response_mime_type="application/json",

                    response_schema={
                        "type": "OBJECT",

                        "properties": {

                            "name": {
                                "type": "STRING"
                            },

                            "answers": {

                                "type": "ARRAY",

                                "items": {

                                    "type": "OBJECT",

                                    "properties": {

                                        "question": {
                                            "type": "INTEGER"
                                        },

                                        "answer": {

                                            "type": "STRING",

                                            "enum": [
                                                "A",
                                                "B",
                                                "C",
                                                "D",
                                                "E",
                                                "BLANK",
                                                "UNCLEAR"
                                            ]
                                        }
                                    },

                                    "required": [
                                        "question",
                                        "answer"
                                    ]
                                }
                            }
                        },

                        "required": [
                            "name",
                            "answers"
                        ]
                    }
                )
            )

            return response

        except Exception as e:

            error_text = str(e)

            print("\nGEMINI ERROR:")
            print(error_text)

            # Retry temporary server errors
            if (
                "503" in error_text
                or "UNAVAILABLE" in error_text
                or "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
                or "500" in error_text
                or "502" in error_text
            ):

                if attempt < max_attempts:

                    delay = 2 ** attempt

                    print(
                        f"\nGemini is temporarily busy."
                    )

                    print(
                        f"Retrying in {delay} seconds..."
                    )

                    time.sleep(delay)

                    continue

            # Non-temporary error
            raise


# ============================================================
# GEMINI IMAGE ANALYSIS
# ============================================================

def analyze_image(
    image_path: str,
    is_key: bool = False
) -> dict:

    prompt = build_prompt(is_key)

    try:

        # ----------------------------------------------------
        # OPEN IMAGE
        # ----------------------------------------------------

        with Image.open(image_path) as source_image:

            image = ImageOps.exif_transpose(
                source_image
            ).convert("RGB")

            # Slight contrast improvement
            image = ImageEnhance.Contrast(
                image
            ).enhance(1.3)

            # Slight sharpness improvement
            image = ImageEnhance.Sharpness(
                image
            ).enhance(1.2)

            # ------------------------------------------------
            # GEMINI
            # ------------------------------------------------

            response = call_gemini_with_retry(
                prompt,
                image
            )

        # ----------------------------------------------------
        # RAW RESPONSE
        # ----------------------------------------------------

        print("\n========================================")
        print("GEMINI RAW RESPONSE")
        print("========================================")

        print(response.text)

        print("========================================\n")

        if not response.text:

            print(
                "ERROR: Gemini returned empty response."
            )

            return {
                "name": "Кўрсатилмаган",
                "answers": []
            }

        # ----------------------------------------------------
        # PARSE JSON
        # ----------------------------------------------------

        try:

            data = json.loads(
                response.text
            )

        except json.JSONDecodeError as e:

            print(
                "JSON ERROR:",
                repr(e)
            )

            return {
                "name": "Кўрсатилмаган",
                "answers": []
            }

        # ----------------------------------------------------
        # DEBUG
        # ----------------------------------------------------

        print("\n========================================")
        print("PARSED GEMINI DATA")
        print("========================================")

        print(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            )
        )

        print("========================================\n")

        return data

    except Exception as e:

        logger.exception(
            "Gemini image analysis failed"
        )

        print("\n========================================")
        print("GEMINI ERROR")
        print("========================================")

        print(
            repr(e)
        )

        print("========================================\n")

        return {
            "name": "Кўрсатилмаган",
            "answers": []
        }


# ============================================================
# TEXT ANSWER KEY PARSER
# ============================================================

def parse_key_text(
    text: str
) -> dict[int, str]:

    """
    Accepts:

    1-A
    2-C
    3-B

    or:

    1: A
    2: C
    3: B

    or:

    1-A, 2-C, 3-Б
    """

    pattern = (
        r"(\d+)"
        r"\s*"
        r"(?:[:.\-),]|\s)"
        r"\s*"
        r"([A-Ea-eА-Еа-е])"
        r"\b"
    )

    matches = re.findall(
        pattern,
        text
    )

    key = {}

    for question, answer in matches:

        normalized = normalize_answer(
            answer
        )

        if normalized in VALID_ANSWERS:

            key[int(question)] = normalized

    return key


# ============================================================
# /KEY COMMAND
# ============================================================

async def handle_key_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    text = (
        update.message.text
        or ""
    )

    parts = text.split(
        maxsplit=1
    )

    if len(parts) < 2:

        await update.message.reply_text(
            "❌ Калит киритилмаган.\n\n"
            "Масалан:\n"
            "/key 1-A, 2-C, 3-B, 4-D"
        )

        return

    parsed_key = parse_key_text(
        parts[1]
    )

    if not parsed_key:

        await update.message.reply_text(
            "❌ Жавоблар аниқланмади.\n\n"
            "Масалан:\n"
            "/key 1-A, 2-C, 3-B, 4-D"
        )

        return

    context.chat_data["active_key"] = parsed_key

    print("\nMASTER KEY:")
    print(parsed_key)

    await update.message.reply_text(
        "✅ Тўғри жавоблар калити сақланди.\n\n"
        f"📋 Саволлар сони: {len(parsed_key)} та\n\n"
        "Энди номзоднинг тест варағини юборинг."
    )


# ============================================================
# RESET KEY
# ============================================================

async def reset_key_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    context.chat_data.pop(
        "active_key",
        None
    )

    await update.message.reply_text(
        "🗑 Жавоблар калити ўчирилди.\n\n"
        "Янги калит юборинг."
    )


# ============================================================
# CONVERT GEMINI ANSWERS
# ============================================================

def convert_gemini_answers(
    raw_answers
) -> dict[int, str]:

    answers = {}

    if not isinstance(
        raw_answers,
        list
    ):

        return answers

    for item in raw_answers:

        if not isinstance(
            item,
            dict
        ):

            continue

        try:

            question = int(
                item.get(
                    "question"
                )
            )

            answer = normalize_answer(
                str(
                    item.get(
                        "answer",
                        ""
                    )
                )
            )

            # Only actual answers count.
            # BLANK and UNCLEAR remain absent
            # from scoring.

            if answer in VALID_ANSWERS:

                answers[question] = answer

        except (
            ValueError,
            TypeError
        ):

            continue

    return answers


# ============================================================
# SEND RESULT
# ============================================================

async def send_candidate_result(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    result_data: dict
) -> None:

    active_key = context.chat_data.get(
        "active_key"
    )

    if not active_key:

        await update.message.reply_text(
            "❌ Жавоблар калити мавжуд эмас.\n\n"
            "Аввал /key орқали калит киритинг."
        )

        return

    # --------------------------------------------------------
    # NAME
    # --------------------------------------------------------

    candidate_name = str(
        result_data.get(
            "name",
            "Кўрсатилмаган"
        )
    ).strip()

    if not candidate_name:

        candidate_name = "Кўрсатилмаган"

    # --------------------------------------------------------
    # ANSWERS
    # --------------------------------------------------------

    candidate_answers = convert_gemini_answers(
        result_data.get(
            "answers",
            []
        )
    )

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    print("\n========================================")
    print("CANDIDATE ANSWERS")
    print("========================================")

    print(candidate_answers)

    print("========================================\n")

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    correct_count = 0

    wrong_details = []

    for question, correct_answer in active_key.items():

        candidate_answer = candidate_answers.get(
            question
        )

        if candidate_answer == correct_answer:

            correct_count += 1

        else:

            wrong_details.append(
                (
                    question,
                    candidate_answer or "—",
                    correct_answer
                )
            )

    total_questions = len(
        active_key
    )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    response_text = (
        f"👤 Ф.И.Ш: {candidate_name}\n"
        f"📊 Натижа: {correct_count}/{total_questions}\n"
    )

    if wrong_details:

        response_text += (
            "\n❌ Нотоғри жавоблар:\n"
        )

        for (
            question,
            candidate_answer,
            correct_answer
        ) in wrong_details:

            response_text += (
                f"• №{question}: "
                f"{candidate_answer} "
                f"(тўғриси: {correct_answer})\n"
            )

    else:

        response_text += (
            "\n🎉 Барча жавоблар тўғри!"
        )

    await send_report(
        update,
        response_text
    )


# ============================================================
# SEND REPORT
# ============================================================

async def send_report(
    update: Update,
    report: str
) -> None:

    if not report.strip():

        await update.message.reply_text(
            "❌ Натижа олиб бўлмади."
        )

        return

    max_length = 4096

    for i in range(
        0,
        len(report),
        max_length
    ):

        await update.message.reply_text(
            report[
                i:i + max_length
            ]
        )


# ============================================================
# PROCESS IMAGE
# ============================================================

async def process_downloaded_image(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    temp_path: str,
    is_key: bool = False
) -> None:

    status_message = await update.message.reply_text(
        "🔎 Расм таҳлил қилинмоқда...\n\n"
        "Илтимос, бироз кутинг."
    )

    try:

        loop = asyncio.get_running_loop()

        result_data = await loop.run_in_executor(
            None,
            analyze_image,
            temp_path,
            is_key
        )

        # ----------------------------------------------------
        # DELETE STATUS
        # ----------------------------------------------------

        try:

            await status_message.delete()

        except Exception:

            pass

        # ----------------------------------------------------
        # MASTER KEY IMAGE
        # ----------------------------------------------------

        if is_key:

            raw_answers = result_data.get(
                "answers",
                []
            )

            active_key = convert_gemini_answers(
                raw_answers
            )

            if not active_key:

                await update.message.reply_text(
                    "❌ Калит расмидан жавоблар аниқланмади.\n\n"
                    "Расмни аниқроқ қилиб қайта юборинг."
                )

                return

            context.chat_data["active_key"] = (
                active_key
            )

            print("\nMASTER KEY FROM IMAGE:")
            print(active_key)

            await update.message.reply_text(
                "✅ Тўғри жавоблар калити расмдан сақланди.\n\n"
                f"📋 Саволлар сони: {len(active_key)} та\n\n"
                "Энди номзоднинг тест варағини юборинг."
            )

            return

        # ----------------------------------------------------
        # CANDIDATE IMAGE
        # ----------------------------------------------------

        await send_candidate_result(
            update,
            context,
            result_data
        )

    except Exception as e:

        logger.exception(
            "Image processing error"
        )

        await update.message.reply_text(
            "❌ Расмни таҳлил қилишда хатолик юз берди.\n\n"
            f"Хатолик: {str(e)}"
        )


# ============================================================
# HANDLE TELEGRAM PHOTO
# ============================================================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    try:

        caption = (
            update.message.caption
            or ""
        ).strip().lower()

        # If caption starts with /key,
        # this image is the master answer key.

        is_key = caption.startswith(
            "/key"
        )

        # Candidate requires an existing key.

        if (
            not is_key
            and not context.chat_data.get(
                "active_key"
            )
        ):

            await update.message.reply_text(
                "❌ Аввал тўғри жавоблар калитини юборинг.\n\n"
                "Масалан:\n"
                "/key 1-A, 2-C, 3-B..."
            )

            return

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        photo = update.message.photo[-1]

        photo_file = await context.bot.get_file(
            photo.file_id
        )

        temp_path = (
            f"temp_{photo.file_unique_id}.jpg"
        )

        await photo_file.download_to_drive(
            temp_path
        )

        try:

            await process_downloaded_image(
                update,
                context,
                temp_path,
                is_key
            )

        finally:

            if os.path.exists(
                temp_path
            ):

                os.remove(
                    temp_path
                )

    except Exception as e:

        logger.exception(
            "Photo processing failed"
        )

        await update.message.reply_text(
            "❌ Расмни қайта ишлашда хатолик юз берди.\n\n"
            f"Хатолик: {str(e)}"
        )


# ============================================================
# HANDLE IMAGE DOCUMENT
# ============================================================

async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    try:

        document = update.message.document

        file_name = (
            document.file_name
            or ""
        ).lower()

        allowed_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".heic"
        )

        if not file_name.endswith(
            allowed_extensions
        ):

            await update.message.reply_text(
                "❌ Илтимос, JPG, JPEG, PNG, WEBP ёки HEIC расм юборинг."
            )

            return

        caption = (
            update.message.caption
            or ""
        ).strip().lower()

        is_key = caption.startswith(
            "/key"
        )

        if (
            not is_key
            and not context.chat_data.get(
                "active_key"
            )
        ):

            await update.message.reply_text(
                "❌ Аввал тўғри жавоблар калитини юборинг."
            )

            return

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        document_file = await context.bot.get_file(
            document.file_id
        )

        safe_name = os.path.basename(
            file_name
        )

        temp_path = (
            f"temp_{document.file_unique_id}_{safe_name}"
        )

        await document_file.download_to_drive(
            temp_path
        )

        try:

            await process_downloaded_image(
                update,
                context,
                temp_path,
                is_key
            )

        finally:

            if os.path.exists(
                temp_path
            ):

                os.remove(
                    temp_path
                )

    except Exception as e:

        logger.exception(
            "Document processing failed"
        )

        await update.message.reply_text(
            "❌ Ҳужжатни қайта ишлашда хатолик юз берди.\n\n"
            f"Хатолик: {str(e)}"
        )


# ============================================================
# HANDLE TEXT
# ============================================================

async def handle_text_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:

    text = (
        update.message.text
        or ""
    ).strip()

    if not text:
        return

    active_key = context.chat_data.get(
        "active_key"
    )

    # --------------------------------------------------------
    # NO KEY
    # --------------------------------------------------------

    if not active_key:

        parsed_key = parse_key_text(
            text
        )

        if parsed_key:

            context.chat_data["active_key"] = (
                parsed_key
            )

            await update.message.reply_text(
                "✅ Тўғри жавоблар калити сақланди.\n\n"
                f"📋 Саволлар сони: {len(parsed_key)} та\n\n"
                "Энди номзоднинг тест варағини юборинг."
            )

        else:

            await update.message.reply_text(
                "❌ Аввал калит киритинг.\n\n"
                "Масалан:\n"
                "/key 1-A, 2-C, 3-B..."
            )

        return

    # --------------------------------------------------------
    # TEXT KEY
    # --------------------------------------------------------

    parsed_answers = parse_key_text(
        text
    )

    if len(parsed_answers) >= 15:

        context.chat_data["active_key"] = (
            parsed_answers
        )

        await update.message.reply_text(
            "✅ Янги тўғри жавоблар калити сақланди.\n\n"
            f"📋 Саволлар сони: {len(parsed_answers)} та"
        )

        return

    # --------------------------------------------------------
    # CANDIDATE TEXT
    # --------------------------------------------------------

    name_match = re.search(
        r"(?:Ф\.?И\.?Ш|ФИШ|F\.?I\.?S\.?H|Name|Ном)"
        r"\s*[:\-]?\s*(.+)",
        text,
        re.IGNORECASE
    )

    candidate_name = (
        name_match.group(1).strip()
        if name_match
        else "Кўрсатилмаган"
    )

    candidate_answers = parsed_answers

    if not candidate_answers:

        await update.message.reply_text(
            "❌ Жавоблар аниқланмади.\n\n"
            "Масалан:\n"
            "ФИШ: Иванов Иван\n"
            "1-A\n"
            "2-C\n"
            "3-B"
        )

        return

    result_data = {

        "name": candidate_name,

        "answers": [

            {
                "question": question,
                "answer": answer
            }

            for question, answer
            in candidate_answers.items()
        ]
    }

    await send_candidate_result(
        update,
        context,
        result_data
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if (
        TELEGRAM_BOT_TOKEN
        == "PUT_YOUR_NEW_TELEGRAM_BOT_TOKEN_HERE"
    ):

        print(
            "\nERROR: Put your new Telegram bot token "
            "into TELEGRAM_BOT_TOKEN.\n"
        )

        return

    if (
        GEMINI_API_KEY
        == "PUT_YOUR_NEW_GEMINI_API_KEY_HERE"
    ):

        print(
            "\nERROR: Put your new Gemini API key "
            "into GEMINI_API_KEY.\n"
        )

        return

    print(
        "=========================================="
    )

    print(
        "FIN-BAN TEST CHECKER"
    )

    print(
        "Gemini model:",
        MODEL_NAME
    )

    print(
        "Bot is starting..."
    )

    print(
        "=========================================="
    )

    # --------------------------------------------------------
    # TELEGRAM APPLICATION
    # --------------------------------------------------------

    app = (
        Application
        .builder()
        .token(
            TELEGRAM_BOT_TOKEN
        )
        .build()
    )

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "key",
            handle_key_command
        )
    )

    app.add_handler(
        CommandHandler(
            "setkey",
            handle_key_command
        )
    )

    app.add_handler(
        CommandHandler(
            "resetkey",
            reset_key_command
        )
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text_message
        )
    )

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    # --------------------------------------------------------
    # IMAGE DOCUMENT
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.Document.IMAGE,
            handle_document
        )
    )

    print(
        "Бот ишга тушди..."
    )

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    app.run_polling()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()