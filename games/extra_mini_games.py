from __future__ import annotations
import json, random, uuid, unicodedata
from datetime import datetime, timezone
from database.pool import get_pool

WORDS_BY_LENGTH = {
    4: ["نواف","خالد","أمين","سارة","ليان","سامي","رامي","مازن","زياد","ياسر","ناصر","راشد","صالح","طارق","عادل","وليد","حمزة","حاتم","باسل","مالك","تامر","ماهر","جابر","حازم","عمار","رائد","إياد","جلال","كنان","فارس","حارس","لاعب","فريق","نحاس","حديد","زجاج","قماش","تراب","هواء","دخان","رماد","جدار","دجاج","حليب","سكين","كتاب","دفتر","ذراع","أصبع","مطار","مسجد","ملعب","متحف","فندق","شاطئ","غابة","مضرب","شبكة","حروف","نجوم","ورود","قلوب","عيون","أيام","أسود","أبيض","أحمر","أزرق","أخضر","كبير","صغير","جميل","سريع","هادئ","سعيد","حزين","ضعيف","طويل","قصير","جديد","قديم","ثقيل","خفيف","قريب","بعيد","نظيف","واضح","غامض","صادق","كاذب","شجاع","جبان","كريم","بخيل","لطيف","نشيط","كسول","مدرب","كورة","سحاب","رياح","شتاء","ربيع","خريف","صباح","مساء","طريق","شارع","قرية","دولة","عالم","وادي","قارب","مركب","حذاء","قميص","قبعة","ساعة","خاتم","سوار","مكتب","كرسي","سرير","مكيف","هاتف","شاشة","لوحة","فأرة","جهاز","موقع","صفحة","بريد","حساب","كلمة","صورة","لعبة","فكرة","سؤال","جواب","عربي","مربع","مثلث","كوكب","فضاء","سماء","ضباب","شجرة","زهرة","وردة","ثمرة","ورقة","جذور","نبات","طيور","نملة","نحلة","عقرب","أرنب","حصان","حمار","بقرة","ماعز","بلبل","بومة","غراب","ثعلب","غزال","سمكة"],
    5: ["سيارة","مدرسة","مكتبة","طائرة","حاسوب","نافذة","حديقة","مفتاح","مصباح","وسادة","حقيبة","ثلاجة","غسالة","مروحة","تلفاز","سفينة","دراجة","طاولة","ملعقة","تفاحة","ليمون","دلفين","حمامة","مطرقة","منشار","كماشة","مسمار","نظارة","جزيرة","سحابة","صحراء","خريطة","كلمات","ألوان","أصوات","ألعاب","أحلام","أوقات","أرقام","أسماء","مهاجم","بطولة","جائزة","ظهيرة","أسبوع","مدينة","ميناء","حافلة","سروال","عباءة","قلادة","محفظة","صندوق","ستارة","سجادة","سماعة","رسالة","فيديو","رواية","قصيدة","صحيفة","حقيقة","تجربة","دراسة","جامعة","نتيجة","شهادة","مختبر","أسنان","رياضة","سباحة","كتابة","قراءة","تاريخ","أحياء","إيقاع","دائرة","حيوان","أسماك","حشرات","فراشة","ذبابة","بعوضة","ثعبان","سحلية","تمساح","عصفور","طاووس","زرافة"],
}

EXTRA_WORDS = {
    4: "مجرة مذنب غيمة ساحل فلفل مقعد مطبخ غرفة مصعد قرية لحظة موعد موسم عطلة رحلة جواز حزام وشاح قطار قارب مركب وادي ضباب شروق غروب نخلة ثمرة موزة بطيخ رمان زبيب شعير زبدة مربى سلطة كعكة حلوى قهوة عصير شوكة شمعة كنبة مسبح مسرح مطعم مقهى متجر مخبز نجار حداد طباخ رسام كاتب شاعر مصور مذيع مغني ممثل قاضي شرطي جندي قائد سائق طيار بحار صياد فلاح تاجر بائع طبيب ممرض راتب نقود عملة زبون هدية دمية مكعب تحدي ورقي ذهبي وردي قبيح بطيء صاخب غاضب خائف ماهر كسول صادق كاذب نادر شائع غريب مفيد ممكن بسيط معقد عميق سطحي واسع ناعم حامض لذيذ طازج فاسد ناضج سليم صحيح ناجح فاشل متاح رائع مذهل أفضل أسوأ أقوى أضعف أسرع أبطأ أعلى أدنى كامل عشرة".split(),
    5: "ميدان مهندس مزارع مخترع قانون عنوان مقالة سفارة وزارة مملكة منطقة دقيقة ثانية تذكرة بنطال جوارب مسلسل أغنية قصيدة صحيفة ترجمة ذاكرة نتيجة جمهور خسارة شاحنة بنزين فرامل بوصلة بحيرة عاصفة إعصار حرارة برودة فاكهة مانجو كمثرى شوربة بيتزا مشروب فنجان ملعقة مقلاة أرضية جامعة مكتبة مختبر سبورة ممحاة مسطرة مقلمة تلميذ وظيفة ألوان رمادي مختلف مألوف ضروري مرتفع منخفض مفتوح ممتلئ مكسور مشهور مجهول معروف مطلوب ممنوع مسموح ممتاز صيدلي محامي".split(),
}
for length in (4, 5):
    WORDS_BY_LENGTH[length] = list(dict.fromkeys([*WORDS_BY_LENGTH[length], *EXTRA_WORDS[length]]))

WORD_HINTS = {
    "نواف": ["القوت مسوي اللي مسوي البوت"],
    "نجوم": ["تلمع", "شي بالسماء"],
    "مجرة": ["تجمع هائل من الأجرام", "بعيدة جدًا في الفضاء"],
    "مذنب": ["يظهر بذيل مضيء", "يزور السماء أحيانًا"],
    "قمر": ["ينير الليل", "يتغيّر شكله خلال الشهر"],
    "كوكب": ["يدور حول نجم", "له مكان في المجموعة الشمسية"],
    "فضاء": ["واسع جدًا وما فيه هواء نتنفسه", "خارج الغلاف الجوي"],
    "سيارة": ["وسيلة تنقّل على الطرق", "لها مقود وإطارات"],
    "طائرة": ["تسافر لمسافات بعيدة", "تعبر فوق السحاب"],
    "قطار": ["يتحرك على مسار محدد", "عرباته متصلة ببعض"],
    "سفينة": ["تبحر في الماء", "قد تحمل ركابًا أو بضائع"],
    "مدرسة": ["مكان للتعلّم", "فيها فصول وطلاب"],
    "مكتبة": ["مكان مليء بالمعرفة", "تجد فيها مصادر للقراءة"],
    "كتاب": ["صفحات تجمع معلومات أو حكاية", "رفيق محبي القراءة"],
    "هاتف": ["تتواصل به مع الآخرين", "تحمله معك غالبًا"],
    "حاسوب": ["جهاز للعمل والدراسة", "تستخدمه للبرامج والملفات"],
    "مفتاح": ["يساعدك على فتح شيء مقفل", "غالبًا تحمله معك"],
    "مصباح": ["يبدد الظلام", "مصدر للإضاءة"],
    "وسادة": ["تجعل الراحة ألطف", "تكون غالبًا على السرير"],
    "ثلاجة": ["تحافظ على برودة الأشياء", "موجودة غالبًا في المطبخ"],
    "مروحة": ["تحرك الهواء", "تخفف الإحساس بالحر"],
    "حديقة": ["مكان فيه نباتات", "مناسبة للتنزه"],
    "جزيرة": ["أرض تحيط بها المياه", "قد تكون وجهة سياحية"],
    "صحراء": ["مساحة واسعة قليلة الأمطار", "تشتهر بالرمال"],
    "شاطئ": ["تلتقي عنده اليابسة بالماء", "مكان محبب للنزهات"],
    "غابة": ["مكان تكثر فيه الأشجار", "موطن لكائنات كثيرة"],
    "بحيرة": ["ماء تحيط به اليابسة", "أصغر عادة من البحر"],
    "وردة": ["ترمز للجمال أحيانًا", "قد تُهدى في المناسبات"],
    "نخلة": ["شجرة مرتبطة بالتمر", "تنتشر في المناطق الحارة"],
    "تفاحة": ["فاكهة قد تكون حمراء أو خضراء", "ترتبط بقصة نيوتن"],
    "ليمون": ["طعمه حامض غالبًا", "يضاف للمشروبات والطعام"],
    "موزة": ["فاكهة صفراء غالبًا", "تقشر قبل أكلها"],
    "دلفين": ["كائن بحري ذكي", "يقفز فوق سطح الماء"],
    "حمامة": ["طائر يُرى في المدن", "ترمز للسلام"],
    "فراشة": ["حشرة بأجنحة ملوّنة", "تنجذب للأزهار"],
    "حصان": ["يُستخدم للركوب", "يُعرف بسرعته"],
    "قهوة": ["مشروب يرتبط بالضيافة", "رائحتها مميزة"],
    "عسل": ["ينتجه النحل", "حلو المذاق"],
    "بيتزا": ["وجبة دائرية غالبًا", "تُخبز وتُقطّع مثلثات"],
    "حليب": ["مشروب أبيض", "مصدر للكالسيوم"],
    "ملعقة": ["أداة لتناول بعض الأطعمة", "توجد بجانب الطبق"],
    "سكين": ["أداة حادة للمطبخ", "تُستخدم للتقطيع"],
    "كرسي": ["تجلس عليه", "له أرجل غالبًا"],
    "سرير": ["مكان للنوم والراحة", "تجده في غرفة النوم"],
    "نافذة": ["تسمح بدخول الضوء", "تطل على الخارج"],
    "مظلة": ["تحميك من المطر أو الشمس", "تُفتح فوق الرأس"],
    "ساعة": ["تساعدك على معرفة الوقت", "قد تُلبس في المعصم"],
    "سماعة": ["تسمع منها الصوت", "قد توضع على الأذن"],
    "كاميرا": ["توثق اللحظات", "تلتقط الصور"],
    "رسالة": ["تنقل كلامًا لشخص آخر", "قد تصلك على الهاتف"],
    "رواية": ["حكاية طويلة مكتوبة", "لها شخصيات وأحداث"],
    "قصيدة": ["كلمات بإيقاع أو وزن", "يكتبها الشاعر"],
    "طبيب": ["يساعد المرضى", "يعمل في مجال الصحة"],
    "مهندس": ["يخطط أو يصمم أو يبني", "تتنوع تخصصاته"],
    "نجار": ["يتعامل مع الخشب", "يصنع الأثاث أحيانًا"],
    "طيار": ["يقود وسيلة جوية", "عمله مرتبط بالمطارات"],
    "مزارع": ["يعتني بالمحاصيل", "يرتبط عمله بالأرض"],
    "مصور": ["يوثق المشاهد", "يهتم باللقطات والزوايا"],
    "مهاجم": ["دوره هجومي في الملعب", "يحاول تسجيل الأهداف"],
    "حارس": ["يحمي المرمى أو المكان", "يراقب ويحاول المنع"],
    "جمهور": ["يشجع من المدرجات", "يرفع الحماس في المباريات"],
    "ألوان": ["تجعل الأشياء أكثر تنوعًا", "منها الأساسي ومنها الثانوي"],
    "أحمر": ["لون يرتبط بالورود أحيانًا", "من ألوان إشارة المرور"],
    "أزرق": ["لون يذكّر بالبحر والسماء", "درجة باردة"],
    "شتاء": ["أحد فصول السنة", "يرتبط بالبرد"],
    "صيف": ["أحد فصول السنة", "يرتبط بالحرارة"],
    "ضباب": ["يقلل وضوح الرؤية", "يشبه سحابة قريبة من الأرض"],
    "عاصفة": ["حالة جوية قوية", "قد يصاحبها رياح وأمطار"],
    "مسرح": ["تُعرض عليه أعمال مباشرة", "ترتبط به الستارة والجمهور"],
    "متحف": ["يحفظ أشياء لها قيمة تاريخية", "تُعرض فيه مقتنيات"],
    "فندق": ["مكان للإقامة المؤقتة", "يحجز فيه المسافر غرفة"],
    "مطار": ["تبدأ منه رحلات جوية", "توجد فيه بوابات سفر"],
};
def _word_hint(word):
    folded = _fold(word)
    if folded == _fold("نواف"):
        return "القوت مسوي اللي مسوي البوت"
    choices = next((value for key, value in WORD_HINTS.items() if _fold(key) == folded), None)
    if choices:
        return random.choice(choices)
    groups = [
        ("نجوم كوكب مجرة مذنب فضاء سماء سحاب غيمة ضباب قمر شمس", "له علاقة بالسماء والفضاء"),
        ("شجرة زهرة وردة نخلة غابة وادي ساحل شاطئ جزيرة صحراء بحيرة", "من الطبيعة"),
        ("سيارة طائرة قطار سفينة حافلة دراجة قارب مركب شاحنة", "وسيلة تنقّل"),
        ("تفاحة ليمون موزة بطيخ رمان زبيب شعير زبدة مربى سلطة كعكة حلوى قهوة عصير بيتزا شوربة", "شيء له علاقة بالأكل أو الشرب"),
        ("دلفين حمامة فراشة حصان أرنب سمكة ثعلب غزال نحلة نملة بومة غراب", "كائن حي"),
        ("مدرسة جامعة مكتبة مختبر مطار محطة فندق مطعم مقهى متجر مخبز مسرح متحف", "مكان ممكن تزوره"),
        ("طبيب مهندس نجار حداد طباخ رسام كاتب شاعر مصور مذيع مغني ممثل قاضي شرطي جندي قائد سائق طيار بحار صياد فلاح تاجر بائع ممرض", "مهنة أو دور لشخص"),
        ("أحمر أزرق أخضر أصفر أسود أبيض بنفسجي وردي ذهبي فضي رمادي", "درجة من الألوان"),
        ("مهاجم مدافع حارس مدرب لاعب فريق بطولة جائزة جمهور نتيجة خسارة", "له علاقة بالرياضة"),
        ("مقعد كرسي سرير كنبة وسادة خزانة طاولة مكتب", "قطعة من الأثاث أو شيء للجلوس والراحة"),
        ("مطبخ غرفة نافذة مصعد جدار سقف قرية", "جزء من مكان أو مبنى"),
        ("لحظة موعد موسم عطلة رحلة شروق غروب", "مرتبط بالوقت أو بأحد أوقات اليوم"),
        ("جواز تذكرة حزام وشاح بنطال جوارب قبعة قميص حذاء", "شيء قد تحتاجه في السفر أو اللبس"),
        ("شوكة ملعقة سكين طبق قدر مقلاة فرن", "أداة تستخدمها في المطبخ أو على المائدة"),
        ("شمعة مصباح مفتاح بطارية شاحن سماعة كاميرا", "غرض نستخدمه في حياتنا اليومية"),
        ("راتب نقود عملة زبون سعر ثمن فاتورة تاجر بائع", "له علاقة بالشراء والبيع"),
        ("هدية دمية مكعب تحدي لعبة", "شيء يرتبط باللعب أو المناسبات"),
        ("قبيح بطيء صاخب غاضب خائف ماهر كسول صادق كاذب نادر شائع غريب مفيد ممكن بسيط معقد عميق سطحي واسع ناعم حامض لذيذ طازج فاسد ناضج سليم صحيح ناجح فاشل متاح رائع مذهل أفضل أسوأ أقوى أضعف أسرع أبطأ أعلى أدنى كامل", "صفة تصف شيئًا أو شخصًا"),
    ]
    for words, hint in groups:
        if folded in {_fold(w) for w in words.split()}:
            return hint
    return "فكّر في المكان أو الموقف اللي ممكن تشوفه فيه"

def _decode(v):
    return json.loads(v) if isinstance(v, str) else (v or {})

def _fold(text):
    s = unicodedata.normalize("NFKC", str(text or "")).strip().replace("ـ", "")
    s = "".join(ch for ch in s if unicodedata.category(ch) not in ("Mn", "Me"))
    return s.translate(str.maketrans({"أ":"ا", "إ":"ا", "آ":"ا", "ٱ":"ا", "ى":"ي", "ؤ":"و", "ئ":"ي", "ة":"ه"}))

def word_feedback(target, guess):
    if len(guess) != len(target):
        return None
    tf, gf = _fold(target), _fold(guess)
    result = [None] * len(target)
    remaining = list(tf)
    for i in range(len(target)):
        if gf[i] == tf[i]:
            result[i] = "green" if guess[i] == target[i] else "green_purple"
            remaining[i] = None
    for i in range(len(target)):
        if result[i] is not None:
            continue
        try:
            pos = remaining.index(gf[i])
        except ValueError:
            result[i] = "white"
            continue
        result[i] = "orange" if guess[i] == target[pos] else "yellow_purple"
        remaining[pos] = None
    return result

def _new_words(count, length):
    length = int(length)
    if length in WORDS_BY_LENGTH:
        pool = list(WORDS_BY_LENGTH[length])
        random.shuffle(pool)
        return pool[:count]
    if length != 0:
        raise ValueError("اختر كلمات من 4 أو 5 أحرف أو كلهم")
    if count == 1:
        return random.sample(WORDS_BY_LENGTH[random.choice((4, 5))], 1)
    # Mixed mode alternates predictably: 4 letters, then 5, then 4, then 5.
    four_count = (count + 1) // 2
    five_count = count // 2
    four_words = iter(random.sample(WORDS_BY_LENGTH[4], four_count))
    five_words = iter(random.sample(WORDS_BY_LENGTH[5], five_count))
    return [next(four_words) if i % 2 == 0 else next(five_words) for i in range(count)]

def _public_word(row, user_id):
    players = _decode(row["players"])
    me = next((p for p in players if int(p["id"]) == int(user_id)), None)
    answers = _decode(row["answers"])
    guesses_by_player = answers.get("guesses") or {}
    my_guesses = guesses_by_player.get(str(int(user_id)), [])
    winner = None
    if players and row["status"] == "finished":
        high = max(int(p.get("score", 0)) for p in players)
        leaders = [p for p in players if int(p.get("score", 0)) == high]
        winner = leaders[0]["name"] if len(leaders) == 1 else "تعادل"
    idx = int(row["current_index"])
    word_list = _decode(row["words"])
    current_word = word_list[idx] if row["status"] == "playing" and idx < len(word_list) else None
    hint_votes = answers.get("hint_votes") or []
    hint_votes_needed = max(1, (2 * len(players) + 2) // 3)
    return {
        "id": str(row["id"]), "mode": row["mode"], "status": row["status"],
        "word_limit": row["word_limit"], "win_target": row["win_target"],
        "attempts_limit": row["attempts_limit"], "attempts_left": max(0, int(row["attempts_limit"]) - len(my_guesses)),
        "word_length": row["word_length"], "round_seconds": row["round_seconds"],
        "my_guesses": my_guesses,
        "current_index": idx, "total": row["word_limit"],
        "players": [{"id": p["id"], "name": p["name"], "score": p.get("score", 0), "attempts_used": len(guesses_by_player.get(str(int(p["id"])), [])), "attempts_left": max(0, int(row["attempts_limit"]) - len(guesses_by_player.get(str(int(p["id"])), [])))} for p in players],
        "my_score": me.get("score", 0) if me else 0, "is_player": bool(me),
        "is_owner": int(row["owner_id"]) == int(user_id),
        "current_word_length": len(current_word) if current_word else None,
        "hint": answers.get("hint"),
        "hint_id": answers.get("hint_id"),
        "hint_until": answers.get("hint_until"),
        "hint_votes_count": len(hint_votes),
        "hint_votes_needed": hint_votes_needed,
        "my_hint_vote": str(int(user_id)) in {str(v) for v in hint_votes},
        "round_deadline": int(row["round_deadline"].timestamp() * 1000) if row["round_deadline"] else None,
        "round_until": int(row["round_until"].timestamp() * 1000) if row["round_until"] else None,
        "round_winner": answers.get("round_winner"), "round_word": answers.get("last_word"),
        "round_end_reason": answers.get("round_end_reason"),
        "last_withdrawal": answers.get("last_withdrawal"),
        "last_guess": answers.get("last_guess"), "last_feedback": answers.get("last_feedback"),
        "words": word_list if row["status"] == "finished" else [],
        "winner": winner,
        "started_at": int(row["started_at"].timestamp() * 1000) if row["started_at"] else None,
    }

async def word_create(user_id, name, mode="online", word_count=5, win_target=None,
                      attempts_limit=6, word_length=5, round_seconds=180):
    word_count = int(word_count)
    word_length = int(word_length)
    attempts_limit = int(attempts_limit)
    round_seconds = int(round_seconds)
    if not 1 <= word_count <= 15:
        raise ValueError("اختر من 1 إلى 15 كلمة")
    if mode not in ("online", "training"):
        raise ValueError("طور اللعبة غير صالح")
    if word_length not in (0, 4, 5):
        raise ValueError("اختر كلمات من 4 أو 5 أحرف أو كلهم")
    if not 1 <= attempts_limit <= 12:
        raise ValueError("عدد المحاولات يجب أن يكون من 1 إلى 12")
    if not 15 <= round_seconds <= 3600:
        raise ValueError("مدة الجولة يجب أن تكون بين 15 و3600 ثانية")
    target = max(1, min(int(win_target or word_count), word_count))
    gid = uuid.uuid4()
    words = _new_words(word_count, word_length)
    players = [{"id": int(user_id), "name": str(name or "لاعب")[:80], "score": 0}]
    status = "playing" if mode == "training" else "waiting"
    pool = get_pool()
    row = await pool.fetchrow(
        """INSERT INTO word_games
        (id,owner_id,mode,status,max_players,word_limit,win_target,words,players,
         attempts_limit,word_length,round_seconds,started_at,round_deadline)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12,
          CASE WHEN $4='playing' THEN NOW() ELSE NULL END,
          CASE WHEN $4='playing' THEN NOW()+($12::integer * INTERVAL '1 second') ELSE NULL END)
        RETURNING *""",
        gid, int(user_id), mode, status, 1 if mode == "training" else 10,
        word_count, target, json.dumps(words, ensure_ascii=False),
        json.dumps(players, ensure_ascii=False), attempts_limit, word_length, round_seconds
    )
    return _public_word(row, user_id)


async def word_update_settings(user_id, raw_id, word_count=5, win_target=3,
                               attempts_limit=6, word_length=5, round_seconds=180):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط الغرفة غير صالح")
    word_count = int(word_count)
    win_target = int(win_target)
    attempts_limit = int(attempts_limit)
    word_length = int(word_length)
    round_seconds = int(round_seconds)
    if not 1 <= word_count <= 15:
        raise ValueError("عدد الكلمات يجب أن يكون من 1 إلى 15")
    if word_length not in (0, 4, 5):
        raise ValueError("اختر كلمات من 4 أو 5 أحرف أو كلهم")
    if not 1 <= attempts_limit <= 12:
        raise ValueError("عدد المحاولات يجب أن يكون من 1 إلى 12")
    if not 15 <= round_seconds <= 3600:
        raise ValueError("مدة الجولة يجب أن تكون بين 15 و3600 ثانية")
    if not 1 <= win_target <= word_count:
        raise ValueError("عدد الكلمات الصحيحة للفوز يجب ألا يتجاوز عدد كلمات اللعبة")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if int(row["owner_id"]) != int(user_id):
                raise ValueError("تعديل الإعدادات لصاحب الغرفة فقط")
            if row["status"] != "waiting":
                raise ValueError("لا يمكن تعديل الإعدادات بعد بدء اللعبة")
            words = _new_words(word_count, word_length)
            row = await c.fetchrow(
                """UPDATE word_games SET word_limit=$2,win_target=$3,words=$4::jsonb,
                   attempts_limit=$5,word_length=$6,round_seconds=$7,updated_at=NOW()
                   WHERE id=$1 RETURNING *""",
                gid, word_count, win_target, json.dumps(words, ensure_ascii=False),
                attempts_limit, word_length, round_seconds,
            )
    return _public_word(row, user_id)

async def word_join(user_id, name, raw_id):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط الغرفة غير صالح")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if row["status"] != "waiting":
                return _public_word(row, user_id)
            players = _decode(row["players"])
            if not any(int(p["id"]) == int(user_id) for p in players):
                if len(players) >= 10:
                    raise ValueError("اكتمل عدد اللاعبين")
                players.append({"id": int(user_id), "name": str(name or "لاعب")[:80], "score": 0})
                await c.execute("UPDATE word_games SET players=$2::jsonb,updated_at=NOW() WHERE id=$1",
                                gid, json.dumps(players, ensure_ascii=False))
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1", gid)
    return _public_word(row, user_id)

async def word_start(user_id, raw_id):
    gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row or int(row["owner_id"]) != int(user_id):
                raise ValueError("بدء اللعبة لصاحب الغرفة فقط")
            if row["status"] != "waiting":
                raise ValueError("اللعبة بدأت بالفعل")
            if len(_decode(row["players"])) < 2:
                raise ValueError("تحتاج لاعبين على الأقل")
            row = await c.fetchrow(
                """UPDATE word_games SET status='playing',started_at=NOW(),
                round_deadline=NOW()+(round_seconds * INTERVAL '1 second'),
                round_until=NULL,answers='{}'::jsonb,updated_at=NOW()
                WHERE id=$1 RETURNING *""", gid
            )
    return _public_word(row, user_id)

async def word_state(user_id, raw_id):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if row["status"] == "playing" and row["round_deadline"] and row["round_deadline"] <= datetime.now(timezone.utc) and row["round_until"] is None:
                words = _decode(row["words"])
                idx = int(row["current_index"])
                answers = _decode(row["answers"])
                answers.update({"last_word": words[idx], "round_end_reason": "timeout"})
                row = await c.fetchrow(
                    """UPDATE word_games SET answers=$2::jsonb,round_until=NOW()+INTERVAL '3 seconds',
                    round_deadline=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
    return _public_word(row, user_id)

async def word_hint_vote(user_id, raw_id):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row or row["status"] != "playing":
                raise ValueError("اللعبة غير نشطة")
            players = _decode(row["players"])
            if not any(int(p["id"]) == int(user_id) for p in players):
                raise ValueError("التصويت متاح للاعبين فقط")
            if row["round_until"] is not None:
                raise ValueError("انتهت الجولة")
            if row["round_deadline"] and row["round_deadline"] <= datetime.now(timezone.utc):
                raise ValueError("انتهى وقت الجولة")
            answers = _decode(row["answers"])
            if answers.get("hint"):
                return _public_word(row, user_id)
            votes = {str(v) for v in (answers.get("hint_votes") or [])}
            votes.add(str(int(user_id)))
            answers["hint_votes"] = sorted(votes)
            needed = max(1, (2 * len(players) + 2) // 3)
            if len(votes) >= needed:
                words = _decode(row["words"])
                target = words[int(row["current_index"])]
                answers["hint"] = _word_hint(target)
                answers["hint_id"] = uuid.uuid4().hex
                answers["hint_until"] = int(datetime.now(timezone.utc).timestamp() * 1000) + 5000
            row = await c.fetchrow(
                "UPDATE word_games SET answers=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                gid, json.dumps(answers, ensure_ascii=False)
            )
    return _public_word(row, user_id)


async def word_guess(user_id, raw_id, guess):
    gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    guess = str(guess or "").strip()
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row or row["status"] != "playing":
                raise ValueError("اللعبة غير نشطة")
            players = _decode(row["players"])
            me = next((p for p in players if int(p["id"]) == int(user_id)), None)
            if not me:
                raise ValueError("أنت متفرج ولا يمكنك الإجابة")
            answers = _decode(row["answers"])
            if row["round_until"] is not None:
                raise ValueError("انتهت الجولة، انتظر الكلمة التالية")
            if row["round_deadline"] and row["round_deadline"] <= datetime.now(timezone.utc):
                words = _decode(row["words"])
                answers.update({"last_word": words[int(row["current_index"])], "round_end_reason": "timeout"})
                row = await c.fetchrow(
                    """UPDATE word_games SET answers=$2::jsonb,round_until=NOW()+INTERVAL '3 seconds',
                    round_deadline=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
                return {"round_over": True, "state": _public_word(row, user_id)}
            target_length = len(_decode(row["words"])[int(row["current_index"])])
            if len(guess) != target_length:
                raise ValueError(f"اكتب كلمة من {target_length} أحرف")
            if any(ch.isspace() for ch in guess):
                raise ValueError("اكتب الكلمة بدون مسافات")
            guesses_by_player = answers.setdefault("guesses", {})
            mine = guesses_by_player.setdefault(str(int(user_id)), [])
            if len(mine) >= int(row["attempts_limit"]):
                raise ValueError("خلصت محاولاتك في هذه الكلمة")
            words = _decode(row["words"])
            target = words[int(row["current_index"])]
            feedback = word_feedback(target, guess)
            mine.append({"guess": guess, "feedback": feedback})
            if _fold(guess) == _fold(target):
                me["score"] = int(me.get("score", 0)) + 1
                answers.update({"round_winner": me["name"], "last_word": target,
                                "last_guess": guess, "last_feedback": feedback,
                                "round_end_reason": "winner"})
                row = await c.fetchrow(
                    """UPDATE word_games SET players=$2::jsonb,answers=$3::jsonb,
                    round_until=NOW()+INTERVAL '3 seconds',round_deadline=NULL,updated_at=NOW()
                    WHERE id=$1 RETURNING *""",
                    gid, json.dumps(players, ensure_ascii=False), json.dumps(answers, ensure_ascii=False)
                )
                return {"correct": True, "state": _public_word(row, user_id)}
            all_out = all(
                len(guesses_by_player.get(str(int(p["id"])), [])) >= int(row["attempts_limit"])
                for p in players
            )
            if all_out:
                answers.update({"last_word": target, "round_end_reason": "attempts"})
                row = await c.fetchrow(
                    """UPDATE word_games SET answers=$2::jsonb,round_until=NOW()+INTERVAL '3 seconds',
                    round_deadline=NULL,updated_at=NOW() WHERE id=$1 RETURNING *""",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
            else:
                row = await c.fetchrow(
                    "UPDATE word_games SET answers=$2::jsonb,updated_at=NOW() WHERE id=$1 RETURNING *",
                    gid, json.dumps(answers, ensure_ascii=False)
                )
    return {"correct": False, "feedback": feedback, "state": _public_word(row, user_id)}


async def word_leave(user_id, raw_id):
    try:
        gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    except Exception:
        raise ValueError("رابط اللعبة غير صالح")
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            players = _decode(row["players"])
            leaver = next((p for p in players if int(p["id"]) == int(user_id)), None)
            if not leaver:
                raise ValueError("أنت لست لاعبًا في هذه الغرفة")
            if row["status"] == "finished":
                return _public_word(row, user_id)
            players = [p for p in players if int(p["id"]) != int(user_id)]
            answers = _decode(row["answers"])
            answers["last_withdrawal"] = {
                "id": int(user_id), "name": str(leaver.get("name") or "مستخدم"),
                "at": int(datetime.now(timezone.utc).timestamp() * 1000)
            }
            status = "finished" if len(players) <= 1 else row["status"]
            row = await c.fetchrow(
                """UPDATE word_games SET players=$2::jsonb,answers=$3::jsonb,status=$4,
                   round_deadline=CASE WHEN $4='finished' THEN NULL ELSE round_deadline END,
                   round_until=CASE WHEN $4='finished' THEN NULL ELSE round_until END,
                   finished_at=CASE WHEN $4='finished' THEN NOW() ELSE finished_at END,
                   updated_at=NOW() WHERE id=$1 RETURNING *""",
                gid, json.dumps(players, ensure_ascii=False),
                json.dumps(answers, ensure_ascii=False), status
            )
            if status == "finished" and len(players) == 1:
                from database.game_stats import record_game_results
                await record_game_results(
                    f"mini-word:{gid}", "word_guess", [players[0]], [], conn=c
                )
    return _public_word(row, user_id)

async def word_next(user_id, raw_id):
    gid = uuid.UUID(hex=str(raw_id).replace("-", ""))
    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("SELECT * FROM word_games WHERE id=$1 FOR UPDATE", gid)
            if not row:
                raise ValueError("الغرفة غير موجودة")
            if row["status"] != "playing":
                return _public_word(row, user_id)
            if not any(int(p["id"]) == int(user_id) for p in _decode(row["players"])):
                raise ValueError("المتفرجون لا يمكنهم الانتقال بين الجولات")
            if row["round_until"] is None:
                return _public_word(row, user_id)
            if row["round_until"] > datetime.now(timezone.utc):
                return _public_word(row, user_id)
            nxt = int(row["current_index"]) + 1
            players = _decode(row["players"])
            reached = any(int(p.get("score", 0)) >= int(row["win_target"]) for p in players)
            status = "finished" if nxt >= int(row["word_limit"]) or (row["mode"] == "training" and reached) else "playing"
            row = await c.fetchrow(
                """UPDATE word_games SET current_index=$2,status=$3,answers='{}'::jsonb,
                round_until=NULL,round_deadline=CASE WHEN $3='playing'
                THEN NOW()+(round_seconds * INTERVAL '1 second') ELSE NULL END,
                updated_at=NOW(),finished_at=CASE WHEN $3='finished' THEN NOW() ELSE finished_at END
                WHERE id=$1 RETURNING *""", gid, nxt, status
            )
            if status == "finished":
                players = _decode(row["players"])
                if row["mode"] == "training":
                    player = players[0] if players else None
                    if player:
                        won = int(player.get("score", 0)) >= int(row["win_target"])
                        winners = [player] if won else []
                        losers = [player] if not won else []
                        from database.game_stats import record_game_results
                        await record_game_results(f"mini-word:{gid}", "word_guess", winners, losers, conn=c)
                elif players:
                    high = max(int(p.get("score", 0)) for p in players)
                    leaders = [p for p in players if int(p.get("score", 0)) == high]
                    if len(leaders) == 1:
                        winner_id = int(leaders[0]["id"])
                        winners = [p for p in players if int(p["id"]) == winner_id]
                        losers = [p for p in players if int(p["id"]) != winner_id]
                        from database.game_stats import record_game_results
                        await record_game_results(f"mini-word:{gid}", "word_guess", winners, losers, conn=c)
    return _public_word(row, user_id)
