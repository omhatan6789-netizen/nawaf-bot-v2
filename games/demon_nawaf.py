import asyncio
import json
import math
import re

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database.pool import get_pool

GAME_NAME = "ديمون نواف"
MAX_QUESTIONS = 30
HTTP_TIMEOUT = 5

# traits = صفات منطقية تستخدم لاختيار الأسئلة وترتيب الشخصيات.
SEED_CHARACTERS = [
    ("neymar", "نيمار جونيور", "Neymar Jr.", "كرة القدم", "Football", "Neymar", ["male", "alive", "arabic_speaker_no", "football", "athlete", "brazilian", "famous", "real"]),
    ("ronaldo", "كريستيانو رونالدو", "Cristiano Ronaldo", "كرة القدم", "Football", "Cristiano Ronaldo", ["male", "alive", "football", "athlete", "portuguese", "famous", "real"]),
    ("messi", "ليونيل ميسي", "Lionel Messi", "كرة القدم", "Football", "Lionel Messi", ["male", "alive", "football", "athlete", "argentinian", "famous", "real"]),
    ("mbappe", "كيليان مبابي", "Kylian Mbappé", "كرة القدم", "Football", "Kylian Mbappé", ["male", "alive", "football", "athlete", "french", "famous", "real"]),
    ("salah", "محمد صلاح", "Mohamed Salah", "كرة القدم", "Football", "Mohamed Salah", ["male", "alive", "football", "athlete", "arab", "egyptian", "famous", "real"]),
    ("benzema", "كريم بنزيما", "Karim Benzema", "كرة القدم", "Football", "Karim Benzema", ["male", "alive", "football", "athlete", "arab", "french", "famous", "real"]),
    ("yasser", "ياسر القحطاني", "Yasser Al-Qahtani", "كرة القدم", "Football", "Yasser Al-Qahtani", ["male", "alive", "football", "athlete", "saudi", "arab", "famous", "real"]),
    ("salem", "سالم الدوسري", "Salem Al-Dawsari", "كرة القدم", "Football", "Salem Al-Dawsari", ["male", "alive", "football", "athlete", "saudi", "arab", "famous", "real"]),
    ("mrbeast", "مستر بيست", "MrBeast", "يوتيوبر", "YouTuber", "MrBeast", ["male", "alive", "youtuber", "american", "famous", "real"]),
    ("pewdiepie", "بيوديباي", "PewDiePie", "يوتيوبر", "YouTuber", "PewDiePie", ["male", "alive", "youtuber", "swedish", "famous", "real"]),
    ("shongx_bong", "شونق بونق", "Shongx Bong", "يوتيوبر", "YouTuber", "شونق بونق", ["male", "alive", "youtuber", "saudi", "arab", "famous", "real", "gamer", "streamer", "gaming_creator", "esports_clan", "falcons"]),
    ("bandarita", "بندريتا", "Bandarita", "يوتيوبر", "YouTuber", "بندريتا", ["male", "alive", "youtuber", "saudi", "arab", "famous", "real", "gamer", "minecraft", "roblox", "gaming_creator"]),
    ("aboflah", "أبو فلة", "AboFlah", "يوتيوبر", "YouTuber", "AboFlah", ["male", "alive", "youtuber", "arab", "kuwaiti", "famous", "real", "gamer", "streamer", "gaming_creator", "challenges"]),
    ("shakira", "شاكيرا", "Shakira", "مغنية", "Singer", "Shakira", ["female", "alive", "singer", "colombian", "famous", "real"]),
    ("taylor", "تايلور سويفت", "Taylor Swift", "مغنية", "Singer", "Taylor Swift", ["female", "alive", "singer", "american", "famous", "real"]),
    ("justin", "جاستن بيبر", "Justin Bieber", "مغنٍ", "Singer", "Justin Bieber", ["male", "alive", "singer", "canadian", "famous", "real"]),
    ("jackie", "جاكي شان", "Jackie Chan", "ممثل", "Actor", "Jackie Chan", ["male", "alive", "actor", "chinese", "famous", "real"]),
    ("tomcruise", "توم كروز", "Tom Cruise", "ممثل", "Actor", "Tom Cruise", ["male", "alive", "actor", "american", "famous", "real"]),
    ("ironman", "آيرون مان", "Iron Man", "مارفل", "Marvel", "Iron Man", ["male", "fictional", "superhero", "marvel", "american", "famous"]),
    ("spiderman", "سبايدرمان", "Spider-Man", "مارفل", "Marvel", "Spider-Man", ["male", "fictional", "superhero", "marvel", "american", "famous"]),
    ("batman", "باتمان", "Batman", "دي سي", "DC", "Batman", ["male", "fictional", "superhero", "dc", "american", "famous"]),
    ("superman", "سوبرمان", "Superman", "دي سي", "DC", "Superman", ["male", "fictional", "superhero", "dc", "alien", "famous"]),
    ("naruto", "ناروتو أوزوماكي", "Naruto Uzumaki", "أنمي", "Anime", "Naruto Uzumaki", ["male", "fictional", "anime", "ninja", "japanese", "famous"]),
    ("luffy", "مونكي دي لوفي", "Monkey D. Luffy", "أنمي", "Anime", "Monkey D. Luffy", ["male", "fictional", "anime", "pirate", "japanese", "famous"]),
    ("zoro", "رورونوا زورو", "Roronoa Zoro", "أنمي", "Anime", "Roronoa Zoro", ["male", "fictional", "anime", "swordsman", "japanese", "famous"]),
    ("goku", "سون غوكو", "Son Goku", "أنمي", "Anime", "Son Goku", ["male", "fictional", "anime", "fighter", "alien", "japanese", "famous"]),
    ("levi", "ليفاي أكرمان", "Levi Ackerman", "أنمي", "Anime", "Levi Ackerman", ["male", "fictional", "anime", "soldier", "japanese", "famous"]),
    ("mikasa", "ميكاسا أكرمان", "Mikasa Ackerman", "أنمي", "Anime", "Mikasa Ackerman", ["female", "fictional", "anime", "soldier", "japanese", "famous"]),
    ("light", "لايت ياغامي", "Light Yagami", "أنمي", "Anime", "Light Yagami", ["male", "fictional", "anime", "student", "japanese", "famous"]),
    ("lelouch", "لولوش لامبيروج", "Lelouch Lamperouge", "أنمي", "Anime", "Lelouch Lamperouge", ["male", "fictional", "anime", "strategist", "japanese", "famous"]),
    ("sherlock", "شيرلوك هولمز", "Sherlock Holmes", "شخصية خيالية", "Fictional character", "Sherlock Holmes", ["male", "fictional", "detective", "british", "famous"]),
    ("harrypotter", "هاري بوتر", "Harry Potter", "شخصية خيالية", "Fictional character", "Harry Potter", ["male", "fictional", "wizard", "british", "famous"]),
    ("putin", "فلاديمير بوتين", "Vladimir Putin", "سياسة", "Politics", "Vladimir Putin", ["male", "alive", "politician", "russian", "famous", "real"]),
    ("trump", "دونالد ترامب", "Donald Trump", "سياسة", "Politics", "Donald Trump", ["male", "alive", "politician", "american", "famous", "real"]),
    ("obama", "باراك أوباما", "Barack Obama", "سياسة", "Politics", "Barack Obama", ["male", "alive", "politician", "american", "famous", "real"]),
    ("king_salman", "الملك سلمان بن عبدالعزيز", "King Salman", "شخصية سياسية", "Politics", "Salman of Saudi Arabia", ["male", "alive", "politician", "saudi", "arab", "royal", "famous", "real"]),
    ("mohammed_bin_salman", "محمد بن سلمان", "Mohammed bin Salman", "شخصية سياسية", "Politics", "Mohammed bin Salman", ["male", "alive", "politician", "saudi", "arab", "royal", "famous", "real"]),
    ("einstein", "ألبرت أينشتاين", "Albert Einstein", "عالم", "Scientist", "Albert Einstein", ["male", "deceased", "scientist", "german", "famous", "real", "historical"]),
    ("tesla", "نيكولا تسلا", "Nikola Tesla", "مخترع", "Inventor", "Nikola Tesla", ["male", "deceased", "scientist", "inventor", "serbian", "famous", "real", "historical"]),
    ("cleopatra", "كليوباترا", "Cleopatra", "شخصية تاريخية", "Historical figure", "Cleopatra", ["female", "deceased", "egyptian", "royal", "historical", "famous", "real"]),
    ("napoleon", "نابليون بونابرت", "Napoleon Bonaparte", "شخصية عسكرية", "Military figure", "Napoleon", ["male", "deceased", "military", "french", "historical", "famous", "real"]),
    ("salahuddin", "صلاح الدين الأيوبي", "Saladin", "شخصية عسكرية", "Military figure", "Saladin", ["male", "deceased", "military", "arab", "historical", "famous", "real"]),
    ("captain_america", "كابتن أمريكا", "Captain America", "مارفل", "Marvel", "Captain America", ["male", "fictional", "superhero", "marvel", "american", "famous"]),
    ("hitler", "أدولف هتلر", "Adolf Hitler", "شخصية تاريخية", "Historical figure", "Adolf Hitler", ["male", "deceased", "real", "historical", "politician", "german", "military", "famous"]),
    ("stalin", "جوزيف ستالين", "Joseph Stalin", "شخصية تاريخية", "Historical figure", "Joseph Stalin", ["male", "deceased", "real", "historical", "politician", "russian", "military", "famous"]),
    ("churchill", "ونستون تشرشل", "Winston Churchill", "شخصية تاريخية", "Historical figure", "Winston Churchill", ["male", "deceased", "real", "historical", "politician", "british", "military", "famous"]),
    ("lincoln", "أبراهام لينكولن", "Abraham Lincoln", "شخصية تاريخية", "Historical figure", "Abraham Lincoln", ["male", "deceased", "real", "historical", "politician", "american", "famous"]),
    ("george_washington", "جورج واشنطن", "George Washington", "شخصية تاريخية", "Historical figure", "George Washington", ["male", "deceased", "real", "historical", "politician", "american", "military", "famous"]),
    ("julius_caesar", "يوليوس قيصر", "Julius Caesar", "شخصية تاريخية", "Historical figure", "Julius Caesar", ["male", "deceased", "real", "historical", "roman", "military", "politician", "famous"]),
    ("alexander_great", "الإسكندر الأكبر", "Alexander the Great", "شخصية تاريخية", "Historical figure", "Alexander the Great", ["male", "deceased", "real", "historical", "military", "royal", "famous"]),
    ("genghis_khan", "جنكيز خان", "Genghis Khan", "شخصية تاريخية", "Historical figure", "Genghis Khan", ["male", "deceased", "real", "historical", "military", "famous"]),
    ("queen_elizabeth", "الملكة إليزابيث الثانية", "Queen Elizabeth II", "شخصية ملكية", "Royalty", "Elizabeth II", ["female", "deceased", "real", "historical", "royal", "british", "famous"]),
    ("marilyn_monroe", "مارلين مونرو", "Marilyn Monroe", "ممثلة", "Actor", "Marilyn Monroe", ["female", "deceased", "real", "actor", "american", "famous"]),
    ("michael_jackson", "مايكل جاكسون", "Michael Jackson", "مغنٍ", "Singer", "Michael Jackson", ["male", "deceased", "real", "singer", "american", "famous"]),
    ("elvis_presley", "إلفيس بريسلي", "Elvis Presley", "مغنٍ", "Singer", "Elvis Presley", ["male", "deceased", "real", "singer", "american", "famous"]),
    ("bob_marley", "بوب مارلي", "Bob Marley", "مغنٍ", "Singer", "Bob Marley", ["male", "deceased", "real", "singer", "jamaican", "famous"]),
    ("freddie_mercury", "فريدي ميركوري", "Freddie Mercury", "مغنٍ", "Singer", "Freddie Mercury", ["male", "deceased", "real", "singer", "british", "famous"]),
    ("muhammad_ali", "محمد علي كلاي", "Muhammad Ali", "ملاكم", "Boxer", "Muhammad Ali", ["male", "deceased", "real", "athlete", "american", "famous"]),
    ("pele", "بيليه", "Pelé", "كرة القدم", "Football", "Pelé", ["male", "deceased", "real", "athlete", "football", "brazilian", "famous"]),
    ("maradona", "دييغو مارادونا", "Diego Maradona", "كرة القدم", "Football", "Diego Maradona", ["male", "deceased", "real", "athlete", "football", "argentinian", "famous"]),
    ("ronaldinho", "رونالدينيو", "Ronaldinho", "كرة القدم", "Football", "Ronaldinho", ["male", "alive", "real", "athlete", "football", "brazilian", "famous"]),
    ("zidane", "زين الدين زيدان", "Zinedine Zidane", "كرة القدم", "Football", "Zinedine Zidane", ["male", "alive", "real", "athlete", "football", "french", "arab", "famous"]),
    ("benzema2", "كريم بنزيما", "Karim Benzema", "كرة القدم", "Football", "Karim Benzema", ["male", "alive", "real", "athlete", "football", "french", "arab", "famous"]),
    ("haaland", "إيرلينغ هالاند", "Erling Haaland", "كرة القدم", "Football", "Erling Haaland", ["male", "alive", "real", "athlete", "football", "norwegian", "famous"]),
    ("vinicius", "فينيسيوس جونيور", "Vinícius Júnior", "كرة القدم", "Football", "Vinicius Junior", ["male", "alive", "real", "athlete", "football", "brazilian", "famous"]),
    ("ronaldo_nazario", "رونالدو نازاريو", "Ronaldo Nazário", "كرة القدم", "Football", "Ronaldo Nazario", ["male", "alive", "real", "athlete", "football", "brazilian", "famous"]),
    ("abraham", "إبراهيموفيتش", "Zlatan Ibrahimović", "كرة القدم", "Football", "Zlatan Ibrahimovic", ["male", "alive", "real", "athlete", "football", "swedish", "famous"]),
    ("socrates", "سقراط", "Socrates", "فيلسوف", "Philosopher", "Socrates", ["male", "deceased", "real", "historical", "philosopher", "greek", "famous"]),
    ("plato", "أفلاطون", "Plato", "فيلسوف", "Philosopher", "Plato", ["male", "deceased", "real", "historical", "philosopher", "greek", "famous"]),
    ("aristotle", "أرسطو", "Aristotle", "فيلسوف", "Philosopher", "Aristotle", ["male", "deceased", "real", "historical", "philosopher", "greek", "famous"]),
    ("ibn_sina", "ابن سينا", "Avicenna", "عالم", "Scientist", "Avicenna", ["male", "deceased", "real", "historical", "scientist", "arab", "famous"]),
    ("ibn_khaldun", "ابن خلدون", "Ibn Khaldun", "مؤرخ", "Historian", "Ibn Khaldun", ["male", "deceased", "real", "historical", "scientist", "arab", "famous"]),
    ("ibn_battuta", "ابن بطوطة", "Ibn Battuta", "رحالة", "Explorer", "Ibn Battuta", ["male", "deceased", "real", "historical", "arab", "famous"]),
    ("al_khwarizmi", "الخوارزمي", "Muhammad ibn Musa al-Khwarizmi", "عالم", "Scientist", "Al-Khwarizmi", ["male", "deceased", "real", "historical", "scientist", "arab", "famous"]),
    ("musa", "موسى عليه السلام", "Moses", "شخصية دينية وتاريخية", "Religious and historical figure", "Moses", ["male", "deceased", "real", "historical", "religious", "famous"]),
    ("cleveland", "كليفلاند براون", "Cleveland Brown", "شخصية كرتونية", "Animated character", "Cleveland Brown", ["male", "fictional", "cartoon", "american", "famous"]),
    ("homer_simpson", "هومر سيمبسون", "Homer Simpson", "شخصية كرتونية", "Animated character", "Homer Simpson", ["male", "fictional", "cartoon", "american", "famous"]),
    ("spongebob", "سبونج بوب", "SpongeBob SquarePants", "شخصية كرتونية", "Animated character", "SpongeBob SquarePants", ["male", "fictional", "cartoon", "famous"]),
    ("tom_cat", "توم", "Tom Cat", "شخصية كرتونية", "Animated character", "Tom and Jerry Tom Cat", ["male", "fictional", "cartoon", "famous"]),
    ("jerry_mouse", "جيري", "Jerry Mouse", "شخصية كرتونية", "Animated character", "Jerry Mouse", ["male", "fictional", "cartoon", "famous"]),
    ("shrek", "شريك", "Shrek", "شخصية خيالية", "Fictional character", "Shrek", ["male", "fictional", "cartoon", "ogre", "famous"]),
    ("elsa", "إلسا", "Elsa", "شخصية خيالية", "Fictional character", "Elsa (Frozen)", ["female", "fictional", "cartoon", "magic", "famous"]),
    ("pikachu", "بيكاتشو", "Pikachu", "بوكيمون", "Pokémon", "Pikachu", ["fictional", "anime", "pokemon", "electric", "famous"]),
    ("saitama", "سايتاما", "Saitama", "أنمي", "Anime", "Saitama (One-Punch Man)", ["male", "fictional", "anime", "superhero", "japanese", "famous"]),
    ("eren_yeager", "إيرين ييغر", "Eren Yeager", "أنمي", "Anime", "Eren Yeager", ["male", "fictional", "anime", "soldier", "japanese", "famous"]),
    ("gojo", "ساتورو غوجو", "Satoru Gojo", "أنمي", "Anime", "Satoru Gojo", ["male", "fictional", "anime", "magic", "japanese", "famous"]),
    ("sukuna", "ريومن سوكونا", "Ryomen Sukuna", "أنمي", "Anime", "Ryomen Sukuna", ["male", "fictional", "anime", "villain", "japanese", "famous"]),
    ("tanjiro", "تانجيرو كامادو", "Tanjiro Kamado", "أنمي", "Anime", "Tanjiro Kamado", ["male", "fictional", "anime", "swordsman", "japanese", "famous"]),
    ("nezuko", "نيزوكو كامادو", "Nezuko Kamado", "أنمي", "Anime", "Nezuko Kamado", ["female", "fictional", "anime", "japanese", "famous"]),
    ("ichigo", "إيتشيغو كوروساكي", "Ichigo Kurosaki", "أنمي", "Anime", "Ichigo Kurosaki", ["male", "fictional", "anime", "fighter", "japanese", "famous"]),
    ("l", "إل", "L (Death Note)", "أنمي", "Anime", "L (Death Note)", ["male", "fictional", "anime", "detective", "japanese", "famous"]),
    ("vegeta", "فيجيتا", "Vegeta", "أنمي", "Anime", "Vegeta", ["male", "fictional", "anime", "fighter", "alien", "japanese", "famous"]),
    ("itachi", "إيتاتشي أوتشيها", "Itachi Uchiha", "أنمي", "Anime", "Itachi Uchiha", ["male", "fictional", "anime", "ninja", "japanese", "famous"]),
    ("sasuke", "ساسكي أوتشيها", "Sasuke Uchiha", "أنمي", "Anime", "Sasuke Uchiha", ["male", "fictional", "anime", "ninja", "japanese", "famous"]),
    ("kakashi", "كاكاشي هاتاكي", "Kakashi Hatake", "أنمي", "Anime", "Kakashi Hatake", ["male", "fictional", "anime", "ninja", "japanese", "famous"]),
    ("thor", "ثور", "Thor", "مارفل", "Marvel", "Thor (Marvel Comics)", ["male", "fictional", "superhero", "marvel", "god", "famous"]),
    ("thanos", "ثانوس", "Thanos", "مارفل", "Marvel", "Thanos", ["male", "fictional", "villain", "marvel", "alien", "famous"]),
    ("joker", "الجوكر", "Joker", "دي سي", "DC", "Joker (character)", ["male", "fictional", "villain", "dc", "famous"]),
    ("wonder_woman", "وندر وومن", "Wonder Woman", "دي سي", "DC", "Wonder Woman", ["female", "fictional", "superhero", "dc", "famous"]),
    ("deadpool", "ديدبول", "Deadpool", "مارفل", "Marvel", "Deadpool", ["male", "fictional", "superhero", "marvel", "famous"]),
    ("wolverine", "وولفرين", "Wolverine", "مارفل", "Marvel", "Wolverine (character)", ["male", "fictional", "superhero", "marvel", "famous"]),
    ("harley_quinn", "هارلي كوين", "Harley Quinn", "دي سي", "DC", "Harley Quinn", ["female", "fictional", "villain", "dc", "famous"]),
    ("yoda", "يودا", "Yoda", "ستار وورز", "Star Wars", "Yoda", ["male", "fictional", "alien", "magic", "famous"]),
    ("darth_vader", "دارث فيدر", "Darth Vader", "ستار وورز", "Star Wars", "Darth Vader", ["male", "fictional", "villain", "magic", "famous"]),
    ("jack_sparrow", "جاك سبارو", "Jack Sparrow", "شخصية خيالية", "Fictional character", "Jack Sparrow", ["male", "fictional", "pirate", "famous"]),
    ("james_bond", "جيمس بوند", "James Bond", "شخصية خيالية", "Fictional character", "James Bond", ["male", "fictional", "spy", "british", "famous"]),
    ("wednesday_addams", "وينزداي آدامز", "Wednesday Addams", "شخصية خيالية", "Fictional character", "Wednesday Addams", ["female", "fictional", "actor", "famous"]),
    ("mr_bean", "مستر بين", "Mr. Bean", "شخصية كوميدية", "Comedy character", "Mr. Bean", ["male", "fictional", "british", "comedy", "famous"]),
    ("rowan_atkinson", "روان أتكينسون", "Rowan Atkinson", "ممثل", "Actor", "Rowan Atkinson", ["male", "alive", "real", "actor", "british", "famous"]),
    ("leonardo_dicaprio", "ليوناردو دي كابريو", "Leonardo DiCaprio", "ممثل", "Actor", "Leonardo DiCaprio", ["male", "alive", "real", "actor", "american", "famous"]),
    ("brad_pitt", "براد بيت", "Brad Pitt", "ممثل", "Actor", "Brad Pitt", ["male", "alive", "real", "actor", "american", "famous"]),
    ("angelina_jolie", "أنجلينا جولي", "Angelina Jolie", "ممثلة", "Actor", "Angelina Jolie", ["female", "alive", "real", "actor", "american", "famous"]),
    ("robert_downey", "روبرت داوني جونيور", "Robert Downey Jr.", "ممثل", "Actor", "Robert Downey Jr.", ["male", "alive", "real", "actor", "american", "famous"]),
    ("keanu_reeves", "كيانو ريفز", "Keanu Reeves", "ممثل", "Actor", "Keanu Reeves", ["male", "alive", "real", "actor", "canadian", "famous"]),
    ("zendaya", "زيندايا", "Zendaya", "ممثلة", "Actor", "Zendaya", ["female", "alive", "real", "actor", "american", "famous"]),
    ("rihanna", "ريهانا", "Rihanna", "مغنية", "Singer", "Rihanna", ["female", "alive", "real", "singer", "barbadian", "famous"]),
    ("eminem", "إيمينيم", "Eminem", "مغنٍ", "Singer", "Eminem", ["male", "alive", "real", "singer", "american", "famous"]),
    ("drake", "دريك", "Drake", "مغنٍ", "Singer", "Drake (musician)", ["male", "alive", "real", "singer", "canadian", "famous"]),
    ("billie_eilish", "بيلي إيليش", "Billie Eilish", "مغنية", "Singer", "Billie Eilish", ["female", "alive", "real", "singer", "american", "famous"]),
    ("elon_musk", "إيلون ماسك", "Elon Musk", "رجل أعمال", "Businessperson", "Elon Musk", ["male", "alive", "real", "businessperson", "american", "famous"]),
    ("steve_jobs", "ستيف جوبز", "Steve Jobs", "رجل أعمال", "Businessperson", "Steve Jobs", ["male", "deceased", "real", "historical", "businessperson", "american", "famous"]),
    ("bill_gates", "بيل غيتس", "Bill Gates", "رجل أعمال", "Businessperson", "Bill Gates", ["male", "alive", "real", "businessperson", "american", "famous"]),
    ("mark_zuckerberg", "مارك زوكربيرغ", "Mark Zuckerberg", "رجل أعمال", "Businessperson", "Mark Zuckerberg", ["male", "alive", "real", "businessperson", "american", "famous"]),
    ("albert_camoo", "ألبير كامو", "Albert Camus", "كاتب", "Writer", "Albert Camus", ["male", "deceased", "real", "historical", "writer", "french", "famous"]),
    ("shakespeare", "ويليام شكسبير", "William Shakespeare", "كاتب", "Writer", "William Shakespeare", ["male", "deceased", "real", "historical", "writer", "british", "famous"]),
    ("agatha_christie", "أغاثا كريستي", "Agatha Christie", "كاتبة", "Writer", "Agatha Christie", ["female", "deceased", "real", "historical", "writer", "british", "famous"]),
    ("sherlock_holmes", "شيرلوك هولمز", "Sherlock Holmes", "شخصية خيالية", "Fictional character", "Sherlock Holmes", ["male", "fictional", "detective", "british", "famous"]),
    ("gandhi", "المهاتما غاندي", "Mahatma Gandhi", "شخصية تاريخية", "Historical figure", "Mahatma Gandhi", ["male", "deceased", "real", "historical", "politician", "indian", "famous"]),
    ("mandela", "نيلسون مانديلا", "Nelson Mandela", "شخصية تاريخية", "Historical figure", "Nelson Mandela", ["male", "deceased", "real", "historical", "politician", "south_african", "famous"]),
    ("margaret_thatcher", "مارغريت تاتشر", "Margaret Thatcher", "شخصية سياسية", "Politics", "Margaret Thatcher", ["female", "deceased", "real", "historical", "politician", "british", "famous"]),
    ("napoleon_iii", "نابليون الثالث", "Napoleon III", "شخصية تاريخية", "Historical figure", "Napoleon III", ["male", "deceased", "real", "historical", "politician", "french", "famous"]),
    ("ksi", "كي إس آي", "KSI", "يوتيوبر", "YouTuber", "KSI", ["male", "alive", "real", "youtuber", "british", "rapper", "streamer", "gaming_creator", "famous"]),
    ("sidemen", "سايدمن", "Sidemen", "مجموعة يوتيوبرز", "YouTube group", "Sidemen", ["real", "youtuber", "british", "gaming_creator", "challenges", "famous"]),
    ("dream", "دريم", "Dream", "يوتيوبر", "YouTuber", "Dream Minecraft YouTuber", ["male", "alive", "real", "youtuber", "american", "gamer", "minecraft", "streamer", "famous"]),
    ("technoblade", "تكنوبليد", "Technoblade", "يوتيوبر", "YouTuber", "Technoblade", ["male", "deceased", "real", "youtuber", "american", "gamer", "minecraft", "famous"]),
    ("markiplier", "ماركيبلاير", "Markiplier", "يوتيوبر", "YouTuber", "Markiplier", ["male", "alive", "real", "youtuber", "american", "gamer", "horror_games", "famous"]),
    ("jacksepticeye", "جاك سيبتيك آي", "Jacksepticeye", "يوتيوبر", "YouTuber", "Jacksepticeye", ["male", "alive", "real", "youtuber", "irish", "gamer", "famous"]),
    ("ishowspeed", "آي شو سبيد", "IShowSpeed", "يوتيوبر", "YouTuber", "IShowSpeed", ["male", "alive", "real", "youtuber", "american", "streamer", "football", "famous"]),
    ("ninja_gamer", "نينجا", "Ninja", "يوتيوبر", "YouTuber", "Ninja streamer", ["male", "alive", "real", "youtuber", "american", "streamer", "gamer", "fortnite", "famous"]),
    ("l3b", "لعيب", "L3b", "يوتيوبر", "YouTuber", "L3b Saudi YouTuber", ["male", "alive", "real", "youtuber", "saudi", "arab", "gamer"]),
    ("d7oomy", "دحومي 999", "D7oomy 999", "يوتيوبر", "YouTuber", "D7oomy 999", ["male", "alive", "real", "youtuber", "saudi", "arab", "gamer", "gaming_creator"]),
    ("azoz", "عزيز الأحمد", "Aziz Al-Ahmad", "صانع محتوى", "Content creator", "Aziz Al-Ahmad", ["male", "deceased", "real", "arabic_creator", "saudi", "arab", "famous"]),
    ("abualrub", "أبو الرب", "Abu Al-Rub", "يوتيوبر", "YouTuber", "Abu Al-Rub", ["male", "alive", "real", "youtuber", "jordanian", "arab", "comedy", "reaction"]),
    ("noor_stars", "نور ستارز", "Noor Stars", "يوتيوبر", "YouTuber", "Noor Stars", ["female", "alive", "real", "youtuber", "iraqi", "arab", "beauty", "vlogger"]),
    ("anasala", "أنس وأصالة", "Anasala Family", "صنّاع محتوى", "Content creators", "Anasala Family", ["real", "youtuber", "arab", "vlogger", "family_content"]),
    ("lisa_blackpink", "ليسا", "Lisa", "مغنية", "Singer", "Lisa (rapper)", ["female", "alive", "real", "singer", "rapper", "thai", "korean", "famous"]),
    ("jungkook", "جونغكوك", "Jungkook", "مغنٍ", "Singer", "Jungkook", ["male", "alive", "real", "singer", "korean", "famous"]),
    ("bts_rm", "آر إم", "RM", "مغنٍ", "Singer", "RM (rapper)", ["male", "alive", "real", "singer", "rapper", "korean", "famous"]),
    ("jackson_wang", "جاكسون وانغ", "Jackson Wang", "مغنٍ", "Singer", "Jackson Wang", ["male", "alive", "real", "singer", "chinese", "famous"]),
    ("greta", "غريتا تونبرغ", "Greta Thunberg", "ناشطة", "Activist", "Greta Thunberg", ["female", "alive", "real", "activist", "swedish", "famous"]),
    ("zelenskyy", "فولوديمير زيلينسكي", "Volodymyr Zelenskyy", "شخصية سياسية", "Politics", "Volodymyr Zelenskyy", ["male", "alive", "real", "politician", "ukrainian", "president", "famous"]),
    ("macron", "إيمانويل ماكرون", "Emmanuel Macron", "شخصية سياسية", "Politics", "Emmanuel Macron", ["male", "alive", "real", "politician", "french", "president", "famous"]),
    ("biden", "جو بايدن", "Joe Biden", "شخصية سياسية", "Politics", "Joe Biden", ["male", "alive", "real", "politician", "american", "president", "famous"]),
    ("merkel", "أنغيلا ميركل", "Angela Merkel", "شخصية سياسية", "Politics", "Angela Merkel", ["female", "alive", "real", "politician", "german", "famous"]),
    ("mao", "ماو تسي تونغ", "Mao Zedong", "شخصية تاريخية", "Historical figure", "Mao Zedong", ["male", "deceased", "real", "historical", "politician", "chinese", "military", "famous"]),
    ("lenin", "فلاديمير لينين", "Vladimir Lenin", "شخصية تاريخية", "Historical figure", "Vladimir Lenin", ["male", "deceased", "real", "historical", "politician", "russian", "revolutionary", "famous"]),
    ("ataturk", "مصطفى كمال أتاتورك", "Mustafa Kemal Atatürk", "شخصية تاريخية", "Historical figure", "Mustafa Kemal Atatürk", ["male", "deceased", "real", "historical", "politician", "turkish", "military", "famous"]),
    ("frida_kahlo", "فريدا كاهلو", "Frida Kahlo", "فنانة", "Artist", "Frida Kahlo", ["female", "deceased", "real", "artist", "mexican", "famous"]),
    ("vincent_van_gogh", "فنسنت فان غوخ", "Vincent van Gogh", "فنان", "Artist", "Vincent van Gogh", ["male", "deceased", "real", "historical", "artist", "dutch", "famous"]),
    ("mozart", "موزارت", "Wolfgang Amadeus Mozart", "موسيقي", "Musician", "Wolfgang Amadeus Mozart", ["male", "deceased", "real", "historical", "musician", "austrian", "famous"]),
    ("beethoven", "بيتهوفن", "Ludwig van Beethoven", "موسيقي", "Musician", "Ludwig van Beethoven", ["male", "deceased", "real", "historical", "musician", "german", "famous"]),
    ("marie_curie", "ماري كوري", "Marie Curie", "عالمة", "Scientist", "Marie Curie", ["female", "deceased", "real", "historical", "scientist", "polish", "french", "nobel", "famous"]),
    ("ada_lovelace", "آدا لوفلايس", "Ada Lovelace", "عالمة رياضيات", "Scientist", "Ada Lovelace", ["female", "deceased", "real", "historical", "scientist", "mathematician", "british", "famous"]),
    ("alan_turing", "آلان تورنغ", "Alan Turing", "عالم رياضيات", "Scientist", "Alan Turing", ["male", "deceased", "real", "historical", "scientist", "mathematician", "british", "famous"]),
    ("galileo", "غاليليو غاليلي", "Galileo Galilei", "عالم", "Scientist", "Galileo Galilei", ["male", "deceased", "real", "historical", "scientist", "italian", "astronomer", "famous"]),
    ("darwin", "تشارلز داروين", "Charles Darwin", "عالم", "Scientist", "Charles Darwin", ["male", "deceased", "real", "historical", "scientist", "british", "famous"]),
    ("suleiman", "سليمان القانوني", "Suleiman the Magnificent", "شخصية تاريخية", "Historical figure", "Suleiman the Magnificent", ["male", "deceased", "real", "historical", "royal", "turkish", "military", "famous"]),
    ("ibn_battuta_extra", "ابن بطوطة", "Ibn Battuta", "رحالة", "Explorer", "Ibn Battuta", ["male", "deceased", "real", "historical", "arab", "explorer", "famous"]),
    ("kakuzu", "كاكوزو", "Kakuzu", "أنمي", "Anime", "Kakuzu Naruto", ["male", "fictional", "anime", "ninja", "villain", "japanese", "famous"]),
    ("madara", "مادارا أوتشيها", "Madara Uchiha", "أنمي", "Anime", "Madara Uchiha", ["male", "fictional", "anime", "ninja", "villain", "japanese", "has_powers", "famous"]),
    ("obito", "أوبيتو أوتشيها", "Obito Uchiha", "أنمي", "Anime", "Obito Uchiha", ["male", "fictional", "anime", "ninja", "villain", "japanese", "has_powers", "famous"]),
    ("minato", "ميناتو ناميكازي", "Minato Namikaze", "أنمي", "Anime", "Minato Namikaze", ["male", "fictional", "anime", "ninja", "japanese", "has_powers", "famous"]),
    ("shanks", "شانكس", "Shanks One Piece", "أنمي", "Anime", "Shanks One Piece", ["male", "fictional", "anime", "pirate", "japanese", "uses_sword", "has_powers", "famous"]),
    ("law_onepiece", "ترافالغار لاو", "Trafalgar Law", "أنمي", "Anime", "Trafalgar D. Water Law", ["male", "fictional", "anime", "pirate", "doctor", "japanese", "has_powers", "famous"]),
    ("sanji", "سانجي", "Sanji", "أنمي", "Anime", "Sanji One Piece", ["male", "fictional", "anime", "pirate", "fighter", "japanese", "famous"]),
    ("ace_onepiece", "بورتغاس دي إيس", "Portgas D. Ace", "أنمي", "Anime", "Portgas D. Ace", ["male", "fictional", "anime", "pirate", "japanese", "has_powers", "famous"]),
    ("denji", "دينجي", "Denji", "أنمي", "Anime", "Denji Chainsaw Man", ["male", "fictional", "anime", "japanese", "has_powers", "main_character", "famous"]),
    ("power_chainsaw", "باور", "Power", "أنمي", "Anime", "Power Chainsaw Man", ["female", "fictional", "anime", "japanese", "has_powers", "famous"]),
    ("makima", "ماكيما", "Makima", "أنمي", "Anime", "Makima Chainsaw Man", ["female", "fictional", "anime", "japanese", "villain", "has_powers", "famous"]),
    ("frieren", "فريرين", "Frieren", "أنمي", "Anime", "Frieren", ["female", "fictional", "anime", "wizard", "has_powers", "famous"]),
    ("anya_forger", "أنيا فورجر", "Anya Forger", "أنمي", "Anime", "Anya Forger", ["female", "fictional", "anime", "student", "has_powers", "famous"]),
    ("nezuko_extra", "نيزوكو كامادو", "Nezuko Kamado", "أنمي", "Anime", "Nezuko Kamado", ["female", "fictional", "anime", "japanese", "has_powers", "famous"]),
    ("sung_jinwoo", "سونغ جين وو", "Sung Jinwoo", "أنمي", "Anime", "Sung Jinwoo", ["male", "fictional", "anime", "has_powers", "main_character", "famous"]),
    ("rimuru", "ريمورو تيمبيست", "Rimuru Tempest", "أنمي", "Anime", "Rimuru Tempest", ["male", "fictional", "anime", "has_powers", "main_character", "famous"]),
    ("loid_forger", "لويد فورجر", "Loid Forger", "أنمي", "Anime", "Loid Forger", ["male", "fictional", "anime", "spy", "japanese", "famous"]),
    ("yor_forger", "يور فورجر", "Yor Forger", "أنمي", "Anime", "Yor Forger", ["female", "fictional", "anime", "spy", "japanese", "uses_sword", "famous"]),
    ("sailor_moon", "سيلور مون", "Sailor Moon", "أنمي", "Anime", "Sailor Moon", ["female", "fictional", "anime", "japanese", "has_powers", "main_character", "famous"]),
    ("ash_ketchum", "آش كيتشام", "Ash Ketchum", "أنمي", "Anime", "Ash Ketchum", ["male", "fictional", "anime", "pokemon", "japanese", "main_character", "famous"]),
    ("lightning_mcqueen", "ماكوين", "Lightning McQueen", "شخصية كرتونية", "Animated character", "Lightning McQueen", ["male", "fictional", "cartoon", "from_movie", "famous"]),
    ("po_kung_fu_panda", "بو", "Po Kung Fu Panda", "شخصية كرتونية", "Animated character", "Po Kung Fu Panda", ["male", "fictional", "cartoon", "fighter", "from_movie", "famous"]),
    ("mulan", "مولان", "Mulan", "شخصية خيالية", "Fictional character", "Mulan Disney", ["female", "fictional", "cartoon", "soldier", "warrior", "from_movie", "famous"]),
    ("moana", "موانا", "Moana", "شخصية خيالية", "Fictional character", "Moana Disney", ["female", "fictional", "cartoon", "main_character", "from_movie", "famous"]),
    ("donald_duck", "بطوط", "Donald Duck", "شخصية كرتونية", "Animated character", "Donald Duck", ["male", "fictional", "cartoon", "famous"]),
    ("bugs_bunny", "باغز باني", "Bugs Bunny", "شخصية كرتونية", "Animated character", "Bugs Bunny", ["male", "fictional", "cartoon", "famous"]),
    ("scooby_doo", "سكوبي دو", "Scooby-Doo", "شخصية كرتونية", "Animated character", "Scooby-Doo", ["male", "fictional", "cartoon", "detective", "famous"]),
]

QUESTION_BANK = [
    ("male", "هل الشخصية رجل؟", "Is the character male?"),
    ("female", "هل الشخصية امرأة؟", "Is the character female?"),
    ("alive", "هل الشخصية على قيد الحياة؟", "Is the character alive?"),
    ("deceased", "هل الشخصية متوفاة؟", "Is the character deceased?"),
    ("real", "هل هي شخصية حقيقية؟", "Is this a real person?"),
    ("fictional", "هل هي شخصية خيالية؟", "Is the character fictional?"),
    ("saudi", "هل هو من السعودية؟", "Is the character from Saudi Arabia?"),
    ("arab", "هل هو عربي؟", "Is the character Arab?"),
    ("american", "هل هو أمريكي؟", "Is the character American?"),
    ("british", "هل هو بريطاني؟", "Is the character British?"),
    ("egyptian", "هل هو مصري؟", "Is the character Egyptian?"),
    ("football", "هل له علاقة بكرة القدم؟", "Is the character related to football/soccer?"),
    ("athlete", "هل هو رياضي؟", "Is the character an athlete?"),
    ("youtuber", "هل هو يوتيوبر أو صانع محتوى؟", "Is the character a YouTuber or content creator?"),
    ("singer", "هل هو مغنٍ أو مغنية؟", "Is the character a singer?"),
    ("actor", "هل هو ممثل أو ممثلة؟", "Is the character an actor?"),
    ("politician", "هل هو شخصية سياسية؟", "Is the character a politician?"),
    ("military", "هل هو شخصية عسكرية؟", "Is the character a military figure?"),
    ("anime", "هل الشخصية من الأنمي؟", "Is the character from anime?"),
    ("cartoon", "هل الشخصية كرتونية؟", "Is the character a cartoon character?"),
    ("superhero", "هل هو بطل خارق؟", "Is the character a superhero?"),
    ("marvel", "هل ينتمي إلى عالم مارفل؟", "Is the character from Marvel?"),
    ("dc", "هل ينتمي إلى عالم دي سي؟", "Is the character from DC?"),
    ("historical", "هل هي شخصية تاريخية؟", "Is the character historical?"),
    ("royal", "هل له علاقة بالعائلة الملكية؟", "Is the character royalty or related to a royal family?"),
    ("scientist", "هل هو عالم؟", "Is the character a scientist?"),
    ("detective", "هل هو محقق؟", "Is the character a detective?"),
    ("ninja", "هل هو نينجا؟", "Is the character a ninja?"),
    ("pirate", "هل هو قرصان؟", "Is the character a pirate?"),
    ("soldier", "هل هو جندي؟", "Is the character a soldier?"),
    ("wizard", "هل يستخدم السحر؟", "Does the character use magic?"),
    ("villain", "هل هو شرير؟", "Is the character a villain?"),
    ("businessperson", "هل هو رجل أعمال؟", "Is the character a businessperson?"),
    ("writer", "هل هو كاتب أو مؤلف؟", "Is the character a writer?"),
    ("philosopher", "هل هو فيلسوف؟", "Is the character a philosopher?"),
    ("religious", "هل هو شخصية دينية؟", "Is the character a religious figure?"),
    ("royal", "هل هو ملك أو أمير؟", "Is the character a monarch or prince?"),
    ("alien", "هل الشخصية من كوكب آخر؟", "Is the character extraterrestrial?"),
    ("student", "هل الشخصية طالب؟", "Is the character a student?"),
    ("spy", "هل هو جاسوس؟", "Is the character a spy?"),
    ("god", "هل يُصوَّر كإله أو كائن خارق؟", "Is the character depicted as a god or supernatural being?"),
    ("historical", "هل عاش قبل القرن العشرين؟", "Did the character live before the 20th century?"),
    ("japanese", "هل هو ياباني؟", "Is the character Japanese?"),
    ("russian", "هل هو روسي؟", "Is the character Russian?"),
    ("german", "هل هو ألماني؟", "Is the character German?"),
    ("french", "هل هو فرنسي؟", "Is the character French?"),
    ("korean", "هل هو كوري؟", "Is the character Korean?"),
    ("chinese", "هل هو صيني؟", "Is the character Chinese?"),
    ("indian", "هل هو هندي؟", "Is the character Indian?"),
    ("brazilian", "هل هو برازيلي؟", "Is the character Brazilian?"),
    ("portuguese", "هل هو برتغالي؟", "Is the character Portuguese?"),
    ("argentinian", "هل هو أرجنتيني؟", "Is the character Argentinian?"),
    ("spanish", "هل هو إسباني؟", "Is the character Spanish?"),
    ("italian", "هل هو إيطالي؟", "Is the character Italian?"),
    ("canadian", "هل هو كندي؟", "Is the character Canadian?"),
    ("swedish", "هل هو سويدي؟", "Is the character Swedish?"),
    ("turkish", "هل هو تركي؟", "Is the character Turkish?"),
    ("pakistani", "هل هو باكستاني؟", "Is the character Pakistani?"),
    ("iraqi", "هل هو عراقي؟", "Is the character Iraqi?"),
    ("kuwaiti", "هل هو كويتي؟", "Is the character Kuwaiti?"),
    ("jordanian", "هل هو أردني؟", "Is the character Jordanian?"),
    ("syrian", "هل هو سوري؟", "Is the character Syrian?"),
    ("lebanese", "هل هو لبناني؟", "Is the character Lebanese?"),
    ("moroccan", "هل هو مغربي؟", "Is the character Moroccan?"),
    ("tunisian", "هل هو تونسي؟", "Is the character Tunisian?"),
    ("yemeni", "هل هو يمني؟", "Is the character Yemeni?"),
    ("qatari", "هل هو قطري؟", "Is the character Qatari?"),
    ("emirati", "هل هو إماراتي؟", "Is the character Emirati?"),
    ("colombian", "هل هو كولومبي؟", "Is the character Colombian?"),
    ("serbian", "هل هو صربي؟", "Is the character Serbian?"),
    ("gamer", "هل محتواه الأساسي ألعاب؟", "Is their main content gaming?"),
    ("streamer", "هل هو ستريمر أو يبث مباشر؟", "Is the character a streamer?"),
    ("esports_clan", "هل ينتمي إلى كلان أو فريق ألعاب معروف؟", "Is the character part of a known gaming clan or team?"),
    ("gaming_creator", "هل اشتهر بمقاطع التحديات والألعاب؟", "Are they known for gaming and challenge videos?"),
    ("arabic_creator", "هل هو صانع محتوى عربي؟", "Is the character an Arabic-speaking content creator?"),
    ("minecraft", "هل يشتهر بمحتوى ماينكرافت؟", "Are they known for Minecraft content?"),
    ("roblox", "هل يشتهر بمحتوى روبلوكس؟", "Are they known for Roblox content?"),
    ("football_gamer", "هل محتواه عن ألعاب كرة القدم؟", "Do they create football video game content?"),
    ("actor", "هل اشتهر بأفلام هوليوود؟", "Is the character known for Hollywood films?"),
    ("rapper", "هل هو مغني راب؟", "Is the character a rapper?"),
    ("streaming_platform", "هل اشتهر على تويتش أو منصة بث؟", "Did the character become famous on Twitch or a streaming platform?"),
    ("falcons", "هل ينتمي إلى فريق فالكونز؟", "Are they part of Team Falcons?"),
    ("powr", "هل ينتمي إلى فريق باور؟", "Are they part of Team POWR?"),
    ("3am", "هل ينتمي إلى كلان ثري إم؟", "Are they part of 3AM?"),
    ("r8", "هل ينتمي إلى فريق آر 8؟", "Are they part of Team R8?"),
    ("minecraft", "هل يشتهر بماينكرافت؟", "Are they known for Minecraft?"),
    ("roblox", "هل يشتهر بروبلوكس؟", "Are they known for Roblox?"),
    ("fortnite", "هل يشتهر بفورتنايت؟", "Are they known for Fortnite?"),
    ("fifa", "هل يشتهر بألعاب فيفا أو إي إيه إف سي؟", "Are they known for FIFA or EA Sports FC?"),
    ("challenges", "هل يشتهر بالتحديات؟", "Are they known for challenges?"),
    ("reaction", "هل يقدم محتوى ردة فعل؟", "Do they make reaction content?"),
    ("vlogger", "هل يقدم فلوقات ويوميات؟", "Do they make vlogs?"),
    ("prank", "هل يشتهر بالمقالب؟", "Are they known for pranks?"),
    ("comedy", "هل محتواه كوميدي؟", "Is their content mainly comedy?"),
    ("tech", "هل يقدم محتوى تقني؟", "Do they make technology content?"),
    ("travel", "هل يشتهر بمحتوى السفر؟", "Are they known for travel content?"),
    ("food", "هل يقدم محتوى طبخ أو أكل؟", "Do they make food content?"),
    ("beauty", "هل محتواه عن الجمال أو المكياج؟", "Is their content about beauty or makeup?"),
    ("education", "هل يقدم محتوى تعليمي؟", "Do they make educational content?"),
    ("podcaster", "هل يقدم بودكاست؟", "Do they host a podcast?"),
    ("rapper", "هل هو مغني راب؟", "Are they a rapper?"),
    ("producer", "هل هو منتج موسيقي؟", "Are they a music producer?"),
    ("basketball", "هل له علاقة بكرة السلة؟", "Are they related to basketball?"),
    ("boxing", "هل هو ملاكم؟", "Are they a boxer?"),
    ("racing", "هل له علاقة بسباقات السيارات؟", "Are they related to car racing?"),
    ("tennis", "هل يلعب التنس؟", "Do they play tennis?"),
    ("olympic", "هل شارك في الألعاب الأولمبية؟", "Did they compete in the Olympics?"),
    ("nobel", "هل حصل على جائزة نوبل؟", "Did they win a Nobel Prize?"),
    ("inventor", "هل هو مخترع؟", "Are they an inventor?"),
    ("mathematician", "هل هو عالم رياضيات؟", "Are they a mathematician?"),
    ("doctor", "هل هو طبيب؟", "Are they a doctor?"),
    ("king", "هل كان ملكًا؟", "Were they a king?"),
    ("queen", "هل كانت ملكة؟", "Were they a queen?"),
    ("president", "هل كان رئيس دولة؟", "Were they a head of state?"),
    ("revolutionary", "هل ارتبط اسمه بثورة أو حركة ثورية؟", "Were they associated with a revolution?"),
    ("warrior", "هل اشتهر كمحارب؟", "Were they known as a warrior?"),
    ("ancient", "هل عاش في العصور القديمة؟", "Did they live in ancient times?"),
    ("medieval", "هل عاش في العصور الوسطى؟", "Did they live in the Middle Ages?"),
    ("twentieth_century", "هل عاش في القرن العشرين؟", "Did they live in the 20th century?"),
    ("black_hair", "هل شعره أسود غالبًا؟", "Does the character usually have black hair?"),
    ("white_hair", "هل شعره أبيض أو فضي؟", "Does the character have white or silver hair?"),
    ("wears_glasses", "هل يرتدي نظارات؟", "Does the character wear glasses?"),
    ("wears_hat", "هل يرتدي قبعة أو خوذة مميزة؟", "Does the character wear a distinctive hat or helmet?"),
    ("uses_sword", "هل يستخدم السيف؟", "Does the character use a sword?"),
    ("has_powers", "هل يمتلك قوى خارقة؟", "Does the character have superpowers?"),
    ("main_character", "هل هو الشخصية الرئيسية في عمله؟", "Are they the main character in their story?"),
    ("villain", "هل هو الشرير الأساسي؟", "Are they a main villain?"),
    ("from_japan", "هل ظهرت الشخصية أول مرة في اليابان؟", "Did the character first appear in Japan?"),
    ("from_game", "هل الشخصية من لعبة فيديو؟", "Is the character from a video game?"),
    ("from_movie", "هل اشتهر من خلال الأفلام؟", "Is the character known mainly from movies?"),
    ("from_tv", "هل اشتهر من خلال مسلسل تلفزيوني؟", "Is the character known mainly from a TV series?"),
    ("from_comics", "هل الشخصية من القصص المصورة؟", "Is the character from comics?"),
    ("family", "هل الشخصية من عائلتك؟", "Is the character in your family?"),
    ("close_relation", "هل الشخصية من أقرب الناس لك؟", "Are they one of your closest relatives?"),
    ("direct_contact", "هل تتواصل مع الشخصية مباشرة؟", "Do you communicate with this person directly?"),
    ("maternal_side", "هل هي من جهة أمك؟", "Are they on your mother's side?"),
    ("paternal_side", "هل هي من جهة أبوك؟", "Are they on your father's side?"),
    ("same_household", "هل تعيشون في نفس البيت؟", "Do you live in the same household?"),
    ("has_children", "هل الشخصية عندها عيال؟", "Does this person have children?"),
    ("self", "هل الشخصية هي أنت؟", "Is the character you?"),
    ("mother", "هل الشخصية أمك؟", "Is the person your mother?"),
    ("father", "هل الشخصية أبوك؟", "Is the person your father?"),
    ("sibling", "هل الشخصية أخ أو أخت لك؟", "Is the person your sibling?"),
    ("parent", "هل الشخصية أحد والديك؟", "Is the person one of your parents?"),
    ("grandparent", "هل الشخصية جد أو جدة لك؟", "Is the person your grandparent?"),
    ("aunt_uncle", "هل الشخصية عم أو عمة أو خال أو خالة؟", "Is the person your aunt or uncle?"),
    ("cousin", "هل الشخصية ابن أو بنت عم أو خال؟", "Is the person your cousin?"),
    ("spouse", "هل الشخصية زوجك أو زوجتك؟", "Is the person your spouse?"),
    ("son", "هل الشخصية ابنك؟", "Is the person your son?"),
    ("daughter", "هل الشخصية بنتك؟", "Is the person your daughter?"),
    ("irish", "هل هو أيرلندي؟", "Is the character Irish?"),
    ("ukrainian", "هل هو أوكراني؟", "Is the character Ukrainian?"),
    ("mexican", "هل هو مكسيكي؟", "Is the character Mexican?"),
    ("dutch", "هل هو هولندي؟", "Is the character Dutch?"),
    ("austrian", "هل هو نمساوي؟", "Is the character Austrian?"),
    ("polish", "هل هو بولندي؟", "Is the character Polish?"),
    ("thai", "هل هو تايلندي؟", "Is the character Thai?"),
    ("activist", "هل هو ناشط أو ناشطة؟", "Is the character an activist?"),
    ("artist", "هل هو فنان أو فنانة؟", "Is the character an artist?"),
    ("musician", "هل هو موسيقي؟", "Is the character a musician?"),
    ("astronomer", "هل هو عالم فلك؟", "Is the character an astronomer?"),
    ("explorer", "هل هو رحالة أو مستكشف؟", "Is the character an explorer?"),
    ("horror_games", "هل اشتهر بألعاب الرعب؟", "Are they known for horror games?"),
    ("family_content", "هل محتواه عن العائلة واليوميات؟", "Is their content about family and daily life?"),

]

ANSWERS = {
    "ar": [("yes", "ايه"), ("no", "لا"), ("unknown", "مدري"), ("probably_no", "يمكن لا"), ("probably_yes", "يمكن")],
    "en": [("yes", "Yes"), ("no", "No"), ("unknown", "Don't know"), ("probably_no", "Probably not"), ("probably_yes", "Probably")],
}

TEXT = {
    "ar": {
        "intro": "بوو 👻\nانا ديمون 🧛🏻‍♀️ اقدر اعرف مين الشخصية الي فبالك!\n\n- فكر بشخص واضغط لغتك وجاوب على اسئلتي",
        "thinking": "خلني أفكر شوي... 🧠",
        "guess": "أتوقع أن الشخصية اللي في بالك هي:\n\n**{name}**\nالفئة: {category}\n\nهل هذا هو الشخص؟",
        "correct": "كنت عارف! 👻✨\nطلعت الشخصية اللي في بالك هي **{name}**",
        "wrong": "تمام، خلني أجرب تخمين ثاني...",
        "none": "ما قدرت أوصل للشخصية بثقة 😅\nجرّب مرة ثانية وفكر بشخصية أوضح أو معروفة أكثر.",
        "question": "السؤال {n}: {question}",
        "start_private": "افتح ديمون نواف في الخاص 👻",
        "language": "اختر لغتك / Choose your language",
        "photo_error": "ما لقيت صورة مناسبة للشخصية، لكن هذا تخميني!",
    },
    "en": {
        "intro": "Boo! 👻\nI'm Demon 🧛🏻‍♀️ and I can guess the character you're thinking of!\n\n- Think of someone, choose your language, and answer my questions.",
        "thinking": "Let me think... 🧠",
        "guess": "I think the character in your mind is:\n\n**{name}**\nCategory: {category}\n\nIs this your character?",
        "correct": "I knew it! 👻✨\nThe character you had in mind was **{name}**.",
        "wrong": "Okay, let me try another guess...",
        "none": "I couldn't identify the character confidently. 😅\nTry again with a more recognizable character.",
        "question": "Question {n}: {question}",
        "start_private": "Open Demon Nawaf in private 👻",
        "language": "Choose your language / اختر لغتك",
        "photo_error": "I couldn't find a suitable image, but this is my guess!",
    },
}



def _sql_placeholders(sql):
    parts = sql.split("?")
    return "".join(part + ("$" + str(i + 1) if i < len(parts) - 1 else "") for i, part in enumerate(parts))


async def _db_execute(sql, params=(), fetch=None):
    pool = get_pool()
    query = _sql_placeholders(sql)
    async with pool.acquire() as conn:
        if fetch == "all":
            return await conn.fetch(query, *params)
        if fetch == "one":
            return await conn.fetchrow(query, *params)
        return await conn.execute(query, *params)


async def ensure_demon_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS demon_nawaf_characters (
                    slug TEXT PRIMARY KEY, name_ar TEXT NOT NULL, name_en TEXT NOT NULL,
                    category_ar TEXT NOT NULL DEFAULT 'شخصية',
                    category_en TEXT NOT NULL DEFAULT 'Character',
                    wiki_title TEXT NOT NULL DEFAULT '', traits TEXT NOT NULL DEFAULT '[]',
                    image_url TEXT NOT NULL DEFAULT '', summary_ar TEXT NOT NULL DEFAULT '',
                    summary_en TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'seed',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS demon_nawaf_sessions (
                    user_id BIGINT NOT NULL, chat_id BIGINT NOT NULL,
                    lang TEXT NOT NULL DEFAULT 'ar', state TEXT NOT NULL DEFAULT 'language',
                    answers TEXT NOT NULL DEFAULT '{}', asked TEXT NOT NULL DEFAULT '[]',
                    excluded TEXT NOT NULL DEFAULT '[]', guesses TEXT NOT NULL DEFAULT '[]',
                    question_count INTEGER NOT NULL DEFAULT 0,
                    current_question TEXT NOT NULL DEFAULT '', last_rejected_at INTEGER,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_demon_nawaf_session_state ON demon_nawaf_sessions(state)")
            seed_rows = [
                (slug, ar, en, cat_ar, cat_en, wiki, json.dumps(traits, ensure_ascii=False))
                for slug, ar, en, cat_ar, cat_en, wiki, traits in SEED_CHARACTERS
            ]
            await conn.executemany("""
                INSERT INTO demon_nawaf_characters
                (slug,name_ar,name_en,category_ar,category_en,wiki_title,traits,source)
                VALUES($1,$2,$3,$4,$5,$6,$7,'seed')
                ON CONFLICT (slug) DO UPDATE SET
                    name_ar=EXCLUDED.name_ar, name_en=EXCLUDED.name_en,
                    category_ar=EXCLUDED.category_ar, category_en=EXCLUDED.category_en,
                    wiki_title=EXCLUDED.wiki_title, traits=EXCLUDED.traits
            """, seed_rows)


async def _load_session(user_id, chat_id):
    row = await _db_execute(
        "SELECT lang,state,answers,asked,excluded,guesses,question_count,current_question,last_rejected_at FROM demon_nawaf_sessions WHERE user_id=? AND chat_id=?",
        (user_id, chat_id), "one"
    )
    if not row:
        return None
    def parse(value, default):
        try:
            return json.loads(value or "")
        except (TypeError, ValueError):
            return default
    return {
        "lang": row["lang"], "state": row["state"],
        "answers": parse(row["answers"], {}), "asked": parse(row["asked"], []),
        "excluded": parse(row["excluded"], []), "guesses": parse(row["guesses"], []),
        "question_count": int(row["question_count"] or 0),
        "current_question": row["current_question"] or "",
        "last_rejected_at": row["last_rejected_at"],
    }


async def _save_session(user_id, chat_id, s):
    await _db_execute("""
        INSERT INTO demon_nawaf_sessions
        (user_id,chat_id,lang,state,answers,asked,excluded,guesses,question_count,current_question,last_rejected_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,NOW())
        ON CONFLICT (user_id,chat_id) DO UPDATE SET
            lang=EXCLUDED.lang,state=EXCLUDED.state,answers=EXCLUDED.answers,
            asked=EXCLUDED.asked,excluded=EXCLUDED.excluded,guesses=EXCLUDED.guesses,
            question_count=EXCLUDED.question_count,current_question=EXCLUDED.current_question,
            last_rejected_at=EXCLUDED.last_rejected_at,updated_at=NOW()
    """, (user_id, chat_id, s["lang"], s["state"], json.dumps(s["answers"], ensure_ascii=False),
          json.dumps(s["asked"], ensure_ascii=False), json.dumps(s["excluded"], ensure_ascii=False),
          json.dumps(s["guesses"], ensure_ascii=False), s["question_count"],
          s.get("current_question", ""), s.get("last_rejected_at")))


async def _delete_session(user_id, chat_id):
    await _db_execute("DELETE FROM demon_nawaf_sessions WHERE user_id=? AND chat_id=?", (user_id, chat_id))


async def _get_characters():
    rows = await _db_execute(
        "SELECT slug,name_ar,name_en,category_ar,category_en,wiki_title,traits,image_url,summary_ar,summary_en FROM demon_nawaf_characters",
        (), "all"
    ) or []
    result = []
    for row in rows:
        try:
            traits = set(json.loads(row["traits"] or "[]"))
        except (TypeError, ValueError):
            traits = set()
        result.append({
            "slug": row["slug"], "name_ar": row["name_ar"], "name_en": row["name_en"],
            "category_ar": row["category_ar"], "category_en": row["category_en"],
            "wiki_title": row["wiki_title"], "traits": traits,
            "image_url": row["image_url"] or "", "summary_ar": row["summary_ar"] or "",
            "summary_en": row["summary_en"] or "",
        })
    return result


def _family_candidates():
    """مرشحون افتراضيون للأقارب؛ لا تُعرض إلا بعد إجابة اللاعب أن الشخصية من عائلته."""
    rows = [
        ("family_self", "أنت", "You", ["family", "real", "self", "close_relation", "direct_contact", "same_household"]),
        ("family_mother", "أمك", "Your mother", ["family", "real", "female", "close_relation", "direct_contact", "maternal_side", "parent", "mother", "has_children", "same_household"]),
        ("family_father", "أبوك", "Your father", ["family", "real", "male", "close_relation", "direct_contact", "paternal_side", "parent", "father", "has_children", "same_household"]),
        ("family_sister", "أختك", "Your sister", ["family", "real", "female", "close_relation", "direct_contact", "sibling", "same_household"]),
        ("family_brother", "أخوك", "Your brother", ["family", "real", "male", "close_relation", "direct_contact", "sibling", "same_household"]),
        ("family_son", "ابنك", "Your son", ["family", "real", "male", "direct_contact", "son"]),
        ("family_daughter", "بنتك", "Your daughter", ["family", "real", "female", "direct_contact", "daughter"]),
        ("family_maternal_grandmother", "جدتك من جهة أمك", "Your maternal grandmother", ["family", "real", "female", "maternal_side", "grandparent"]),
        ("family_maternal_grandfather", "جدك من جهة أمك", "Your maternal grandfather", ["family", "real", "male", "maternal_side", "grandparent"]),
        ("family_paternal_grandmother", "جدتك من جهة أبوك", "Your paternal grandmother", ["family", "real", "female", "paternal_side", "grandparent"]),
        ("family_paternal_grandfather", "جدك من جهة أبوك", "Your paternal grandfather", ["family", "real", "male", "paternal_side", "grandparent"]),
        ("family_maternal_aunt", "خالتك", "Your maternal aunt", ["family", "real", "female", "maternal_side", "aunt_uncle"]),
        ("family_maternal_uncle", "خالك", "Your maternal uncle", ["family", "real", "male", "maternal_side", "aunt_uncle"]),
        ("family_paternal_aunt", "عمتك", "Your paternal aunt", ["family", "real", "female", "paternal_side", "aunt_uncle"]),
        ("family_paternal_uncle", "عمك", "Your paternal uncle", ["family", "real", "male", "paternal_side", "aunt_uncle"]),
        ("family_maternal_cousin", "قريبك من جهة أمك", "Your cousin on your mother's side", ["family", "real", "maternal_side", "cousin"]),
        ("family_paternal_cousin", "قريبك من جهة أبوك", "Your cousin on your father's side", ["family", "real", "paternal_side", "cousin"]),
        ("family_spouse", "زوجك أو زوجتك", "Your spouse", ["family", "real", "close_relation", "direct_contact", "spouse"]),
    ]
    return [{"slug": slug, "name_ar": ar, "name_en": en,
             "category_ar": "من عائلتك", "category_en": "Your family",
             "wiki_title": "", "traits": set(traits), "image_url": "",
             "summary_ar": "", "summary_en": ""} for slug, ar, en, traits in rows]


async def _characters_for_answers(answers):
    # نضيف خيارات الأقارب لحساب فائدة سؤال "هل هو من عائلتك؟"، لكن
    # _rank_characters لا يسمح بتخمين قريب إلا إذا أجاب اللاعب بنعم على family.
    return await _get_characters() + _family_candidates()


def _likelihood(answer, has_trait):
    # احتمالات بسيطة تسمح بإجابات غير قطعية من دون حذف الشخصية مباشرة.
    return {"yes": 0.94 if has_trait else 0.06,
            "no": 0.06 if has_trait else 0.94,
            "probably_yes": 0.72 if has_trait else 0.28,
            "probably_no": 0.28 if has_trait else 0.72,
            "unknown": 1.0}.get(answer, 1.0)


def _infer_answers(answers):
    """استنتاج الحقائق الواضحة حتى لا نكرر سؤالًا يناقض إجابة سابقة."""
    effective = dict(answers)
    implications = {
        "alive": {"deceased": "no"},
        "deceased": {"alive": "no"},
        "real": {"fictional": "no", "anime": "no", "cartoon": "no"},
        "fictional": {"real": "no", "family": "no"},
        "anime": {"fictional": "yes", "real": "no", "family": "no"},
        "cartoon": {"fictional": "yes", "real": "no", "family": "no"},
        "superhero": {"fictional": "yes", "real": "no"},
        "marvel": {"fictional": "yes", "real": "no"},
        "dc": {"fictional": "yes", "real": "no"},
        "male": {"female": "no"},
        "female": {"male": "no"},
        "youtuber": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "politician": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "military": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "singer": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "actor": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "athlete": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "gamer": {"youtuber": "yes"},
        "streamer": {"real": "yes"},
        "esports_clan": {"gamer": "yes", "real": "yes"},
        "arabic_creator": {"youtuber": "yes", "real": "yes"},
        "family": {"real": "yes", "fictional": "no", "anime": "no", "cartoon": "no"},
        "close_relation": {"family": "yes", "real": "yes"},
        "direct_contact": {"family": "yes", "real": "yes"},
        "self": {"family": "yes", "real": "yes"},
        "mother": {"family": "yes", "female": "yes", "parent": "yes", "has_children": "yes", "real": "yes"},
        "father": {"family": "yes", "male": "yes", "parent": "yes", "has_children": "yes", "real": "yes"},
        "sibling": {"family": "yes", "close_relation": "yes", "real": "yes"},
        "parent": {"family": "yes", "close_relation": "yes", "real": "yes"},
        "grandparent": {"family": "yes", "real": "yes"},
        "aunt_uncle": {"family": "yes", "real": "yes"},
        "cousin": {"family": "yes", "real": "yes"},
        "spouse": {"family": "yes", "close_relation": "yes", "real": "yes"},
        "son": {"family": "yes", "male": "yes", "real": "yes"},
        "daughter": {"family": "yes", "female": "yes", "real": "yes"},
        "japanese": {"russian": "no", "german": "no", "french": "no", "korean": "no", "chinese": "no", "indian": "no", "brazilian": "no", "portuguese": "no", "argentinian": "no", "spanish": "no", "italian": "no", "canadian": "no", "swedish": "no", "turkish": "no", "pakistani": "no", "iraqi": "no", "kuwaiti": "no", "jordanian": "no", "syrian": "no", "lebanese": "no", "moroccan": "no", "tunisian": "no", "yemeni": "no", "qatari": "no", "emirati": "no", "colombian": "no", "serbian": "no", "american": "no", "british": "no", "saudi": "no", "egyptian": "no"},
        "russian": {"japanese": "no", "german": "no", "french": "no", "korean": "no", "chinese": "no", "indian": "no", "brazilian": "no", "portuguese": "no", "argentinian": "no", "spanish": "no", "italian": "no", "canadian": "no", "swedish": "no", "turkish": "no", "pakistani": "no", "iraqi": "no", "kuwaiti": "no", "jordanian": "no", "syrian": "no", "lebanese": "no", "moroccan": "no", "tunisian": "no", "yemeni": "no", "qatari": "no", "emirati": "no", "colombian": "no", "serbian": "no", "american": "no", "british": "no", "saudi": "no", "egyptian": "no"},
        "german": {"japanese": "no", "russian": "no", "french": "no", "korean": "no", "chinese": "no", "indian": "no", "brazilian": "no", "portuguese": "no", "argentinian": "no", "spanish": "no", "italian": "no", "canadian": "no", "swedish": "no", "turkish": "no", "pakistani": "no", "iraqi": "no", "kuwaiti": "no", "jordanian": "no", "syrian": "no", "lebanese": "no", "moroccan": "no", "tunisian": "no", "yemeni": "no", "qatari": "no", "emirati": "no", "colombian": "no", "serbian": "no", "american": "no", "british": "no", "saudi": "no", "egyptian": "no"},
    }
    changed = True
    while changed:
        changed = False
        for feature, answer in list(effective.items()):
            # هذه خريطة استنتاجات باتجاه واحد: "نعم، يوتيوبر" تعني أنه حقيقي،
            # لكن "لا، ليس يوتيوبر" لا تعني أنه غير حقيقي. لذلك لا نعكس كل دلالة آليًا.
            if answer != "yes":
                continue
            implied_items = dict(implications.get(feature, {}))
            nationality_features = {"saudi", "american", "british", "egyptian", "japanese", "russian", "german", "french", "korean", "chinese", "indian", "brazilian", "portuguese", "argentinian", "spanish", "italian", "canadian", "swedish", "turkish", "pakistani", "iraqi", "kuwaiti", "jordanian", "syrian", "lebanese", "moroccan", "tunisian", "yemeni", "qatari", "emirati", "colombian", "serbian", "south_african", "jamaican", "roman", "mongolian", "greek"}
            if feature in nationality_features and answer == "yes":
                implied_items.update({other: "no" for other in nationality_features if other != feature})
            for implied, value in implied_items.items():
                if implied not in effective:
                    effective[implied] = value
                    changed = True
    return effective


def _rank_characters(characters, answers, excluded):
    """ترتيب المرشحين مع تضييق فعلي للفئة بحسب إجابات اللاعب.

    الإجابات القطعية عن الفئات الأساسية (مثل سياسي/يوتيوبر/أنمي) لا تبقى
    مجرد نقاط ترجيح؛ بل تصفي المرشحين حتى لا نعود لأسئلة من فئة مستبعدة.
    إذا كانت بيانات القاعدة ناقصة ولا يوجد تطابق، نرجع للترتيب الاحتمالي
    بدل إنهاء اللعبة بلا نتيجة.
    """
    effective_answers = _infer_answers(answers)
    available = [c for c in characters if c["slug"] not in excluded]
    if effective_answers.get("family") != "yes":
        available = [c for c in available if not c["slug"].startswith("family_")]
    if not available:
        return []

    # أسئلة الفئات التي ينبغي أن تغيّر مسار اللعبة مباشرةً.
    category_features = {
        "politician", "youtuber", "anime", "cartoon", "football",
        "athlete", "singer", "actor", "military", "superhero", "marvel",
        "dc", "historical", "scientist", "businessperson", "streamer",
        "gamer", "rapper", "royal", "religious", "fictional", "real",
        "male", "female", "family",
    }
    filtered = available
    for feature in category_features:
        answer = effective_answers.get(feature)
        if answer not in ("yes", "no"):
            continue
        if feature in ("male", "female"):
            # لا نستبعد المرشح الذي لم تُسجّل له صفة جنس، مثل خيار "أنت".
            matches = [c for c in filtered if feature in c["traits"] or not ({"male", "female"} & c["traits"])] if answer == "yes" else [c for c in filtered if feature not in c["traits"]]
        elif answer == "yes":
            matches = [c for c in filtered if feature in c["traits"]]
        else:
            matches = [c for c in filtered if feature not in c["traits"]]
        # لا نفرض تصفية إذا كانت بيانات الشخصيات الحالية لا تغطي الإجابة.
        if matches:
            filtered = matches

    ranked = []
    for c in filtered:
        log_score = 0.0
        for feature, answer in effective_answers.items():
            p = _likelihood(answer, feature in c["traits"])
            log_score += math.log(max(p, 0.0001))
        ranked.append((log_score, c))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked


# الفروع المتخصصة للأسئلة. الإجابة بنعم على فئة رئيسية تنقل اللعبة لأسئلتها.
PRIMARY_BRANCHES = (
    "family", "politician", "youtuber", "anime", "football", "singer", "actor",
    "scientist", "businessperson", "military", "historical", "superhero",
    "cartoon", "athlete", "writer", "philosopher", "religious",
)

BRANCH_QUESTIONS = {
    "family": {"family", "male", "female", "close_relation", "direct_contact", "maternal_side", "paternal_side", "same_household", "has_children", "self", "mother", "father", "sibling", "parent", "grandparent", "aunt_uncle", "cousin", "spouse", "son", "daughter"},
    "politician": {
        "male", "female", "alive", "deceased", "real", "historical", "saudi", "arab",
        "american", "british", "egyptian", "russian", "german", "french", "indian",
        "turkish", "president", "king", "queen", "royal", "military", "revolutionary",
        "ancient", "medieval", "twentieth_century", "religious", "greek", "roman",
    },
    "youtuber": {
        "male", "female", "alive", "real", "saudi", "arab", "american", "british",
        "egyptian", "japanese", "russian", "german", "french", "korean", "chinese",
        "indian", "brazilian", "portuguese", "argentinian", "spanish", "italian",
        "canadian", "swedish", "turkish", "kuwaiti", "iraqi", "jordanian", "syrian",
        "lebanese", "moroccan", "yemeni", "qatari", "emirati", "gamer", "streamer",
        "esports_clan", "gaming_creator", "arabic_creator", "minecraft", "roblox",
        "football_gamer", "streaming_platform", "falcons", "powr", "3am", "r8",
        "fortnite", "fifa", "challenges", "reaction", "vlogger", "prank", "comedy",
        "tech", "travel", "food", "beauty", "education", "podcaster",
    },
    "anime": {
        "male", "female", "fictional", "japanese", "from_japan", "ninja", "pirate",
        "soldier", "wizard", "villain", "alien", "student", "god", "black_hair",
        "white_hair", "wears_glasses", "wears_hat", "uses_sword", "has_powers",
        "main_character", "from_game", "from_comics",
    },
    "football": {"male", "female", "alive", "deceased", "real", "saudi", "arab", "american",
                  "british", "egyptian", "brazilian", "portuguese", "argentinian", "french",
                  "spanish", "italian", "athlete", "basketball", "boxing", "racing", "tennis", "olympic"},
    "singer": {"male", "female", "alive", "deceased", "real", "saudi", "arab", "american",
               "british", "egyptian", "french", "canadian", "swedish", "colombian", "jamaican",
               "rapper", "producer"},
    "actor": {"male", "female", "alive", "deceased", "real", "american", "british", "french",
              "canadian", "chinese", "from_movie", "from_tv"},
    "scientist": {"male", "female", "alive", "deceased", "real", "historical", "german", "serbian",
                  "arab", "nobel", "inventor", "mathematician", "doctor", "ancient", "medieval",
                  "twentieth_century"},
    "military": {"male", "female", "alive", "deceased", "real", "historical", "arab", "french",
                 "german", "russian", "british", "american", "saudi", "king", "revolutionary",
                 "warrior", "ancient", "medieval", "twentieth_century"},
    "historical": {"male", "female", "alive", "deceased", "real", "politician", "military", "royal",
                   "scientist", "religious", "arab", "egyptian", "german", "russian", "french", "british",
                   "american", "greek", "roman", "mongolian", "king", "queen", "president", "revolutionary",
                   "warrior", "ancient", "medieval", "twentieth_century"},
    "superhero": {"male", "female", "fictional", "marvel", "dc", "villain", "alien", "god", "has_powers",
                  "main_character", "from_comics", "from_movie"},
    "cartoon": {"male", "female", "fictional", "anime", "from_tv", "from_movie", "villain", "main_character"},
}


def _active_branch(answers):
    # الفرع مبني على إجابة اللاعب الصريحة، وليس على الاستنتاجات التلقائية فقط.
    answers = answers or {}
    for feature in PRIMARY_BRANCHES:
        if answers.get(feature) == "yes":
            return feature
    return None


def _choose_question(characters, asked, answers=None):
    answers = answers or {}
    known = set(asked) | set(_infer_answers(answers).keys())
    pool = [q for q in QUESTION_BANK if q[0] not in known]
    if not pool or len(characters) < 2:
        return None

    branch = _active_branch(answers)
    allowed = BRANCH_QUESTIONS.get(branch)
    inferred = _infer_answers(answers)
    specific_positive = any(answers.get(feature) == "yes" for feature in PRIMARY_BRANCHES if feature != "family")
    if not branch and inferred.get("real") == "yes" and "family" not in known and not specific_positive:
        family_question = next((q for q in pool if q[0] == "family"), None)
        if family_question:
            return family_question
    if allowed:
        focused = [q for q in pool if q[0] in allowed]
        # ما دام فيه سؤال مفيد داخل فرع اللاعب، لا نرجع لفئات لا علاقة لها به.
        if focused:
            pool = focused

    # احسب مقدار تمييز كل سؤال، مع ترجيح أسئلة الفرع المؤكد.
    total = max(len(characters), 1)
    best, best_score = None, -1.0
    for q in pool:
        feature = q[0]
        yes_count = sum(feature in c["traits"] for c in characters)
        no_count = total - yes_count
        if yes_count == 0 or no_count == 0:
            continue
        balance = min(yes_count, no_count) / total
        branch_bonus = 0.10 if allowed and feature in allowed else 0.0
        # أسئلة الجنسية والصفات التخصصية تظل متاحة، ويُختار الأفضل حسب المرشحين الحاليين.
        score = balance + branch_bonus
        if score > best_score:
            best, best_score = q, score
    return best or (pool[0] if pool else None)


def _language_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("العربية 🇸🇦", callback_data="dn:lang:ar")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="dn:lang:en")],
    ])


def _answer_keyboard(lang):
    labels = dict(ANSWERS[lang])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(labels["yes"], callback_data="dn:answer:yes"), InlineKeyboardButton(labels["no"], callback_data="dn:answer:no")],
        [InlineKeyboardButton(labels["unknown"], callback_data="dn:answer:unknown")],
        [InlineKeyboardButton(labels["probably_no"], callback_data="dn:answer:probably_no"), InlineKeyboardButton(labels["probably_yes"], callback_data="dn:answer:probably_yes")],
        [InlineKeyboardButton("إيقاف اللعبة" if lang == "ar" else "Stop game", callback_data="dn:stop")],
    ])


def _guess_keyboard(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ايه، هو" if lang == "ar" else "Yes, that's it", callback_data="dn:guess:yes")],
        [InlineKeyboardButton("لا، مو هو" if lang == "ar" else "No, try again", callback_data="dn:guess:no")],
        [InlineKeyboardButton("إيقاف اللعبة" if lang == "ar" else "Stop game", callback_data="dn:stop")],
    ])


async def _send_next_question(update, context, user_id, chat_id, s, edit_query=None):
    lang = s["lang"]
    characters = await _characters_for_answers(s["answers"])
    ranked = _rank_characters(characters, s["answers"], set(s["excluded"]))
    if not ranked:
        s["state"] = "finished"
        await _save_session(user_id, chat_id, s)
        text = TEXT[lang]["none"]
        if edit_query:
            await edit_query.edit_message_text(text)
        else:
            await update.effective_message.reply_text(text)
        await _delete_session(user_id, chat_id)
        return

    # بعد عدد كافٍ من الأسئلة، جرّب الشخصية الأعلى احتمالًا.
    if s["question_count"] >= 12:
        top_score, top = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else top_score - 5
        confidence_gap = top_score - second_score
        last_rejected_at = s.get("last_rejected_at")
        extra_checks_done = last_rejected_at is None or (s["question_count"] - int(last_rejected_at)) >= 4
        confident_enough = (confidence_gap >= 2.4 or len(ranked) <= 1) and extra_checks_done
        if s["question_count"] >= MAX_QUESTIONS or confident_enough:
            s["state"] = "guess"
            s["guesses"] = list(dict.fromkeys(s["guesses"] + [top["slug"]]))
            await _save_session(user_id, chat_id, s)
            display_name = top["name_ar"] if lang == "ar" else top["name_en"]
            category = top["category_ar"] if lang == "ar" else top["category_en"]
            text = TEXT[lang]["guess"].format(name=display_name, category=category)
            markup = _guess_keyboard(lang)
            if edit_query:
                await edit_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
            return

    remaining = [c for _, c in ranked[:max(8, min(60, len(ranked)))]]
    inferred = _infer_answers(s["answers"])
    if "family" not in inferred:
        remaining.extend(_family_candidates())
    question = _choose_question(remaining, set(s["asked"]), s["answers"])
    if not question:
        s["question_count"] = MAX_QUESTIONS
        # Force the best available guess without asking a duplicate question.
        top = ranked[0][1]
        s["state"] = "guess"
        if top["slug"] not in s["guesses"]:
            s["guesses"].append(top["slug"])
        await _save_session(user_id, chat_id, s)
        display_name = top["name_ar"] if lang == "ar" else top["name_en"]
        category = top["category_ar"] if lang == "ar" else top["category_en"]
        body = TEXT[lang]["guess"].format(name=display_name, category=category)
        if edit_query:
            await edit_query.edit_message_text(body, reply_markup=_guess_keyboard(lang), parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(body, reply_markup=_guess_keyboard(lang), parse_mode="Markdown")
        return
    s["state"] = "question"
    s["asked"].append(question[0])
    s["current_question"] = question[0]
    await _save_session(user_id, chat_id, s)
    question_text = question[1] if lang == "ar" else question[2]
    body = TEXT[lang]["question"].format(n=s["question_count"] + 1, question=question_text)
    markup = _answer_keyboard(lang)
    if edit_query:
        await edit_query.edit_message_text(body, reply_markup=markup)
    else:
        await update.effective_message.reply_text(body, reply_markup=markup)


async def start_demon_nawaf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    if message.chat.type not in (ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP):
        return
    user_id, chat_id = user.id, message.chat_id
    s = {"lang": "ar", "state": "language", "answers": {}, "asked": [], "excluded": [], "guesses": [], "question_count": 0, "current_question": "", "last_rejected_at": None}
    await _save_session(user_id, chat_id, s)
    await message.reply_text(TEXT["ar"]["intro"], reply_markup=_language_keyboard())


async def demon_nawaf_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user or not query.message:
        return
    data = query.data or ""
    user_id, chat_id = query.from_user.id, query.message.chat_id
    s = await _load_session(user_id, chat_id)
    if data == "dn:stop":
        await query.answer("تم إيقاف اللعبة" if not s or s.get("lang") == "ar" else "Game stopped")
        await _delete_session(user_id, chat_id)
        try:
            await query.edit_message_text("انتهت اللعبة. اكتب ديمون نواف للعب مرة ثانية." if not s or s.get("lang") == "ar" else "Game stopped. Type Demon Nawaf to play again.")
        except TelegramError:
            pass
        return
    if not s:
        await query.answer("اكتب ديمون نواف لبدء لعبة جديدة" if data.endswith(":ar") or data.endswith(":en") else "Game expired", show_alert=False)
        return
    if data.startswith("dn:lang:"):
        lang = data.rsplit(":", 1)[-1]
        if lang not in ("ar", "en"):
            await query.answer()
            return
        s["lang"] = lang
        s["state"] = "question"
        await query.answer()
        await query.edit_message_text(TEXT[lang]["thinking"])
        await _send_next_question(update, context, user_id, chat_id, s, edit_query=query)
        return
    if data.startswith("dn:answer:"):
        if s.get("state") != "question":
            await query.answer("انتظر السؤال التالي" if s.get("lang") == "ar" else "Please wait for the next question")
            return
        answer = data.rsplit(":", 1)[-1]
        feature = s.get("current_question")
        if feature:
            s["answers"][feature] = answer
        s["question_count"] += 1
        await query.answer()
        await _send_next_question(update, context, user_id, chat_id, s, edit_query=query)
        return
    if data.startswith("dn:guess:"):
        choice = data.rsplit(":", 1)[-1]
        if s.get("state") != "guess":
            await query.answer()
            return
        characters = await _characters_for_answers(s["answers"])
        ranked = _rank_characters(characters, s["answers"], set(s["excluded"]))
        if not ranked:
            await query.answer()
            await query.edit_message_text(TEXT[s["lang"]]["none"])
            await _delete_session(user_id, chat_id)
            return
        _, character = ranked[0]
        if choice == "no":
            s["excluded"].append(character["slug"])
            s["last_rejected_at"] = s.get("question_count", 0)
            s["state"] = "question"
            await query.answer()
            await query.edit_message_text(TEXT[s["lang"]]["wrong"])
            await _send_next_question(update, context, user_id, chat_id, s, edit_query=query)
            return
        await query.answer()
        await _delete_session(user_id, chat_id)
        await _show_character_result(query, context, character, s["lang"])
        return
    await query.answer()


async def _wikipedia_info(title, lang):
    if not title:
        return {}
    primary = "ar" if lang == "ar" else "en"
    languages = [primary, "en" if primary == "ar" else "ar"]
    headers = {"User-Agent": "DemonNawafTelegramBot/1.1 (character guessing game)"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT), headers=headers, follow_redirects=True) as client:
        for language in languages:
            url = f"https://{language}.wikipedia.org/w/api.php"
            variants = (
                {"action": "query", "format": "json", "prop": "pageimages|extracts", "exintro": 1, "explaintext": 1, "pithumbsize": 800, "redirects": 1, "titles": title},
                {"action": "query", "format": "json", "generator": "search", "gsrsearch": title, "gsrlimit": 3, "prop": "pageimages|extracts", "exintro": 1, "explaintext": 1, "pithumbsize": 800},
            )
            for params in variants:
                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    pages = response.json().get("query", {}).get("pages", {})
                    page_list = list(pages.values())
                    target_words = {w.casefold() for w in re.findall(r"[A-Za-z0-9]+", title) if len(w) > 2}
                    if "generator" in params:
                        page_list = [page for page in page_list if len(target_words & {w.casefold() for w in re.findall(r"[A-Za-z0-9]+", page.get("title", "")) if len(w) > 2}) / max(len(target_words), 1) >= 0.5]
                    ordered = sorted(page_list, key=lambda page: (not bool(page.get("thumbnail", {}).get("source")), not bool(page.get("extract"))))
                    for page in ordered:
                        if page.get("thumbnail", {}).get("source") or page.get("extract"):
                            return {"image": page.get("thumbnail", {}).get("source", ""), "summary": page.get("extract", ""), "title": page.get("title", title), "source": f"Wikipedia ({language})"}
                except (httpx.HTTPError, ValueError, KeyError):
                    continue
        try:
            response = await client.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": f'filetype:bitmap "{title}"', "gsrnamespace": 6,
                "gsrlimit": 5, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 800,
            })
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            target_words = {w.casefold() for w in re.findall(r"[A-Za-z0-9]+", title) if len(w) > 2}
            candidates = []
            for page in pages.values():
                page_words = {w.casefold() for w in re.findall(r"[A-Za-z0-9]+", page.get("title", "")) if len(w) > 2}
                overlap = len(target_words & page_words) / max(len(target_words), 1)
                image_info = (page.get("imageinfo") or [{}])[0]
                image_url = image_info.get("thumburl") or image_info.get("url")
                mime = (image_info.get("mime") or "").lower()
                if image_url and overlap >= 0.5 and (not mime or mime.startswith("image/")):
                    candidates.append((overlap, image_url))
            if candidates:
                candidates.sort(reverse=True)
                return {"image": candidates[0][1], "summary": "", "title": title, "source": "Wikimedia Commons"}
        except (httpx.HTTPError, ValueError, KeyError):
            pass
    return {}


async def _show_character_result(query, context, character, lang):
    name = character["name_ar"] if lang == "ar" else character["name_en"]
    category = character["category_ar"] if lang == "ar" else character["category_en"]
    is_family_candidate = character["slug"].startswith("family_")
    wiki_title = character["wiki_title"] or character["name_en"]
    info = {} if is_family_candidate else await _wikipedia_info(wiki_title, lang)
    image_url = info.get("image", "") or character["image_url"]
    summary = info.get("summary", "") or (character["summary_ar"] if lang == "ar" else character["summary_en"])
    if info and not is_family_candidate:
        try:
            await _db_execute(
                "UPDATE demon_nawaf_characters SET image_url=CASE WHEN ?<>'' THEN ? ELSE image_url END, "
                "summary_ar=CASE WHEN ?='ar' AND summary_ar='' THEN ? ELSE summary_ar END, "
                "summary_en=CASE WHEN ?='en' AND summary_en='' THEN ? ELSE summary_en END, "
                "updated_at=NOW() WHERE slug=?",
                (info.get("image", ""), info.get("image", ""), lang, summary[:2500], lang, summary[:2500], character["slug"])
            )
        except Exception:
            pass
    bot_username = context.application.bot_data.get("demon_nawaf_bot_username")
    bot_button_name = context.application.bot_data.get("demon_nawaf_bot_name")
    if not bot_username or not bot_button_name:
        try:
            me = await context.bot.get_me()
            bot_username = me.username
            bot_button_name = me.first_name or ("@" + me.username if me.username else "ديمون نواف")
            context.application.bot_data["demon_nawaf_bot_username"] = bot_username
            context.application.bot_data["demon_nawaf_bot_name"] = bot_button_name
        except TelegramError:
            bot_username = None
            bot_button_name = "ديمون نواف"
    buttons = []
    if bot_username:
        buttons.append([InlineKeyboardButton(bot_button_name, url=f"https://t.me/{bot_username}")])
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    caption = TEXT[lang]["correct"].format(name=name) + f"\n\n{'الفئة' if lang == 'ar' else 'Category'}: {category}"
    if summary:
        caption += "\n\n" + summary[:650]
    if is_family_candidate:
        await query.message.reply_text(caption, reply_markup=markup, parse_mode="Markdown")
        return
    sent_photo = False
    if image_url:
        try:
            photo = None
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT), headers={"User-Agent": "DemonNawafTelegramBot/1.0"}, follow_redirects=True) as client:
                    response = await client.get(image_url)
                    response.raise_for_status()
                    content_type = response.headers.get("Content-Type", "")
                    if "image" in content_type.lower() and len(response.content) >= 1024:
                        from io import BytesIO
                        photo = BytesIO(response.content)
                        photo.name = "demon_nawaf.jpg"
            except (httpx.HTTPError, ValueError):
                photo = None
            if photo:
                await query.message.reply_photo(photo=photo, caption=caption[:1020], reply_markup=markup, parse_mode="Markdown")
                sent_photo = True
            else:
                await query.message.reply_photo(photo=image_url, caption=caption[:1020], reply_markup=markup, parse_mode="Markdown")
                sent_photo = True
        except (TelegramError, Exception):
            sent_photo = False
    if not sent_photo:
        fallback = caption + "\n\n" + TEXT[lang]["photo_error"]
        await query.message.reply_text(fallback[:4000], reply_markup=markup, parse_mode="Markdown")


async def demon_nawaf_private_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Optional /start deep-link entry point: /start demon_nawaf."""
    if context.args and context.args[0] == "demon_nawaf":
        await start_demon_nawaf(update, context)
        raise ApplicationHandlerStop
