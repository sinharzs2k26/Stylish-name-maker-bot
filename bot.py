import os
import sqlite3
import logging
import asyncio
import random
import hashlib
import threading
from typing import Dict, List, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode
from contextlib import contextmanager

# ==================== CONFIGURATION ====================
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [7728700576]
DB_NAME = 'stylish_name_bot.db'
ITEMS_PER_PAGE = 10
MAX_NAME_LENGTH = 30

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== DATABASE LOCK ====================
db_lock = threading.Lock()

@contextmanager
def get_db_connection():
    """Thread-safe database connection"""
    with db_lock:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

# ==================== DATABASE ====================
class Database:
    @staticmethod
    def setup():
        """Initialize database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Create tables with correct schema
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        first_name TEXT,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS generated_styles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        original_text TEXT,
                        styled_text TEXT,
                        style_type TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                conn.commit()
                logger.info("✅ Database initialized")
                
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
    
    @staticmethod
    def add_user(user_id: int, first_name: str, username: str):
        """Add user to database"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users (user_id, first_name, username) 
                    VALUES (?, ?, ?)
                ''', (user_id, first_name, username or ""))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Add user error: {e}")
    
    @staticmethod
    def get_user_count():
        """Get total user count"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                count = cursor.fetchone()[0]
                return count if count else 0
        except sqlite3.Error as e:
            logger.error(f"Get user count error: {e}")
            return 0
    
    @staticmethod
    def get_all_users():
        """Get all user IDs"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users")
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Get all users error: {e}")
            return []
    
    @staticmethod
    def save_style(user_id: int, original: str, styled: str, style_type: str):
        """Save generated style"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO generated_styles (user_id, original_text, styled_text, style_type)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, original, styled, style_type))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Save style error: {e}")

# ==================== FONTS & STYLES ====================
class FontStyles:
    # Base characters for translation
    NORMAL = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    
    # 50+ Fonts Collection
    FONTS = {
        'bold': "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
        'italic': "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝚈𝚉0123456789",
        'bold_italic': "𝙖𝙗𝙘𝙙𝙚𝙛𝙜𝙝𝙞𝙟𝙠𝙡𝙢𝙣𝙤𝙥𝙦𝙧𝙨𝙩𝙪𝙫𝙬𝙭𝙮𝙯𝘼𝘽𝘾𝘿𝙀𝙁𝙂𝙃𝙄𝙅𝙆𝙇𝙈𝙉𝙊𝙋𝙌𝙍𝙎𝙏𝙐𝙑𝙒𝙓𝙔𝙕𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟿",
        'monospace': "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿",
        'cursive': "𝒶𝒷𝒸𝒹𝑒𝒻𝑔𝒽𝒾𝒿𝓀𝓁𝓂𝓃𝑜𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏𝒜𝐵𝒞𝒟𝐸𝐹𝒢𝐻𝐼𝒥𝒦𝐿𝑀𝒩𝒪𝒫𝒬𝑅𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫",
        'fraktur': "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ0123456789",
        'blackboard': "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
        'small_caps': "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        'bubble': "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ⓪①②③④⑤⑥⑦⑧⑨",
        'circled': "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ⓪①②③④⑤⑥⑦⑧⑨",
        'square': "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉0123456789",
        'gothic': "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷0123456789",
        'double_struck': "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
        'script': "𝒜𝐵𝒞𝒟𝐸𝐹𝒢𝐻𝐼𝒥𝒦𝐿𝑀𝒩𝒪𝒫𝒬𝑅𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹𝑒𝒻𝑔𝒽𝒾𝒿𝓀𝓁𝓂𝓃𝑜𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏0123456789",
        'superscript': "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖᵠʳˢᵗᵘᵛʷˣʸᶻᴬᴮᶜᴰᴱᶠᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᵠᴿˢᵀᵁⱽᵂˣʸᶻ⁰¹²³⁴⁵⁶⁷⁸⁹",
        'subscript': "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓᵧ𝓏ₐ𝓫𝒸𝒹ₑ𝒻𝓰ₕᵢⱼₖₗₘₙₒₚ𝓆ᵣₛₜᵤᵥ𝓌ₓᵧ𝓏₀₁₂₃₄₅₆₇₈₉",
        'outline': "𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟0123456789",
        'heavy': "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
        'wide': "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ０１２３４５６７８９",
        'narrow': "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ0123456789",
        'upside_down': "ɐqɔpǝɟƃɥıɾʞlɯuodbɹsʇnʌʍxʎz∀qƆpƎℲפHIſʞ˥WNOԀQɹS┴∩ΛMX⅄Z0ƖᄅƐㄣϛ9ㄥ86",
        'mirror': "ɐqɔpǝɟƃɥıɾʞlɯuodbɹsʇnʌʍxʎz∀qƆpƎℲפHIſʞ˥WNOԀQɹS┴∩ΛMX⅄Z0ƖᄅƐㄣϛ9ㄥ86",
        'strikethrough': "a̶b̶c̶d̶e̶f̶g̶h̶i̶j̶k̶l̶m̶n̶o̶p̶q̶r̶s̶t̶u̶v̶w̶x̶y̶z̶A̶B̶C̶D̶E̶F̶G̶H̶I̶J̶K̶L̶M̶N̶O̶P̶Q̶R̶S̶T̶U̶V̶W̶X̶Y̶Z̶0̶1̶2̶3̶4̶5̶6̶7̶8̶9̶",
        'underline': "a̲b̲c̲d̲e̲f̲g̲h̲i̲j̲k̲l̲m̲n̲o̲p̲q̲r̲s̲t̲u̲v̲w̲x̲y̲z̲A̲B̲C̲D̲E̲F̲G̲H̲I̲J̲K̲L̲M̲N̲O̲P̲Q̲R̲S̲T̲U̲V̲W̲X̲Y̲Z̲0̲1̲2̲3̲4̲5̲6̲7̲8̲9̲",
        'overline': "a̅b̅c̅d̅e̅f̅g̅h̅i̅j̅k̅l̅m̅n̅o̅p̅q̅r̅s̅t̅u̅v̅w̅x̅y̅z̅A̅B̅C̅D̅E̅F̅G̅H̅I̅J̅K̅L̅M̅N̅O̅P̅Q̅R̅S̅T̅U̅V̅W̅X̅Y̅Z̅0̅1̅2̅3̅4̅5̅6̅7̅8̅9̅",
        'double_underline': "a̳b̳c̳d̳e̳f̳g̳h̳i̳j̳k̳l̳m̳n̳o̳p̳q̳r̳s̳t̳u̳v̳w̳x̳y̳z̳A̳B̳C̳D̳E̳F̳G̳H̳I̳J̳K̳L̳M̳N̳O̳P̳Q̳R̳S̳T̳U̳V̳W̳X̳Y̳Z̳0̳1̳2̳3̳4̳5̳6̳7̳8̳9̳",
        'squiggle': "a̰b̰c̰d̰ḛf̰g̰h̰ḭj̰k̰l̰m̰n̰o̰p̰q̰r̰s̰t̰ṵv̰w̰x̰y̰z̰A̰B̰C̰D̰ḚF̰G̰H̰ḬJ̰K̰L̰M̰N̰O̰P̰Q̰R̰S̰T̰ṴV̰W̰X̰Y̰Z̰0̰1̰2̰3̰4̰5̰6̰7̰8̰9̰",
        'wave': "ãb̃c̃d̃ẽf̃g̃h̃ĩj̃k̃l̃m̃ñõp̃q̃r̃s̃t̃ũṽw̃x̃ỹz̃ÃB̃C̃D̃ẼF̃G̃H̃ĨJ̃K̃L̃M̃ÑÕP̃Q̃R̃S̃T̃ŨṼW̃X̃ỸZ̃0̃1̃2̃3̃4̃5̃6̃7̃8̃9̃",
        'slash': "a̷b̷c̷d̷e̷f̷g̷h̷i̷j̷k̷l̷m̷n̷o̷p̷q̷r̷s̷t̷u̷v̷w̷x̷y̷z̷A̷B̷C̷D̷E̷F̷G̷H̷I̷J̷K̷L̷M̷N̷O̷P̷Q̷R̷S̷T̷U̷V̷W̷X̷Y̷Z̷0̷1̷2̷3̷4̷5̷6̷7̷8̷9̷",
        'x_through': "a̸b̸c̸d̸e̸f̸g̸h̸i̸j̸k̸l̸m̸n̸o̸p̸q̸r̸s̸t̸u̸v̸w̸x̸y̸z̸A̸B̸C̸D̸E̸F̸G̸H̸I̸J̸K̸L̸M̸N̸O̸P̸Q̸R̸S̸T̸U̸V̷W̷X̷Y̷Z̷0̷1̷2̷3̷4̷5̷6̷7̷8̷9̷",
        'asterisk': "a͙b͙c͙d͙e͙f͙g͙h͙i͙j͙k͙l͙m͙n͙o͙p͙q͙r͙s͙t͙u͙v͙w͙x͙y͙z͙A͙B͙C͙D͙E͙F͙G͙H͙I͙J͙K͙L͙M͙N͙O͙P͙Q͙R͙S͙T͙U͙V͙W͙X͙Y͙Z͙0͙1͙2͙3͙4͙5͙6͙7͙8͙9͙",
        'dot_above': "ȧḃċḋėḟġḣi̇j̇k̇l̇ṁṅȯṗq̇ṙṡṫu̇v̇ẇẋẏżȦḂĊḊĖḞĠḢİJ̇K̇L̇ṀṄȮṖQ̇ṘṠṪU̇V̇ẆẊẎŻ0̇1̇2̇3̇4̇5̇6̇7̇8̇9̇",
        'dot_below': "ạḅc̣ḍẹf̣g̣ḥịj̣ḳḷṃṇọp̣q̣ṛṣṭụṿẉx̣ỵẓẠḄC̣ḌẸF̣G̣ḤỊJ̣ḲḶṂṆỌP̣Q̣ṚṢṬỤṾẈX̣ỴẒ0̣1̣2̣3̣4̣5̣6̣7̣8̣9̣",
        'ring_above': "åb̊c̊d̊e̊f̊g̊h̊i̊j̊k̊l̊m̊n̊o̊p̊q̊r̊s̊t̊ův̊ẘx̊ẙz̊ÅB̊C̊D̊E̊F̊G̊H̊I̊J̊K̊L̊M̊N̊O̊P̊Q̊R̊S̊T̊ŮV̊W̊X̊Y̊Z̊0̊1̊2̊3̊4̊5̊6̊7̊8̊9̊",
        'hook_above': "ảb̉c̉d̉ẻf̉g̉h̉ỉj̉k̉l̉m̉n̉ỏp̉q̉r̉s̉t̉ủv̉w̉x̉ỷz̉ẢB̉C̉D̉ẺF̉G̉H̉ỈJ̉K̉L̉M̉N̉ỎP̉Q̉R̉S̉T̉ỦV̉W̉X̉ỶZ̉0̉1̉2̉3̉4̉5̉6̉7̉8̉9̉",
        'horn': "a̛b̛c̛d̛e̛f̛g̛h̛i̛j̛k̛l̛m̛n̛ơp̛q̛r̛s̛t̛ưv̛w̛x̛y̛z̛A̛B̛C̛D̛E̛F̛G̛H̛I̛J̛K̛L̛M̛N̛ƠP̛Q̛R̛S̛T̛ƯV̛W̛X̛Y̛Z̛0̛1̛2̛3̛4̛5̛6̛7̛8̛9̛",
        'cedilla': "a̧b̧çḑȩf̧ģḩi̧j̧ķļm̧ņo̧p̧q̧ŗşţu̧v̧w̧x̧y̧z̧A̧B̧ÇḐȨF̧ĢḨI̧J̧ĶĻM̧ŅO̧P̧Q̧ŖŞŢU̧V̧W̧X̧Y̧Z̧0̧1̧2̧3̧4̧5̧6̧7̧8̧9̧",
        'ogonek': "ąb̨c̨d̨ęf̨g̨h̨įj̨k̨l̨m̨n̨ǫp̨q̨r̨s̨t̨ųv̨w̨x̨y̨z̨ĄB̨C̨D̨ĘF̨G̨H̨ĮJ̨K̨L̨M̨N̨ǪP̨Q̨R̨S̨T̨ŲV̨W̨X̨Y̨Z̨0̨1̨2̨3̨4̨5̨6̨7̨8̨9̨",
        'caron': "ǎb̌čďěf̌ǧȟǐǰǩľm̌ňǒp̌q̌řšťǔv̌w̌x̌y̌žǍB̌ČĎĚF̌ǦȞǏJ̌ǨĽM̌ŇǑP̌Q̌ŘŠŤǓV̌W̌X̌Y̌Ž0̌1̌2̌3̌4̌5̌6̌7̌8̌9̌",
        'breve': "ăb̆c̆d̆ĕf̆ğh̆ĭj̆k̆l̆m̆n̆ŏp̆q̆r̆s̆t̆ŭv̆w̆x̆y̆z̆ĂB̆C̆D̆ĔF̆ĞH̆ĬJ̆K̆L̆M̆N̆ŎP̆Q̆R̆S̆T̆ŬV̆W̆X̆Y̆Z̆0̆1̆2̆3̆4̆5̆6̆7̆8̆9̆",
        'macron': "āb̄c̄d̄ēf̄ḡh̄īj̄k̄l̄m̄n̄ōp̄q̄r̄s̄t̄ūv̄w̄x̄ȳz̄ĀB̄C̄D̄ĒF̄ḠH̄ĪJ̄K̄L̄M̄N̄ŌP̄Q̄R̄S̄T̄ŪV̄W̄X̄ȲZ̄0̄1̄2̄3̄4̄5̄6̄7̄8̄9̄",
        'tilde': "ãb̃c̃d̃ẽf̃g̃h̃ĩj̃k̃l̃m̃ñõp̃q̃r̃s̃t̃ũṽw̃x̃ỹz̃ÃB̃C̃D̃ẼF̃G̃H̃ĨJ̃K̃L̃M̃ÑÕP̃Q̃R̃S̃T̃ŨṼW̃X̃ỸZ̃0̃1̃2̃3̃4̃5̃6̃7̃8̃9̃",
        'diaeresis': "äb̈c̈d̈ëf̈g̈ḧïj̈k̈l̈m̈n̈öp̈q̈r̈s̈ẗüv̈ẅẍÿz̈ÄB̈C̈D̈ËF̈G̈ḦÏJ̈K̈L̈M̈N̈ÖP̈Q̈R̈S̈T̈ÜV̈ẄẌŸZ̈0̈1̈2̈3̈4̈5̈6̈7̈8̈9̈",
        'acute': "áb́ćd́éf́ǵh́íj́ḱĺḿńóṕq́ŕśt́úv́ẃx́ýźÁB́ĆD́ÉF́ǴH́ÍJ́ḰĹḾŃÓṔQ́ŔŚT́ÚV́ẂX́ÝŹ0́1́2́3́4́5́6́7́8́9́",
        'grave': "àb̀c̀d̀èf̀g̀h̀ìj̀k̀l̀m̀ǹòp̀q̀r̀s̀t̀ùv̀ẁx̀ỳz̀ÀB̀C̀D̀ÈF̀G̀H̀ÌJ̀K̀L̀M̀ǸÒP̀Q̀R̀S̀T̀ÙV̀ẀX̀ỲZ̀0̀1̀2̀3̀4̀5̀6̀7̀8̀9̀",
        'circumflex': "âb̂ĉd̂êf̂ĝĥîĵk̂l̂m̂n̂ôp̂q̂r̂ŝt̂ûv̂ŵx̂ŷẑÂB̂ĈD̂ÊF̂ĜĤÎĴK̂L̂M̂N̂ÔP̂Q̂R̂ŜT̂ÛV̂ŴX̂ŶẐ0̂1̂2̂3̂4̂5̂6̂7̂8̂9̂",
    }
    
    # Small Caps Font for bot messages
    SMALL_CAPS_FONT = str.maketrans(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789"
    )
    
    # Translation tables cache
    TRANSLATION_TABLES = {}
    
    @classmethod
    def _init_translation_tables(cls):
        """Initialize translation tables"""
        if not cls.TRANSLATION_TABLES:
            for font_name, font_chars in cls.FONTS.items():
                if len(cls.NORMAL) == len(font_chars):
                    cls.TRANSLATION_TABLES[font_name] = str.maketrans(cls.NORMAL, font_chars)
    
    # 1000+ Decorative Styles
    DECORATIVE_STYLES = [
        # Basic Decorations
        "꧁{}꧂", "⫷{}⫸", "『{}』", "༺{}༻", "♛{}♛", "⚡{}⚡", "◥{}◤", "✦{}✦",
        "❖{}❖", "⌖{}⌖", "亗{}亗", "卍{}卍", "【{}】", "〖{}〗", "〈{}〉", "«{}»",
        "‹{}›", "⁅{}⁆", "⌈{}⌉", "⌊{}⌋", "⎰{}⎱", "⎡{}⎤", "⎣{}⎦", "⎡{}⎦",
        "⎣{}⎤", "⎡{}⎥", "⎢{}⎦", "⎣{}⎥", "⎢{}⎤", "『☆{}☆』", "『★{}★』",
        "『☯{}☯』", "『☬{}☬』", "『☠{}☠』", "『☣{}☣』", "『⚜{}⚜』", "『✠{}✠』",
        "『✧{}✧』", "『✦{}✦』", "『❖{}❖』", "『✪{}✪』", "『✰{}✰』", "『❂{}❂』",
        "『✵{}✵』", "『✯{}✯』", "╔═══✦{}✦═══╗", "┏━━━❖{}❖━━━┓", "【†{}†】",
        "『〖{}〗』", "▁▂▃▄▅▆▇█{}█▇▆▅▄▃▂▁", "░▒▓█{}█▓▒░", "█▀▀▀▀▀▀▀▀▀▀{}▀▀▀▀▀▀▀▀▀▀█",
        "╔═╗{}╔═╗", "█▶{}◀█", "◄{}►", "«{}»", "≪{}≫", "⋘{}⋙", "❰{}❱",
        "〔{}〕", "〖{}〗", "〈{}〉", "««{}»»", "≪≪{}≫≫", "▄︻デ══━一{}一══デ︻▄",
        "╾━╤デ╦︻{}︻╦デ╤━╼", "︻╦̵̵͇̿̿̿̿╤──{}──╤̵̵͇̿̿̿̿╦︻", "【﻿{}】", "『⇝{}⇜』",
        "|!¤*'~``~'*¤!|{}|!¤*'~``~'*¤!|", "╔═══━━━──•{}•──━━━═══╗",
        "╔═════≪•{}•≫═════╗", "╔═╗•{}•╔═╗", "╔╗•{}•╔╗", "╔╗{}╔╗",
        "╚╗{}╔╝", "╚═╝{}╚═╝", "╚╝{}╚╝", "◢{}◣", "◣{}◢", "◤{}◥",
        "◥{}◤", "◈{}◈", "◇{}◇", "◆{}◆", "◉{}◉", "◎{}◎", "⊙{}⊙",
        "⦿{}⦿", "⦾{}⦾", "⦿{}⦿", "⧈{}⧈", "⧉{}⧉", "⧊{}⧊", "⧋{}⧋",
        "⧌{}⧌", "⧍{}⧍", "⧎{}⧎", "⧏{}⧏", "⧐{}⧐", "⧑{}⧑", "⧒{}⧒",
        "⧓{}⧓", "⧔{}⧔", "⧕{}⧕", "⧖{}⧖", "⧗{}⧗", "⧘{}⧘", "⧙{}⧙",
        "⧚{}⧚", "⧛{}⧛", "⧜{}⧜", "⧝{}⧝", "⧞{}⧞", "⧟{}⧟", "⧠{}⧠",
        "⧡{}⧡", "⧢{}⧢", "⧣{}⧣", "⧤{}⧤", "⧥{}⧥", "⧦{}⧦", "⧧{}⧧",
        "⧨{}⧨", "⧩{}⧩", "⧪{}⧪", "⧫{}⧫", "⧬{}⧬", "⧭{}⧭", "⧮{}⧮",
        "⧯{}⧯", "⧰{}⧰", "⧱{}⧱", "⧲{}⧲", "⧳{}⧳", "⧴{}⧴", "⧵{}⧵",
        "⧶{}⧶", "⧷{}⧷", "⧸{}⧸", "⧹{}⧹", "⧺{}⧺", "⧻{}⧻", "⧼{}⧼",
        "⧽{}⧽", "⧾{}⧾", "⧿{}⧿", "⨀{}⨀", "⨁{}⨁", "⨂{}⨂", "⨃{}⨃",
        "⨄{}⨄", "⨅{}⨅", "⨆{}⨆", "⨇{}⨇", "⨈{}⨈", "⨉{}⨉", "⨊{}⨊",
        "⨋{}⨋", "⨌{}⨌", "⨍{}⨍", "⨎{}⨎", "⨏{}⨏", "⨐{}⨐", "⨑{}⨑",
        "⨒{}⨒", "⨓{}⨓", "⨔{}⨔", "⨕{}⨕", "⨖{}⨖", "⨗{}⨗", "⨘{}⨘",
        "⨙{}⨙", "⨚{}⨚", "⨛{}⨛", "⨜{}⨜", "⨝{}⨝", "⨞{}⨞", "⨟{}⨟",
        "⨠{}⨠", "⨡{}⨡", "⨢{}⨢", "⨣{}⨣", "⨤{}⨤", "⨥{}⨥", "⨦{}⨦",
        "⨧{}⨧", "⨨{}⨨", "⨩{}⨩", "⨪{}⨪", "⨫{}⨫", "⨬{}⨬", "⨭{}⨭",
        "⨮{}⨮", "⨯{}⨯", "⨰{}⨰", "⨱{}⨱", "⨲{}⨲", "⨳{}⨳", "⨴{}⨴",
        "⨵{}⨵", "⨶{}⨶", "⨷{}⨷", "⨸{}⨸", "⨹{}⨹", "⨺{}⨺", "⨻{}⨻",
        "⨼{}⨼", "⨽{}⨽", "⨾{}⨾", "⨿{}⨿", "⩀{}⩀", "⩁{}⩁", "⩂{}⩂",
        "⩃{}⩃", "⩄{}⩄", "⩅{}⩅", "⩆{}⩆", "⩇{}⩇", "⩈{}⩈", "⩉{}⩉",
        "⩊{}⩊", "⩋{}⩋", "⩌{}⩌", "⩍{}⩍", "⩎{}⩎", "⩏{}⩏", "⩐{}⩐",
        "⩑{}⩑", "⩒{}⩒", "⩓{}⩓", "⩔{}⩔", "⩕{}⩕", "⩖{}⩖", "⩗{}⩗",
        "⩘{}⩘", "⩙{}⩙", "⩚{}⩚", "⩛{}⩛", "⩜{}⩜", "⩝{}⩝", "⩞{}⩞",
        "⩟{}⩟", "⩠{}⩠", "⩡{}⩡", "⩢{}⩢", "⩣{}⩣", "⩤{}⩤", "⩥{}⩥",
        "⩦{}⩦", "⩧{}⩧", "⩨{}⩨", "⩩{}⩩", "⩪{}⩪", "⩫{}⩫", "⩬{}⩬",
        "⩭{}⩭", "⩮{}⩮", "⩯{}⩯", "⩰{}⩰", "⩱{}⩱", "⩲{}⩲", "⩳{}⩳",
        "⩴{}⩴", "⩵{}⩵", "⩶{}⩶", "⩷{}⩷", "⩸{}⩸", "⩹{}⩹", "⩺{}⩺",
        "⩻{}⩻", "⩼{}⩼", "⩽{}⩽", "⩾{}⩾", "⩿{}⩿", "⪀{}⪀", "⪁{}⪁",
        "⪂{}⪂", "⪃{}⪃", "⪄{}⪄", "⪅{}⪅", "⪆{}⪆", "⪇{}⪇", "⪈{}⪈",
        "⪉{}⪉", "⪊{}⪊", "⪋{}⪋", "⪌{}⪌", "⪍{}⪍", "⪎{}⪎", "⪏{}⪏",
        "⪐{}⪐", "⪑{}⪑", "⪒{}⪒", "⪓{}⪓", "⪔{}⪔", "⪕{}⪕", "⪖{}⪖",
        "⪗{}⪗", "⪘{}⪘", "⪙{}⪙", "⪚{}⪚", "⪛{}⪛", "⪜{}⪜", "⪝{}⪝",
        "⪞{}⪞", "⪟{}⪟", "⪠{}⪠", "⪡{}⪡", "⪢{}⪢", "⪣{}⪣", "⪤{}⪤",
        "⪥{}⪥", "⪦{}⪦", "⪧{}⪧", "⪨{}⪨", "⪩{}⪩", "⪪{}⪪", "⪫{}⪫",
        "⪬{}⪬", "⪭{}⪭", "⪮{}⪮", "⪯{}⪯", "⪰{}⪰", "⪱{}⪱", "⪲{}⪲",
        "⪳{}⪳", "⪴{}⪴", "⪵{}⪵", "⪶{}⪶", "⪷{}⪷", "⪸{}⪸", "⪹{}⪹",
        "⪺{}⪺", "⪻{}⪻", "⪼{}⪼", "⪽{}⪽", "⪾{}⪾", "⪿{}⪿", "⫀{}⫀",
        "⫁{}⫁", "⫂{}⫂", "⫃{}⫃", "⫄{}⫄", "⫅{}⫅", "⫆{}⫆", "⫇{}⫇",
        "⫈{}⫈", "⫉{}⫉", "⫊{}⫊", "⫋{}⫋", "⫌{}⫌", "⫍{}⫍", "⫎{}⫎",
        "⫏{}⫏", "⫐{}⫐", "⫑{}⫑", "⫒{}⫒", "⫓{}⫓", "⫔{}⫔", "⫕{}⫕",
        "⫖{}⫖", "⫗{}⫗", "⫘{}⫘", "⫙{}⫙", "⫚{}⫚", "⫛{}⫛", "⫝̸{}⫝̸",
        "⫝{}⫝", "⫞{}⫞", "⫟{}⫟", "⫠{}⫠", "⫡{}⫡", "⫢{}⫢", "⫣{}⫣",
        "⫤{}⫤", "⫥{}⫥", "⫦{}⫦", "⫧{}⫧", "⫨{}⫨", "⫩{}⫩", "⫪{}⫪",
        "⫫{}⫫", "⫬{}⫬", "⫭{}⫭", "⫮{}⫮", "⫯{}⫯", "⫰{}⫰", "⫱{}⫱",
        "⫲{}⫲", "⫳{}⫳", "⫴{}⫴", "⫵{}⫵", "⫶{}⫶", "⫷{}⫷", "⫸{}⫸",
        "⫹{}⫹", "⫺{}⫺", "⫻{}⫻", "⫼{}⫼", "⫽{}⫽", "⫾{}⫾", "⫿{}⫿",
        
        # Emoji Styles (200+)
        "😈{}😈", "👑{}👑", "🔥{}🔥", "⚡{}⚡", "✨{}✨", "🎯{}🎯", "🎭{}🎭",
        "🎮{}🎮", "💀{}💀", "🤖{}🤖", "👻{}👻", "👽{}👽", "🤴{}🤴", "👸{}👸",
        "🦸{}🦸", "🦹{}🦹", "🧙{}🧙", "🧛{}🧛", "🧟{}🧟", "🧞{}🧞", "🧚{}🧚",
        "🦄{}🦄", "🐉{}🐉", "🐲{}🐲", "🦁{}🦁", "🐯{}🐯", "🐺{}🐺", "🦊{}🦊",
        "🐍{}🐍", "🦅{}🦅", "🦇{}🦇", "🕷️{}🕷️", "🕸️{}🕸️", "💎{}💎", "⚔️{}⚔️",
        "🛡️{}🛡️", "🏹{}🏹", "🔫{}🔫", "🗡️{}🗡️", "🔱{}🔱", "⚜️{}⚜️", "🦠{}🦠",
        "♡{}♡", "♥{}♥", "❥{}❥", "ღ{}ღ", "❦{}❦", "❧{}❧", "☯{}☯", "☮{}☮",
        "☪{}☪", "✡{}✡", "⚛{}⚛", "🕉{}🕉", "✝{}✝", "✞{}✞", "✟{}✟", "☦{}☦",
        "🕎{}🕎", "🔯{}🔯", "🔼{}🔼", "🔽{}🔽", "⏫{}⏫", "⏬{}⏬", "⏭️{}⏭️",
        "⏮️{}⏮️", "⏸️{}⏸️", "⏹️{}⏹️", "⏺️{}⏺️", "⏏️{}⏏️", "🎦{}🎦", "🔅{}🔅",
        "🔆{}🔆", "📛{}📛", "📜{}📜", "📰{}📰", "🏴{}🏴", "🏳️{}🏳️", "🏴‍☠️{}🏴‍☠️",
        "🏳️‍🌈{}🏳️‍🌈", "🇺🇳{}🇺🇳", "🇺🇸{}🇺🇸", "🇬🇧{}🇬🇧", "🇩🇪{}🇩🇪", "🇫🇷{}🇫🇷",
        "🇮🇹{}🇮🇹", "🇪🇸{}🇪🇸", "🇷🇺{}🇷🇺", "🇨🇳{}🇨🇳", "🇯🇵{}🇯🇵", "🇰🇷{}🇰🇷",
        "🇮🇳{}🇮🇳", "🇧🇩{}🇧🇩", "🇵🇰{}🇵🇰", "🇸🇦{}🇸🇦", "🇦🇪{}🇦🇪", "🇶🇦{}🇶🇦",
        "🎮{}🎮", "🕹️{}🕹️", "👾{}👾", "🖥️{}🖥️", "💻{}💻", "📱{}📱", "🎲{}🎲",
        "🎰{}🎰", "🎯{}🎯", "🎳{}🎳", "🏓{}🏓", "🏸{}🏸", "🥊{}🥊", "🥋{}🥋",
        "⛸️{}⛸️", "🎿{}🎿", "⛷️{}⛷️", "🏂{}🏂", "🏄{}🏄", "🏊{}🏊", "🤽{}🤽",
        "🏋️{}🏋️", "🤸{}🤸", "🤾{}🤾", "🤺{}🤺", "🥌{}🥌", "🎖️{}🎖️", "🏆{}🏆",
        "🏅{}🏅", "🥇{}🥇", "🥈{}🥈", "🥉{}🥉", "⚽{}⚽", "🏀{}🏀", "🏈{}🏈",
        "⚾{}⚾", "🎾{}🎾", "🏐{}🏐", "🏉{}🏉", "🎱{}🎱", "🏏{}🏏", "🏑{}🏑",
        "🏒{}🏒", "🏓{}🏓", "🏸{}🏸", "🥅{}🥅", "🥊{}🥊", "🥋{}🥋", "🥏{}🥏",
        "🥍{}🥍", "🪃{}🪃", "🪁{}🪁", "🪂{}🪂", "🤿{}🤿", "🥽{}🥽", "🥼{}🥼",
        "🦺{}🦺", "👑{}👑", "👒{}👒", "🎩{}🎩", "🎓{}🎓", "🧢{}🧢", "⛑️{}⛑️",
        "📿{}📿", "💄{}💄", "💍{}💍", "💎{}💎", "🔪{}🔪", "💣{}💣", "🧨{}🧨",
        "📯{}📯", "🗜️{}🗜️", "⚙️{}⚙️", "🔩{}🔩", "⚗️{}⚗️", "🔬{}🔬", "🔭{}🔭",
        "📡{}📡", "💉{}💉", "💊{}💊", "🧪{}🧪", "🧫{}🧫", "🧬{}🧬", "🔋{}🔋",
        "🔌{}🔌", "💡{}💡", "🔦{}🔦", "🕯️{}🕯️", "🧯{}🧯", "🛢️{}🛢️", "⚱️{}⚱️",
        "🗿{}🗿", "🪨{}🪨", "🪵{}🪵", "🌱{}🌱", "🌲{}🌲", "🌳{}🌳", "🌴{}🌴",
        "🌵{}🌵", "🌾{}🌾", "🌿{}🌿", "🍀{}🍀", "🍁{}🍁", "🍂{}🍂", "🍃{}🍃",
        "🍄{}🍄", "🌰{}🌰", "🦴{}🦴", "🦷{}🦷", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴",
        "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴",
        "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴",
        "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴", "🦴{}🦴",
    ]
    
    # 500+ Art Styles
    ART_STYLES = [
        "░▒▓█{}█▓▒░", "█▀▀▀▀▀▀▀▀▀▀{}▀▀▀▀▀▀▀▀▀▀█", "╔═╗{}╔═╗", "█▶{}◀█",
        "◄{}►", "«{}»", "≪{}≫", "⋘{}⋙", "❰{}❱", "〔{}〕", "【{}】",
        "〖{}〗", "〈{}〉", "««{}»»", "≪≪{}≫≫", "▁▂▃▄▅▆▇█{}█▇▆▅▄▃▂▁",
        "░▒▓█▓▒░{}░▒▓█▓▒░", "▒▓█▓▒░{}░▒▓█▓▒", "▓█▓▒░{}░▒▓█▓", "█▓▒░{}░▒▓█",
        "▓▒░{}░▒▓", "▒░{}░▒", "░{}░", "▒{}▒", "▓{}▓", "█{}█",
        "▀▄▀▄▀▄{}▄▀▄▀▄▀", "▄▀▄▀▄▀{}▀▀▀▄▀▄", "▀█▀█▀█{}█▀█▀█▀",
        "█▀█▀█▀{}▀█▀█▀█", "▓▒▓▒▓▒{}▒▓▒▓▒▓", "▒▓▒▓▒▓{}▓▒▓▒▓▒",
        "░▓░▓░▓{}▓░▓░▓░", "▓░▓░▓░{}░▓░▓░▓", "▒░▒░▒░{}░▒░▒░▒",
        "░▒░▒░▒{}▒░▒░▒░", "█░█░█░{}░█░█░█", "░█░█░█{}█░█░█░",
        "▀░▀░▀░{}░▀░▀░▀", "░▀░▀░▀{}▀░▀░▀░", "■□■□■{}□■□■□",
        "□■□■□{}■□■□■", "●○●○●{}○●○●○", "○●○●○{}●○●○●",
        "▲△▲△▲{}△▲△▲△", "△▲△▲△{}▲△▲△▲", "▼▽▼▽▼{}▽▼▽▼▽",
        "▽▼▽▼▽{}▼▽▼▽▼", "◆◇◆◇◆{}◇◆◇◆◇", "◇◆◇◆◇{}◆◇◆◇◆",
        "★☆★☆★{}☆★☆★☆", "☆★☆★☆{}★☆★☆★", "♠♡♠♡♠{}♡♠♡♠♡",
        "♡♠♡♠♡{}♠♡♡♠♡", "♣♦♣♦♣{}♦♣♦♣♦", "♦♣♦♣♦{}♣♦♣♦♣",
        "⚫⚪⚫⚪⚫{}⚪⚫⚪⚫⚪", "⚪⚫⚪⚫⚪{}⚫⚪⚫⚪⚫",
        "⬛⬜⬛⬜⬛{}⬜⬛⬜⬛⬜", "⬜⬛⬜⬛⬜{}⬛⬜⬛⬜⬛",
        "▪️▫️▪️▫️▪️{}▫️▪️▫️▪️▫️", "▫️▪️▫️▪️▫️{}▪️▫️▪️▫️▪️",
        "◼️◻️◼️◻️◼️{}◻️◼️◻️◼️◻️", "◻️◼️◻️◼️◻️{}◼️◻️◼️◻️◼️",
        "◾◽◾◽◾{}◽◾◽◾◽", "◽◾◽◾◽{}◾◽◾◽◾",
        "🔳🔲🔳🔲🔳{}🔲🔳🔲🔳🔲", "🔲🔳🔲🔳🔲{}🔳🔲🔳🔲🔳",
        "🟥🟧🟨🟩🟦{}🟪🟫⬛⬜", "🟧🟨🟩🟦🟪{}🟫⬛⬜🟥",
        "🟨🟩🟦🟪🟫{}⬛⬜🟥🟧", "🟩🟦🟪🟫⬛{}⬜🟥🟧🟨",
        "🟦🟪🟫⬛⬜{}🟥🟧🟨🟩", "🟪🟫⬛⬜🟥{}🟧🟨🟩🟦",
        "🟫⬛⬜🟥🟧{}🟨🟩🟦🟪", "⬛⬜🟥🟧🟨{}🟩🟦🟪🟫",
        "⬜🟥🟧🟨🟩{}🟦🟪🟫⬛", "🟥🟧🟨🟩🟦{}🟪🟫⬛⬜",
        "🔴🟠🟡🟢🔵{}🟣🟤⚫⚪", "🟠🟡🟢🔵🟣{}🟤⚫⚪🔴",
        "🟡🟢🔵🟣🟤{}⚫⚪🔴🟠", "🟢🔵🟣🟤⚫{}⚪🔴🟠🟡",
        "🔵🟣🟤⚫⚪{}🔴🟠🟡🟢", "🟣🟤⚫⚪🔴{}🟠🟡🟢🔵",
        "🟤⚫⚪🔴🟠{}🟡🟢🔵🟣", "⚫⚪🔴🟠🟡{}🟢🔵🟣🟤",
        "⚪🔴🟠🟡🟢{}🔵🟣🟤⚫", "🔴🟠🟡🟢🔵{}🟣🟤⚫⚪",
        "⭕❌⭕❌⭕{}❌⭕❌⭕❌", "❌⭕❌⭕❌{}⭕❌⭕❌⭕",
        "✅❎✅❎✅{}❎✅❎✅❎", "❎✅❎✅❎{}✅❎✅❎✅",
        "☑️🔘☑️🔘☑️{}🔘☑️🔘☑️🔘", "🔘☑️🔘☑️🔘{}☑️🔘☑️🔘☑️",
        "⚪🔴⚪🔴⚪{}🔴⚪🔴⚪🔴", "🔴⚪🔴⚪🔴{}⚪🔴⚪🔴⚪",
        "🔵🟢🔵🟢🔵{}🟢🔵🟢🔵🟢", "🟢🔵🟢🔵🟢{}🔵🟢🔵🟢🔵",
        "🟡🟠🟡🟠🟡{}🟠🟡🟠🟡🟠", "🟠🟡🟠🟡🟠{}🟡🟠🟡🟠🟡",
        "🟣🟤🟣🟤🟣{}🟤🟣🟤🟣🟤", "🟤🟣🟤🟣🟤{}🟣🟤🟣🟤🟣",
        "⚫⚪⚫⚪⚫{}⚪⚫⚪⚫⚪", "⚪⚫⚪⚫⚪{}⚫⚪⚫⚪⚫",
        "⬛⬜⬛⬜⬛{}⬜⬛⬜⬛⬜", "⬜⬛⬜⬛⬜{}⬛⬜⬛⬜⬛",
    ]
    
    # Mixed Styles (Font + Decoration)
    MIXED_STYLES = []
    
    @classmethod
    def generate_mixed_styles(cls):
        """Generate mixed styles"""
        if not cls.MIXED_STYLES:
            mixed = []
            fonts = list(cls.FONTS.keys())
            decorations = cls.DECORATIVE_STYLES[:50]  # Use first 50 decorations
            
            for font in fonts[:20]:  # Use first 20 fonts
                for decor in decorations[:20]:  # Use first 20 decorations
                    mixed.append((font, decor))
            
            # Special combinations
            special_combos = [
                ('bold', '꧁{}꧂'), ('italic', '『{}』'), ('monospace', '♛{}♛'),
                ('bubble', '⚡{}⚡'), ('gothic', '【{}】'), ('double_struck', '〖{}〗'),
                ('script', '❖{}❖'), ('fraktur', '▄︻デ══━一{}一══デ︻▄'),
                ('blackboard', '╔═══✦{}✦═══╗'), ('small_caps', '┏━━━❖{}❖━━━┓'),
                ('superscript', '😈{}😈'), ('subscript', '👑{}👑'), ('outline', '🔥{}🔥'),
                ('heavy', '⚡{}⚡'), ('cursive', '✨{}✨'), ('upside_down', '🎯{}🎯'),
                ('wide', '『☆{}☆』'), ('narrow', '『★{}★』'), ('strikethrough', '『☯{}☯』'),
                ('underline', '『☬{}☬』'), ('overline', '『☠{}☠』'), ('double_underline', '『☣{}☣』'),
                ('squiggle', '『⚜{}⚜』'), ('wave', '『✠{}✠』'), ('slash', '『✧{}✧』'),
                ('x_through', '『✦{}✦』'), ('asterisk', '『❖{}❖』'), ('dot_above', '『✪{}✪』'),
                ('dot_below', '『✰{}✰』'), ('ring_above', '『❂{}❂』'), ('hook_above', '『✵{}✵』'),
                ('horn', '『✯{}✯』'), ('cedilla', '╔═══✦{}✦═══╗'), ('ogonek', '┏━━━❖{}❖━━━┓'),
                ('caron', '【†{}†】'), ('breve', '『〖{}〗』'), ('macron', '▁▂▃▄▅▆▇█{}█▇▆▅▄▃▂▁'),
                ('tilde', '░▒▓█{}█▓▒░'), ('diaeresis', '█▀▀▀▀▀▀▀▀▀▀{}▀▀▀▀▀▀▀▀▀▀█'),
                ('acute', '╔═╗{}╔═╗'), ('grave', '█▶{}◀█'), ('circumflex', '◄{}►'),
            ]
            
            cls.MIXED_STYLES = mixed + special_combos
    
    @classmethod
    def apply_font(cls, text: str, font_name: str) -> str:
        """Apply font to text"""
        if not cls.TRANSLATION_TABLES:
            cls._init_translation_tables()
        
        if font_name == 'small_caps':
            return text.translate(cls.SMALL_CAPS_FONT)
        
        table = cls.TRANSLATION_TABLES.get(font_name)
        if table:
            return text.translate(table)
        return text
    
    @classmethod
    def apply_style(cls, text: str, style_type: str, style_template: str = None) -> str:
        """Apply style to text"""
        if style_type == "font" and style_template:
            return cls.apply_font(text, style_template)
        elif style_type == "decorative" and style_template:
            return style_template.format(text)
        elif style_type == "art" and style_template:
            return style_template.format(text)
        elif style_type == "mixed" and style_template:
            font_name, decor = style_template
            font_text = cls.apply_font(text, font_name)
            return decor.format(font_text)
        return text

# ==================== TEXT STORAGE ====================
class TextStorage:
    """Fast text storage with hash"""
    _storage = {}
    
    @classmethod
    def store_text(cls, text: str) -> str:
        """Store text and return hash"""
        text_hash = hashlib.md5(text.encode()).hexdigest()[:16]
        cls._storage[text_hash] = text
        return text_hash
    
    @classmethod
    def get_text(cls, text_hash: str) -> str:
        """Get text by hash"""
        return cls._storage.get(text_hash, "")

# ==================== BOT HANDLERS ====================
class BotHandlers:
    def __init__(self):
        self.font_styles = FontStyles()
        self.text_storage = TextStorage()
        self.font_styles.generate_mixed_styles()
        self.font_styles._init_translation_tables()
    
    def apply_small_caps(self, text: str) -> str:
        """Apply small caps font"""
        return text.translate(FontStyles.SMALL_CAPS_FONT)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            user = update.effective_user
            
            # Add user to database
            await asyncio.get_event_loop().run_in_executor(
                None, Database.add_user, user.id, user.first_name, user.username
            )
            
            welcome_msg = self.apply_small_caps(
                f"✨ ᴡᴇʟᴄᴏᴍᴇ {user.first_name}! ✨\n\n"
                "🎨 sᴛʏʟɪsʜ ɴᴀᴍᴇ ʙᴏᴛ\n"
                "• 2000+ sᴛʏʟᴇs/ғᴏɴᴛs/ᴀʀᴛ\n"
                "• ғᴀsᴛ ᴘᴀɢɪɴᴀᴛɪᴏɴ\n\n"
                "👇 ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ:"
            )
            
            keyboard = [
                [InlineKeyboardButton("🎨 ᴄʀᴇᴀᴛᴇ sᴛʏʟᴇ", callback_data='create_style')],
                [InlineKeyboardButton("🎲 ʀᴀɴᴅᴏᴍ ɴᴀᴍᴇ", callback_data='random_name')],
                [InlineKeyboardButton("📊 ʙᴏᴛ sᴛᴀᴛs", callback_data='bot_stats')],
                [InlineKeyboardButton("ℹ️ ʜᴇʟᴘ", callback_data='help')]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Check if update has message or callback_query
            if update.message:
                await update.message.reply_text(welcome_msg, reply_markup=reply_markup)
            elif update.callback_query:
                await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup)
            else:
                # Fallback
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=welcome_msg,
                    reply_markup=reply_markup
                )
            
        except Exception as e:
            logger.error(f"Start command error: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=self.apply_small_caps("⚠️ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ. ᴘʟᴇᴀsᴇ ᴛʀʏ /start ᴀɢᴀɪɴ.")
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = self.apply_small_caps(
            "🎨 *sᴛʏʟɪsʜ ɴᴀᴍᴇ ʙᴏᴛ*\n\n"
            "*ᴄᴏᴍᴍᴀɴᴅs:*\n"
            "/start - sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ\n"
            "/help - sʜᴏᴡ ʜᴇʟᴘ\n"
            "/admin - ᴀᴅᴍɪɴ ᴍᴇɴᴜ\n\n"
            "*ʜᴏᴡ ᴛᴏ ᴜsᴇ:*\n"
            "1. ᴄʟɪᴄᴋ /start\n"
            "2. ᴄʜᴏᴏsᴇ 'ᴄʀᴇᴀᴛᴇ sᴛʏʟᴇ'\n"
            "3. ᴇɴᴛᴇʀ ʏᴏᴜʀ ɴᴀᴍᴇ\n"
            "4. sᴇʟᴇᴄᴛ ᴀ ᴄᴀᴛᴇɢᴏʀʏ\n"
            "5. ᴄʟɪᴄᴋ ᴏɴ ᴀɴʏ sᴛʏʟᴇ ᴛᴏ ᴄᴏᴘʏ\n\n"
            "*ɴᴏᴛᴇ:*\n"
            "• ɴᴀᴍᴇ ᴍᴀx 30 ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
            "• ᴀʟʟ sᴛʏʟᴇs sᴜᴘᴘᴏʀᴛᴇᴅ ᴏɴ ᴍᴏʙɪʟᴇ & ᴅᴇsᴋᴛᴏᴘ\n"
            "• 2000+ sᴛʏʟᴇs ᴀᴠᴀɪʟᴀʙʟᴇ"
        )
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command"""
        user = update.effective_user
        
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("⛔ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ.")
            return
        
        admin_text = self.apply_small_caps(
            "👑 *ᴀᴅᴍɪɴ ᴍᴇɴᴜ*\n\n"
            "*ᴄᴏᴍᴍᴀɴᴅs:*\n"
            "/stats - sʜᴏᴡ ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n"
            "/broadcast - sᴇɴᴅ ᴍᴇssᴀɢᴇ ᴛᴏ ᴀʟʟ ᴜsᴇʀs\n"
            "/users - sʜᴏᴡ ᴜsᴇʀ ʟɪsᴛ\n\n"
            "*ɪɴsᴛʀᴜᴄᴛɪᴏɴs:*\n"
            "ғᴏʀ ʙʀᴏᴀᴅᴄᴀsᴛ:\n"
            "1. ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ\n"
            "2. ᴛʏᴘᴇ /broadcast\n"
            "ᴏʀ\n"
            "ᴛʏᴘᴇ: /broadcast ʏᴏᴜʀ ᴍᴇssᴀɢᴇ"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data='admin_stats')],
            [InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀsᴛ", callback_data='admin_broadcast')],
            [InlineKeyboardButton("👥 ᴜsᴇʀs", callback_data='admin_users')],
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    async def ask_for_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask for name"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            self.apply_small_caps("✍️ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ʏᴏᴜʀ ɴᴀᴍᴇ:"),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def process_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process name input"""
        name = update.message.text.strip()
        
        if len(name) > MAX_NAME_LENGTH:
            await update.message.reply_text(
                self.apply_small_caps(f"⚠️ ɴᴀᴍᴇ ᴛᴏᴏ ʟᴏɴɢ! ᴍᴀx {MAX_NAME_LENGTH} ᴄʜᴀʀs.")
            )
            return
        
        if not name:
            await update.message.reply_text(self.apply_small_caps("⚠️ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴀᴍᴇ."))
            return
        
        context.user_data['name'] = name
        
        keyboard = [
            [InlineKeyboardButton("🎭 ᴅᴇᴄᴏʀᴀᴛɪᴠᴇ (1000+)", callback_data='cat_decorative')],
            [InlineKeyboardButton("🔤 ғᴏɴᴛs (50+)", callback_data='cat_fonts')],
            [InlineKeyboardButton("🎨 ᴀʀᴛ (500+)", callback_data='cat_art')],
            [InlineKeyboardButton("🌀 ᴍɪxᴇᴅ (500+)", callback_data='cat_mixed')],
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            self.apply_small_caps(f"✅ ɴᴀᴍᴇ: `{name}`\n\n👇 sᴇʟᴇᴄᴛ ᴄᴀᴛᴇɢᴏʀʏ:"),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_category_styles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show styles for category"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        name = context.user_data.get('name', '')
        
        if not name:
            await query.edit_message_text(self.apply_small_caps("⚠️ ɴᴏ ɴᴀᴍᴇ ғᴏᴜɴᴅ."))
            return
        
        category_map = {
            'cat_decorative': ('decorative', FontStyles.DECORATIVE_STYLES),
            'cat_fonts': ('fonts', list(FontStyles.FONTS.keys())),
            'cat_art': ('art', FontStyles.ART_STYLES),
            'cat_mixed': ('mixed', FontStyles.MIXED_STYLES)
        }
        
        if data not in category_map:
            return
        
        category, styles = category_map[data]
        context.user_data['current_category'] = category
        context.user_data['current_styles'] = styles
        context.user_data['current_page'] = 1
        
        await self.show_styles_page(update, context)
    
    async def show_styles_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
        """Show styles page"""
        query = update.callback_query if hasattr(update, 'callback_query') else None
        if query:
            await query.answer()
        
        name = context.user_data.get('name', '')
        category = context.user_data.get('current_category', '')
        styles = context.user_data.get('current_styles', [])
        
        if not name:
            return await self.start_command(update, context)
        
        if page:
            context.user_data['current_page'] = page
        else:
            page = context.user_data.get('current_page', 1)
        
        total = len(styles)
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(1, min(page, total_pages))
        
        start = (page - 1) * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        page_styles = styles[start:end]
        
        # Generate buttons
        buttons = []
        for i, style in enumerate(page_styles, 1):
            styled_text = self._generate_styled_text(name, category, style)
            text_hash = TextStorage.store_text(styled_text)
            
            btn_text = f"{i}. {styled_text[:15]}..." if len(styled_text) > 15 else f"{i}. {styled_text}"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"copy_{text_hash}")])
        
        # Pagination
        pagination_buttons = []
        if page > 1:
            pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
        
        pagination_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data='current_page'))
        
        if page < total_pages:
            pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
        
        if pagination_buttons:
            buttons.append(pagination_buttons)
        
        # Navigation
        nav_buttons = [
            InlineKeyboardButton("🔄 ᴄʜᴀɴɢᴇ", callback_data='change_category'),
            InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start'),
            InlineKeyboardButton("✏️ ɴᴇᴡ", callback_data='new_name')
        ]
        buttons.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        category_names = {
            'decorative': "🎭 ᴅᴇᴄᴏʀᴀᴛɪᴠᴇ",
            'fonts': "🔤 ғᴏɴᴛs",
            'art': "🎨 ᴀʀᴛ",
            'mixed': "🌀 ᴍɪxᴇᴅ"
        }
        
        category_display = category_names.get(category, category)
        
        message_text = self.apply_small_caps(
            f"📝 ɴᴀᴍᴇ: `{name}`\n"
            f"📂 ᴄᴀᴛᴇɢᴏʀʏ: {category_display}\n"
            f"📊 ᴛᴏᴛᴀʟ: {total}\n"
            f"📄 ᴘᴀɢᴇ: {page}/{total_pages}\n\n"
            "👇 ᴄʟɪᴄᴋ:"
        )
        
        if query:
            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    def _generate_styled_text(self, name: str, category: str, style) -> str:
        """Generate styled text"""
        if category == 'fonts':
            return FontStyles.apply_font(name, style)
        elif category == 'decorative':
            return style.format(name)
        elif category == 'art':
            return style.format(name)
        elif category == 'mixed':
            font_name, decor = style
            font_text = FontStyles.apply_font(name, font_name)
            return decor.format(font_text)
        return name
    
    async def handle_pagination(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pagination"""
        query = update.callback_query
        data = query.data
        
        if data.startswith('page_'):
            page = int(data.split('_')[1])
            await self.show_styles_page(update, context, page)
    
    async def copy_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Copy text handler"""
        query = update.callback_query
        data = query.data
        
        if data.startswith('copy_'):
            text_hash = data[5:]
            text_to_copy = TextStorage.get_text(text_hash)
            
            if text_to_copy:
                # Save to database in background
                user_id = query.from_user.id
                name = context.user_data.get('name', '')
                category = context.user_data.get('current_category', '')
                
                await asyncio.get_event_loop().run_in_executor(
                    None, Database.save_style, user_id, name, text_to_copy, category
                )
                
                # Send copy-able text
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"```\n{text_to_copy}\n```",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                
                await query.answer(self.apply_small_caps("✅ sᴛʏʟɪsʜ ɴᴀᴍᴇ sᴇɴᴛ ᴀs ᴀ ᴍᴇssᴀɢᴇ ʙᴇʟᴏᴡ. ᴄᴏᴘʏ ᴀɴᴅ ᴘᴀsᴛᴇ ᴀɴʏᴡʜᴇʀᴇ ʏᴏᴜ ᴡᴀɴᴛ!"), show_alert=True)
            else:
                await query.answer(self.apply_small_caps("⚠️ ᴛᴇxᴛ ɴᴏᴛ ғᴏᴜɴᴅ"), show_alert=True)
    
    async def generate_random_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate random names"""
        query = update.callback_query
        await query.answer()
        
        first_parts = ["Shadow", "Dark", "Neo", "Royal", "Crimson", "Ghost", "Night", "Demon", 
                      "Cyber", "Steel", "Iron", "Golden", "Silver", "Phantom", "Mystic"]
        second_parts = ["Killer", "Hunter", "Rider", "Warrior", "Slayer", "Assassin", "Master", 
                       "Lord", "King", "Queen", "Prince", "Legend", "Hero", "Ninja", "Samurai"]
        
        await query.edit_message_text(self.apply_small_caps("🎲 ɢᴇɴᴇʀᴀᴛɪɴɢ..."))
        
        for i in range(5):
            name = f"{random.choice(first_parts)}{random.choice(second_parts)}{random.randint(1, 99)}"
            
            categories = ['decorative', 'fonts', 'art', 'mixed']
            category = random.choice(categories)
            
            if category == 'decorative':
                style = random.choice(FontStyles.DECORATIVE_STYLES)
                styled_text = style.format(name)
            elif category == 'fonts':
                font = random.choice(list(FontStyles.FONTS.keys()))
                styled_text = FontStyles.apply_font(name, font)
            elif category == 'art':
                style = random.choice(FontStyles.ART_STYLES)
                styled_text = style.format(name)
            else:
                font = random.choice(list(FontStyles.FONTS.keys()))
                decor = random.choice(FontStyles.DECORATIVE_STYLES)
                styled_text = decor.format(FontStyles.apply_font(name, font))
            
            text_hash = TextStorage.store_text(styled_text)
            
            keyboard = [[InlineKeyboardButton("📋 ᴄʟɪᴄᴋ", callback_data=f"copy_{text_hash}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=self.apply_small_caps(f"🎲 ɴᴀᴍᴇ #{i+1}:\n`{styled_text}`"),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        
        keyboard = [[InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=self.apply_small_caps("✅ 5 ʀᴀɴᴅᴏᴍ ɴᴀᴍᴇs ɢᴇɴᴇʀᴀᴛᴇᴅ!"),
            reply_markup=reply_markup
        )
    
    async def show_bot_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot stats"""
        query = update.callback_query
        await query.answer()
        
        user_count = await asyncio.get_event_loop().run_in_executor(None, Database.get_user_count)
        
        stats_text = self.apply_small_caps(
            f"📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n\n"
            f"👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs: {user_count}\n"
            f"🎨 sᴛʏʟᴇ ᴄᴀᴛᴇɢᴏʀɪᴇs: 4\n"
            f"✨ ᴛᴏᴛᴀʟ sᴛʏʟᴇs: 2000+\n"
            f"• ᴅᴇᴄᴏʀᴀᴛɪᴠᴇ: 1000+\n"
            f"• ғᴏɴᴛs: 50+\n"
            f"• ᴀʀᴛ: 500+\n"
            f"• ᴍɪxᴇᴅ: 500+\n\n"
            f"🚀 ʙᴏᴛ sᴛᴀᴛᴜs: ᴀᴄᴛɪᴠᴇ"
        )
        
        keyboard = [[InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
    
    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle navigation"""
        query = update.callback_query
        data = query.data
        await query.answer()
        
        if data == 'back_to_start':
            await self.start_command(update, context)
        elif data == 'change_category':
            await self.show_category_menu(update, context)
        elif data == 'new_name':
            await self.ask_for_name(update, context)
    
    async def show_category_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show category menu"""
        query = update.callback_query
        await query.answer()
        
        name = context.user_data.get('name', 'ɴᴏ ɴᴀᴍᴇ')
        
        keyboard = [
            [InlineKeyboardButton("🎭 ᴅᴇᴄᴏʀᴀᴛɪᴠᴇ (1000+)", callback_data='cat_decorative')],
            [InlineKeyboardButton("🔤 ғᴏɴᴛs (50+)", callback_data='cat_fonts')],
            [InlineKeyboardButton("🎨 ᴀʀᴛ (500+)", callback_data='cat_art')],
            [InlineKeyboardButton("🌀 ᴍɪxᴇᴅ (500+)", callback_data='cat_mixed')],
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            self.apply_small_caps(f"📝 ɴᴀᴍᴇ: `{name}`\n\n👇 sᴇʟᴇᴄᴛ ᴄᴀᴛᴇɢᴏʀʏ:"),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Admin handlers
    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin stats"""
        query = update.callback_query
        await query.answer()
        
        user_count = await asyncio.get_event_loop().run_in_executor(None, Database.get_user_count)
        
        stats_text = self.apply_small_caps(
            f"👑 ᴀᴅᴍɪɴ sᴛᴀᴛs\n\n"
            f"👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs: {user_count}\n"
            f"📅 ʙᴏᴛ ᴜᴘᴛɪᴍᴇ: ᴀᴄᴛɪᴠᴇ\n"
            f"💾 ᴅᴀᴛᴀʙᴀsᴇ: sᴛʏʟɪsʜ_ɴᴀᴍᴇ_ʙᴏᴛ.ᴅʙ\n"
            f"⚡ ᴘᴇʀғᴏʀᴍᴀɴᴄᴇ: ᴏᴘᴛɪᴍɪᴢᴇᴅ\n"
            f"🎨 sᴛʏʟᴇs ᴀᴠᴀɪʟᴀʙʟᴇ: 2000+"
        )
        
        keyboard = [
            [InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀsᴛ", callback_data='admin_broadcast')],
            [InlineKeyboardButton("👥 ᴜsᴇʀ ʟɪsᴛ", callback_data='admin_users')],
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_text, reply_markup=reply_markup)
    
    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin broadcast"""
        query = update.callback_query
        await query.answer()
        
        broadcast_text = self.apply_small_caps(
            "📢 *ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇɴᴜ*\n\n"
            "*ɪɴsᴛʀᴜᴄᴛɪᴏɴs:*\n"
            "ᴛᴏ sᴇɴᴅ ʙʀᴏᴀᴅᴄᴀsᴛ:\n"
            "1. ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ\n"
            "2. ᴛʏᴘᴇ /broadcast\n"
            "\nᴏʀ\n"
            "\nᴛʏᴘᴇ: /broadcast ʏᴏᴜʀ ᴍᴇssᴀɢᴇ\n\n"
            "*ɴᴏᴛᴇ:*\n"
            "• ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ʙʀᴏᴀᴅᴄᴀsᴛ\n"
            "• ᴜsᴇ ᴡɪsᴇʟʏ\n"
            "• ᴅᴏɴ'ᴛ sᴘᴀᴍ"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')],
            [InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data='admin_stats')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(broadcast_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    async def admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin users"""
        query = update.callback_query
        await query.answer()
        
        users = await asyncio.get_event_loop().run_in_executor(None, Database.get_all_users)
        
        if not users:
            await query.edit_message_text(self.apply_small_caps("📭 ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ."))
            return
        
        users_text = self.apply_small_caps(f"👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs: {len(users)}\n\n")
        
        for i, user_id in enumerate(users[:10], 1):
            users_text += f"{i}. `{user_id}`\n"
        
        if len(users) > 10:
            users_text += f"\n... ᴀɴᴅ {len(users) - 10} ᴍᴏʀᴇ\n"
        
        keyboard = [[InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data='back_to_start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(users_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ==================== ADMIN COMMANDS ====================
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ.")
        return
    
    bot_handlers = BotHandlers()
    user_count = await asyncio.get_event_loop().run_in_executor(None, Database.get_user_count)
    
    stats_text = bot_handlers.apply_small_caps(
        f"📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n\n"
        f"👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs: {user_count}\n"
        f"⚡ ʙᴏᴛ sᴛᴀᴛᴜs: ᴀᴄᴛɪᴠᴇ\n"
        f"💾 ᴅᴀᴛᴀʙᴀsᴇ: ᴏᴘᴇʀᴀᴛɪᴏɴᴀʟ\n"
        f"🎨 sᴛʏʟᴇs: 2000+\n"
        f"🚀 ᴘᴇʀғᴏʀᴍᴀɴᴄᴇ: ᴏᴘᴛɪᴍɪᴢᴇᴅ"
    )
    
    await update.message.reply_text(stats_text)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ.")
        return
    
    # Check if replying to message
    if update.message.reply_to_message:
        message = update.message.reply_to_message.text or update.message.reply_to_message.caption
        if not message:
            await update.message.reply_text("⚠️ ɴᴏ ᴛᴇxᴛ ɪɴ ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ.")
            return
    elif context.args:
        message = " ".join(context.args)
    else:
        await update.message.reply_text("⚠️ ᴜsᴀɢᴇ: /broadcast <ᴍᴇssᴀɢᴇ> ᴏʀ ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇssᴀɢᴇ.")
        return
    
    users = await asyncio.get_event_loop().run_in_executor(None, Database.get_all_users)
    total = len(users)
    
    if total == 0:
        await update.message.reply_text("📭 ɴᴏ ᴜsᴇʀs ᴛᴏ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ.")
        return
    
    await update.message.reply_text(f"📢 ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ ᴛᴏ {total} ᴜsᴇʀs...")
    
    success = 0
    failed = 0
    
    bot_handlers = BotHandlers()
    broadcast_msg = f"📢 *ʙʀᴏᴀᴅᴄᴀsᴛ:*\n\n{message}"
    
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=broadcast_msg,
                parse_mode=ParseMode.MARKDOWN
            )
            success += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ᴛᴏ {user_id}: {e}")
            failed += 1
    
    result_text = bot_handlers.apply_small_caps(
        f"✅ ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇ!\n"
        f"✓ sᴜᴄᴄᴇss: {success}\n"
        f"✗ ғᴀɪʟᴇᴅ: {failed}\n"
        f"📊 ᴛᴏᴛᴀʟ: {total}"
    )
    
    await update.message.reply_text(result_text)

# ==================== ERROR HANDLER ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    error_msg = str(context.error) if context.error else "Unknown error"
    logger.error(f"ᴇʀʀᴏʀ: {error_msg}")

# ==================== MAIN FUNCTION ====================
def main():
    """Main function"""

    # Initialize database
    Database.setup()

    # Create bot
    bot_handlers = BotHandlers()

    # Create application
    application = Application.builder().token(TOKEN).build()

    # Add error handler
    application.add_error_handler(error_handler)

    # Add command handlers
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("admin", bot_handlers.admin_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(bot_handlers.ask_for_name, pattern='^create_style$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.generate_random_name, pattern='^random_name$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.show_bot_stats, pattern='^bot_stats$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.help_command, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.show_category_styles, pattern='^cat_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_pagination, pattern='^page_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.copy_text, pattern='^copy_'))
    application.add_handler(CallbackQueryHandler(bot_handlers.handle_navigation, pattern='^(back_to_start|new_name|change_category)$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.admin_stats, pattern='^admin_stats$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.admin_broadcast, pattern='^admin_broadcast$'))
    application.add_handler(CallbackQueryHandler(bot_handlers.admin_users, pattern='^admin_users$'))

    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.process_name))
        
    # Start the bot
    logger.info("🤖 Bot is starting...")
    logger.info("📡 Press Ctrl+C to stop")

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Bot is alive!')

        def log_message(self, format, *args):
            pass  # Silence logs

    def run_health_server():
        port = int(os.environ.get("PORT", 10000))
        httpd = HTTPServer(('0.0.0.0', port), HealthHandler)
        logger.info(f"✅ Health server on port {port}")
        httpd.serve_forever()
    
        # Start health server
        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
    
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
        )
        
if __name__ == '__main__':
    main()