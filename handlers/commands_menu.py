from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


# =========================================================
# 📋 قائمة أوامر البوت
# =========================================================


# =========================================================
# 🔘 أزرار القائمة الرئيسية
# =========================================================

def main_menu_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "👤 المستخدمين والرتب",
                callback_data="cmdmenu:users"
            ),
            InlineKeyboardButton(
                "🛡️ الحماية",
                callback_data="cmdmenu:protection"
            ),
        ],

        [
            InlineKeyboardButton(
                "💬 الردود",
                callback_data="cmdmenu:replies"
            ),
            InlineKeyboardButton(
                "⭐ الردود المميزة",
                callback_data="cmdmenu:special_replies"
            ),
        ],

        [
            InlineKeyboardButton(
                "👮 الإدارة",
                callback_data="cmdmenu:admin"
            ),
            InlineKeyboardButton(
                "🧩 الأوامر المضافة",
                callback_data="cmdmenu:custom"
            ),
        ],

        [
            InlineKeyboardButton(
                "💰 النقاط",
                callback_data="cmdmenu:points"
            ),
            InlineKeyboardButton(
                "🤫 الهمسات",
                callback_data="cmdmenu:whispers"
            ),
        ],

        [
            InlineKeyboardButton(
                "🎮 الألعاب",
                callback_data="cmdmenu:games"
            ),
            InlineKeyboardButton(
                "⚙️ إدارة الألعاب",
                callback_data="cmdmenu:games_manager"
            ),
        ],

        [
            InlineKeyboardButton(
                "🎨 ألوان الأزرار",
                callback_data="cmdmenu:colors"
            ),
            InlineKeyboardButton(
                "👨‍💻 المطور",
                callback_data="cmdmenu:developer"
            ),
        ],

    ])


# =========================================================
# 👤 المستخدمين والرتب
# =========================================================

def users_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🪪 أوامر المستخدمين",
                callback_data="cmdmenu:users_info"
            ),
            InlineKeyboardButton(
                "⬆️ رفع الرتب",
                callback_data="cmdmenu:promote"
            ),
        ],

        [
            InlineKeyboardButton(
                "⬇️ تنزيل الرتب",
                callback_data="cmdmenu:demote"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع",
                callback_data="cmdmenu:home"
            )
        ]

    ])


# =========================================================
# 🛡️ الحماية
# =========================================================

def protection_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🚫 الحظر والكتم",
                callback_data="cmdmenu:moderation"
            ),
            InlineKeyboardButton(
                "🔐 منع وسماح",
                callback_data="cmdmenu:permissions"
            ),
        ],

        [
            InlineKeyboardButton(
                "🔒 قفل وفتح الأوامر",
                callback_data="cmdmenu:locks"
            ),
            InlineKeyboardButton(
                "🗑️ المسح",
                callback_data="cmdmenu:delete"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع",
                callback_data="cmdmenu:home"
            )
        ]

    ])


# =========================================================
# 🎮 الألعاب
# =========================================================

def games_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🫣 غميضة",
                callback_data="cmdmenu:hide"
            ),
            InlineKeyboardButton(
                "⚽ بلنتيات",
                callback_data="cmdmenu:penalties"
            ),
        ],

        [
            InlineKeyboardButton(
                "🤥 الكذاب",
                callback_data="cmdmenu:liar"
            ),
        ],

        [
            InlineKeyboardButton(
                "🏃 سباق الكلمات",
                callback_data="cmdmenu:word_race"
            ),
            InlineKeyboardButton(
                "🖼️ توقع الصورة",
                callback_data="cmdmenu:image_quiz"
            ),
        ],

        [
            InlineKeyboardButton(
                "⚡ أسرع كلمة",
                callback_data="cmdmenu:speed_words"
            ),
            InlineKeyboardButton(
                "🎌 الأنمي",
                callback_data="cmdmenu:anime"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع",
                callback_data="cmdmenu:home"
            )
        ]

    ])


# =========================================================
# ⚽ بلنتيات
# =========================================================

def penalties_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📖 الأوامر",
                callback_data="cmdmenu:penalties_commands"
            ),
            InlineKeyboardButton(
                "ℹ️ الشرح",
                callback_data="cmdmenu:penalties_help"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# 🫣 غميضة
# =========================================================

def hide_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📖 الأوامر",
                callback_data="cmdmenu:hide_commands"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# 🤥 الكذاب
# =========================================================

def liar_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📖 الأوامر",
                callback_data="cmdmenu:liar_commands"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# 🏃 سباق الكلمات
# =========================================================

def word_race_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📖 الأوامر",
                callback_data="cmdmenu:word_race_commands"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# 🖼️ توقع الصورة
# =========================================================

def image_quiz_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📖 الأوامر",
                callback_data="cmdmenu:image_quiz_commands"
            ),
        ],

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# ⚡ أسرع كلمة
# =========================================================

def speed_words_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# 🎌 الأنمي
# =========================================================

def anime_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "↩️ رجوع للألعاب",
                callback_data="cmdmenu:games"
            )
        ]

    ])


# =========================================================
# 📋 إرسال القائمة الرئيسية
# =========================================================

async def commands_menu_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    await update.message.reply_text(
        "📋 <b>أوامر بوت نواف</b>\n\n"
        "اختر القسم الذي تريد معرفة أوامره:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )


# =========================================================
# 🔄 تعديل الصفحة
# =========================================================

async def edit_page(
    query,
    text,
    keyboard
):

    await query.edit_message_text(

        text,

        parse_mode="HTML",

        reply_markup=keyboard
    )


# =========================================================
# 🔘 معالجة الأزرار
# =========================================================

async def commands_menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data

    # =====================================================
    # الرئيسية
    # =====================================================

    if data == "cmdmenu:home":

        await edit_page(
            query,

            "📋 <b>أوامر بوت نواف</b>\n\n"
            "اختر القسم الذي تريد معرفة أوامره:",

            main_menu_keyboard()
        )

        return


    # =====================================================
    # المستخدمين والرتب
    # =====================================================

    if data == "cmdmenu:users":

        await edit_page(

            query,

            "👤 <b>المستخدمين والرتب</b>\n\n"
            "اختر القسم:",

            users_keyboard()
        )

        return


    # =====================================================
    # معلومات المستخدم
    # =====================================================

    if data == "cmdmenu:users_info":

        await edit_page(

            query,

            "🪪 <b>أوامر المستخدمين</b>\n\n"

            "<b>ايدي</b>\n"
            "عرض آيدي حسابك.\n\n"

            "<b>رتبتي</b>\n"
            "عرض رتبتك في المجموعة.\n\n"

            "<b>رتبته</b>\n"
            "عرض رتبة شخص آخر.\n\n"

            "<b>كشف</b>\n"
            "عرض معلومات الشخص.\n\n"

            "<b>كشف المجموعة</b>\n"
            "عرض معلومات المجموعة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للمستخدمين والرتب",
                        callback_data="cmdmenu:users"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # رفع الرتب
    # =====================================================

    if data == "cmdmenu:promote":

        await edit_page(

            query,

            "⬆️ <b>رفع الرتب</b>\n\n"

            "<b>رفع مميز</b>\n"
            "رفع العضو إلى رتبة مميز.\n\n"

            "<b>رفع ادمن</b>\n"
            "رفع العضو إلى رتبة ادمن.\n\n"

            "<b>رفع ادمن اساسي</b>\n"
            "رفع العضو إلى رتبة ادمن اساسي.\n\n"

            "<b>رفع نائب المالك</b>\n"
            "رفع العضو إلى رتبة نائب المالك.\n\n"

            "<b>رفع المالك</b>\n"
            "رفع العضو إلى رتبة المالك.\n\n"

            "<b>رفع Dev</b>\n"
            "رفع العضو إلى رتبة Dev.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:users"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # تنزيل الرتب
    # =====================================================

    if data == "cmdmenu:demote":

        await edit_page(

            query,

            "⬇️ <b>تنزيل الرتب</b>\n\n"

            "<b>تنزيل مميز</b>\n"
            "تنزيل رتبة مميز.\n\n"

            "<b>تنزيل ادمن</b>\n"
            "تنزيل رتبة ادمن.\n\n"

            "<b>تنزيل ادمن اساسي</b>\n"
            "تنزيل رتبة ادمن اساسي.\n\n"

            "<b>تنزيل نائب المالك</b>\n"
            "تنزيل رتبة نائب المالك.\n\n"

            "<b>تنزيل المالك</b>\n"
            "تنزيل رتبة المالك.\n\n"

            "<b>تنزيل Dev</b>\n"
            "تنزيل رتبة Dev.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:users"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الحماية
    # =====================================================

    if data == "cmdmenu:protection":

        await edit_page(

            query,

            "🛡️ <b>الحماية</b>\n\n"
            "اختر نوع الأوامر:",

            protection_keyboard()
        )

        return


    # =====================================================
    # الحظر والكتم
    # =====================================================

    if data == "cmdmenu:moderation":

        await edit_page(

            query,

            "🚫 <b>الحظر والكتم</b>\n\n"

            "<b>حظر</b>\n"
            "حظر عضو بالرد على رسالته أو باستخدام الآيدي.\n\n"

            "<b>رفع الحظر</b>\n"
            "رفع الحظر عن عضو بالرد أو باستخدام الآيدي.\n\n"

            "<b>كتم</b>\n"
            "كتم عضو بالرد على رسالته أو باستخدام الآيدي.\n\n"

            "<b>رفع الكتم</b>\n"
            "رفع الكتم عن عضو بالرد أو باستخدام الآيدي.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للحماية",
                        callback_data="cmdmenu:protection"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # منع / سماح
    # =====================================================

    if data == "cmdmenu:permissions":

        await edit_page(

            query,

            "🔐 <b>منع وسماح الأوامر</b>\n\n"

            "<b>منع (اسم الأمر)</b>\n"
            "منع استخدام أمر معين.\n\n"
            "مثال:\n"
            "<code>منع ايدي</code>\n\n"

            "<b>سماح (اسم الأمر)</b>\n"
            "السماح باستخدام أمر تم منعه.\n\n"
            "مثال:\n"
            "<code>سماح ايدي</code>",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للحماية",
                        callback_data="cmdmenu:protection"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # قفل / فتح
    # =====================================================

    if data == "cmdmenu:locks":

        await edit_page(

            query,

            "🔒 <b>قفل وفتح الأوامر</b>\n\n"

            "<b>قفل امر (اسم الأمر)</b>\n"
            "قفل أمر معين في المجموعة.\n\n"

            "مثال:\n"
            "<code>قفل امر ايدي</code>\n\n"

            "<b>فتح امر (اسم الأمر)</b>\n"
            "فتح أمر تم قفله.\n\n"

            "مثال:\n"
            "<code>فتح امر ايدي</code>",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للحماية",
                        callback_data="cmdmenu:protection"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # المسح
    # =====================================================

    if data == "cmdmenu:delete":

        await edit_page(

            query,

            "🗑️ <b>أوامر المسح</b>\n\n"

            "<b>مسح</b>\n"
            "مسح الرسائل.\n\n"

            "<b>مسح 100</b>\n"
            "مسح العدد المحدد من الرسائل.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للحماية",
                        callback_data="cmdmenu:protection"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الردود
    # =====================================================

    if data == "cmdmenu:replies":

        await edit_page(

            query,

            "💬 <b>الردود</b>\n\n"

            "<b>اضف رد</b>\n"
            "إضافة رد جديد.\n\n"

            "<b>تعديل رد</b>\n"
            "تعديل رد موجود.\n\n"

            "<b>مسح رد</b>\n"
            "حذف رد.\n\n"

            "<b>الردود</b>\n"
            "عرض الردود المضافة.\n\n"

            "<b>مسح الردود</b>\n"
            "حذف جميع الردود.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الردود المميزة
    # =====================================================

    if data == "cmdmenu:special_replies":

        await edit_page(

            query,

            "⭐ <b>الردود المميزة</b>\n\n"

            "<b>اضف رد مميز</b>\n"
            "إضافة رد مميز.\n\n"

            "<b>تعديل رد مميز</b>\n"
            "تعديل رد مميز.\n\n"

            "<b>مسح رد مميز</b>\n"
            "حذف رد مميز.\n\n"

            "<b>الردود المميزة</b>\n"
            "عرض الردود المميزة.\n\n"

            "<b>مسح الردود المميزة</b>\n"
            "حذف جميع الردود المميزة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الإدارة
    # =====================================================

    if data == "cmdmenu:admin":

        await edit_page(

            query,

            "👮 <b>أوامر الإدارة</b>\n\n"

            "<b>المطور</b>\n"
            "عرض معلومات المطور.\n\n"

            "<b>المالك</b>\n"
            "عرض معلومات المالك.\n\n"

            "<b>تغيير يوزر المطور</b>\n"
            "تغيير يوزر المطور.\n\n"

            "<b>تغيير يوزر المالك</b>\n"
            "تغيير يوزر المالك.\n\n"

            "<b>اضف ردي</b>\n"
            "إضافة ردك كأدمن.\n\n"

            "<b>حذف ردي</b>\n"
            "حذف ردك.\n\n"

            "<b>حذف رده</b>\n"
            "حذف رد أدمن.\n\n"

            "<b>ردود الادمن</b>\n"
            "عرض ردود الأدمن.\n\n"

            "<b>تفعيل ردود الادمن</b>\n"
            "تفعيل ردود الأدمن.\n\n"

            "<b>تعطيل ردود الادمن</b>\n"
            "تعطيل ردود الأدمن.\n\n"

            "<b>حذف ردود الادمن</b>\n"
            "حذف جميع ردود الأدمن.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الأوامر المضافة
    # =====================================================

    if data == "cmdmenu:custom":

        await edit_page(

            query,

            "🧩 <b>الأوامر المضافة</b>\n\n"

            "<b>اضف امر</b>\n"
            "إضافة أمر مخصص.\n\n"

            "<b>الاوامر المضافة</b>\n"
            "عرض الأوامر المضافة.\n\n"

            "<b>مسح امر</b>\n"
            "حذف أمر مضاف.\n\n"

            "<b>مسح الاوامر المضافة</b>\n"
            "حذف جميع الأوامر المضافة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # النقاط
    # =====================================================

    if data == "cmdmenu:points":

        await edit_page(

            query,

            "💰 <b>النقاط</b>\n\n"

            "<b>نقاطي</b>\n"
            "عرض نقاطك.\n\n"

            "<b>توب</b>\n"
            "عرض المتصدرين بالنقاط.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الهمسات
    # =====================================================

    if data == "cmdmenu:whispers":

        await edit_page(

            query,

            "🤫 <b>الهمسات</b>\n\n"

            "<b>اهمس</b>\n"
            "إرسال همسة.\n\n"

            "<b>همسه</b>\n"
            "إرسال همسة.\n\n"

            "<b>همسة</b>\n"
            "إرسال همسة.\n\n"

            "<b>تفعيل الهمسات</b>\n"
            "تفعيل نظام الهمسات.\n\n"

            "<b>تعطيل الهمسات</b>\n"
            "تعطيل نظام الهمسات.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الألعاب
    # =====================================================

    if data == "cmdmenu:games":

        await edit_page(

            query,

            "🎮 <b>ألعاب البوت</b>\n\n"
            "اختر اللعبة التي تريد معرفة أوامرها:",

            games_keyboard()
        )

        return


    # =====================================================
    # بلنتيات
    # =====================================================

    if data == "cmdmenu:penalties":

        await edit_page(

            query,

            "⚽ <b>لعبة البلنتيات</b>\n\n"
            "اختر ما تريد معرفته:",

            penalties_keyboard()
        )

        return


    if data == "cmdmenu:penalties_commands":

        await edit_page(

            query,

            "⚽ <b>أوامر البلنتيات</b>\n\n"

            "<b>بلنتيات</b>\n"
            "بدء تجهيز لعبة البلنتيات.\n\n"

            "<b>دخول</b>\n"
            "الدخول إلى اللعبة.\n\n"

            "<b>.وزع</b>\n"
            "توزيع اللاعبين.\n\n"

            "<b>.احمر رقم رقم</b>\n"
            "اختيار لاعبين للفريق الأحمر.\n\n"

            "<b>.ازرق رقم رقم</b>\n"
            "اختيار لاعبين للفريق الأزرق.\n\n"

            "<b>.ابدا</b>\n"
            "بدء الجولة.\n\n"

            "<b>.كمل</b>\n"
            "إكمال اللعبة.\n\n"

            "<b>انهاء بلنتيات</b>\n"
            "إنهاء اللعبة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للبلنتيات",
                        callback_data="cmdmenu:penalties"
                    )
                ]

            ])
        )

        return


    if data == "cmdmenu:penalties_help":

        await edit_page(

            query,

            "📖 <b>شرح البلنتيات</b>\n\n"
            "لعبة جماعية تعتمد على توزيع اللاعبين "
            "على الفرق ثم تنفيذ جولات البلنتيات.\n\n"
            "يمكن الدخول إلى اللعبة ثم توزيع اللاعبين "
            "يدويًا أو تلقائيًا حسب نظام اللعبة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للبلنتيات",
                        callback_data="cmdmenu:penalties"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # غميضة
    # =====================================================

    if data == "cmdmenu:hide":

        await edit_page(

            query,

            "🫣 <b>لعبة الغميضة</b>\n\n"
            "اختر ما تريد معرفته:",

            hide_keyboard()
        )

        return


    if data == "cmdmenu:hide_commands":

        await edit_page(

            query,

            "🫣 <b>أوامر الغميضة</b>\n\n"

            "<b>غميضة</b>\n"
            "بدء تجهيز اللعبة.\n\n"

            "<b>دخول</b>\n"
            "الدخول إلى اللعبة.\n\n"

            "<b>ابدا</b>\n"
            "بدء اللعبة.\n\n"

            "<b>انهاء غميضة</b>\n"
            "إنهاء اللعبة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للغميضة",
                        callback_data="cmdmenu:hide"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # الكذاب
    # =====================================================

    if data == "cmdmenu:liar":

        await edit_page(

            query,

            "🤥 <b>لعبة الكذاب</b>\n\n"
            "اختر ما تريد معرفته:",

            liar_keyboard()
        )

        return


    if data == "cmdmenu:liar_commands":

        await edit_page(

            query,

            "🤥 <b>أوامر الكذاب</b>\n\n"

            "<b>الكذاب</b>\n"
            "بدء تجهيز اللعبة.\n\n"

            "<b>دخول</b>\n"
            "الدخول إلى اللعبة.\n\n"

            "<b>.خروج</b>\n"
            "الخروج قبل بداية اللعبة.\n\n"

            "<b>.ابدا</b>\n"
            "بدء اللعبة.\n\n"

            "<b>.التصويت</b>\n"
            "بدء التصويت.\n\n"

            "<b>انهاء الكذاب</b>\n"
            "إنهاء اللعبة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع للكذاب",
                        callback_data="cmdmenu:liar"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # سباق الكلمات
    # =====================================================

    if data == "cmdmenu:word_race":

        await edit_page(

            query,

            "🏃 <b>سباق الكلمات</b>\n\n"
            "اختر ما تريد معرفته:",

            word_race_keyboard()
        )

        return


    if data == "cmdmenu:word_race_commands":

        await edit_page(

            query,

            "🏃 <b>أوامر سباق الكلمات</b>\n\n"

            "<b>سباق الكلمات</b>\n"
            "بدء تجهيز اللعبة.\n\n"

            "<b>دخول</b>\n"
            "الدخول إلى اللعبة.\n\n"

            "<b>خروج</b>\n"
            "الخروج من اللعبة.\n\n"

            "<b>.الطور</b>\n"
            "اختيار طور اللعبة.\n\n"

            "<b>.وزع</b>\n"
            "توزيع اللاعبين.\n\n"

            "<b>.اضافة احمر</b>\n"
            "إضافة لاعب للفريق الأحمر.\n\n"

            "<b>.اضافة ازرق</b>\n"
            "إضافة لاعب للفريق الأزرق.\n\n"

            "<b>.اضافة اخضر</b>\n"
            "إضافة لاعب للفريق الأخضر.\n\n"

            "<b>.اضافة اصفر</b>\n"
            "إضافة لاعب للفريق الأصفر.\n\n"

            "<b>.ابدا</b>\n"
            "بدء اللعبة.\n\n"

            "<b>.كمل</b>\n"
            "إكمال اللعبة.\n\n"

            "<b>انهاء سباق الكلمات</b>\n"
            "إنهاء اللعبة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع لسباق الكلمات",
                        callback_data="cmdmenu:word_race"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # توقع الصورة
    # =====================================================

    if data == "cmdmenu:image_quiz":

        await edit_page(

            query,

            "🖼️ <b>توقع الصورة</b>\n\n"
            "اختر ما تريد معرفته:",

            image_quiz_keyboard()
        )

        return


    if data == "cmdmenu:image_quiz_commands":

        await edit_page(

            query,

            "🖼️ <b>أوامر توقع الصورة</b>\n\n"

            "<b>توقع الصورة</b>\n"
            "بدء تجهيز اللعبة.\n\n"

            "<b>دخول</b>\n"
            "الدخول إلى اللعبة.\n\n"

            "<b>خروج</b>\n"
            "الخروج من اللعبة.\n\n"

            "<b>.اضافة</b>\n"
            "إضافة لاعب.\n\n"

            "<b>.اعدادات</b>\n"
            "فتح إعدادات اللعبة.\n\n"

            "<b>.ابدا</b>\n"
            "بدء اللعبة.\n\n"

            "<b>.كمل</b>\n"
            "إكمال اللعبة.\n\n"

            "<b>.انهاء</b>\n"
            "إنهاء اللعبة.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع لتوقع الصورة",
                        callback_data="cmdmenu:image_quiz"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # أسرع كلمة
    # =====================================================

    if data == "cmdmenu:speed_words":

        await edit_page(

            query,

            "⚡ <b>أسرع كلمة</b>\n\n"

            "<b>كلمات</b>\n"
            "بدء لعبة أسرع كلمة.",

            speed_words_keyboard()
        )

        return


    # =====================================================
    # الأنمي
    # =====================================================

    if data == "cmdmenu:anime":

        await edit_page(

            query,

            "🎌 <b>لعبة الأنمي</b>\n\n"

            "<b>انمي</b>\n"
            "بدء لعبة أسئلة الأنمي.",

            anime_keyboard()
        )

        return


    # =====================================================
    # إدارة الألعاب
    # =====================================================

    if data == "cmdmenu:games_manager":

        await edit_page(

            query,

            "⚙️ <b>إدارة الألعاب</b>\n\n"

            "<b>اضف لعبة</b>\n"
            "إضافة لعبة جديدة.\n\n"

            "<b>الالعاب</b>\n"
            "عرض الألعاب الموجودة.\n\n"

            "<b>حذف لعبة اسم اللعبة</b>\n"
            "حذف لعبة.\n\n"

            "<b>تفعيل لعبة اسم اللعبة</b>\n"
            "تفعيل لعبة.\n\n"

            "<b>تعطيل لعبة اسم اللعبة</b>\n"
            "تعطيل لعبة.\n\n"

            "<b>تفعيل الالعاب</b>\n"
            "تفعيل جميع الألعاب.\n\n"

            "<b>تعطيل الالعاب</b>\n"
            "تعطيل جميع الألعاب.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # ألوان الأزرار
    # =====================================================

    if data == "cmdmenu:colors":

        await edit_page(

            query,

            "🎨 <b>ألوان الأزرار</b>\n\n"

            "<b>تعديل لون</b>\n"
            "تغيير لون أزرار البوت.\n\n"

            "الألوان المتاحة:\n"
            "🔴 احمر\n"
            "🔵 ازرق\n"
            "🟢 اخضر\n"
            "⚪ شفاف",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return


    # =====================================================
    # المطور
    # =====================================================

    if data == "cmdmenu:developer":

        await edit_page(

            query,

            "👨‍💻 <b>أوامر المطور</b>\n\n"

            "<b>اوامر الادمن</b>\n"
            "عرض أوامر الإدارة.\n\n"

            "<b>اوامر المطور</b>\n"
            "عرض أوامر المطور.",

            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "↩️ رجوع",
                        callback_data="cmdmenu:home"
                    )
                ]

            ])
        )

        return
