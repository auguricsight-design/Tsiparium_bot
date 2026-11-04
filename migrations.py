from datetime import datetime, timezone

def add_missing_columns(db, table_name, columns):
    existing_columns = {
        row["name"]
        for row in db.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }

    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            db.execute(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} {column_type}"
            )


def migrate_games_table(db):
    add_missing_columns(
        db,
        "games",
        {
            "start_at": "TEXT",
            "finish_at": "TEXT",
            "author": "TEXT",
            "author_user_id": "INTEGER",
            "prizes": "TEXT",
            "hashtag": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "created_at": "TEXT",
        },
    )



CHAT_RULES = 'Правила чату\n\n1. Зайшов — привітайся, будь чемним і умнічкою.\n\n2. Цей чат — про гумор, вишивку і балабольство. Ми не носимо сюди:\n— гіфки, картіночки і всякі привітання зі святами вайбер-стайл. Зі святами вітати можна і текстово;\n— новини (окрім ну дуууужжеее ржачних відосиків, ну прям раз на місяць-два);\n— виписки і фото з медичних і дотичних тем. Дитячі розмови та поради теж, будь ласка, дуже дозовано. Говорити про виховання і цікаві моменти — можна. Обговорювати соплі, памперси — ні.\n\n3. Не сремось за мову. Тут це заборонено в будь-якому прояві.\n\n4. Пишемо хоча б раз на три місяці. Якщо активності не буде, я видалю з чату, вибачте. Один раз на три місяці скинути фоточку процесу — це не страшно і не боляче, а ми ще й лайків насиплемо.\n\n5. Кидати посилання на ютубчики й інстаграм можна. Тіки не нагло. Тобто формат «оце моя сторінка і мій канал» — можна. Раз на тиждень «ПІДПИСУЙТЕСЬ НА МЕНЕ!!! ААДИИН АДИИНН» — видалю, аж вхурделить слідом. Те саме стосується продажів і реклами. Але найкраще — спитати в особисті в адміністрації чату дозволу.\n\n6. Не розповсюджуємо платні схеми. Ніяк. Ваще ніяк. Нічиї.\n\n7. Поважаєм слово диктатора, в спину не плюєм. Якщо дуже хочеться — можна спробувать в обличчя. Цей чат частково створювався на добровільній цензурі й виявився дуже затишним. Тому раз на рік я, буває, таки видаляю кілька повідомлень і даю по шапці. Я стараюсь так робити нечасто, але право за собою лишаю.\n\n8. Флуд теж не особливо привічається. Що мається на увазі під флудом: не треба переписуватись самі з собою. Якщо ви бачите, що тема не заходить у чаті, ніхто не відповідає чи вона відверто неприємна більшості — згортайтесь самі.\n\n9. У чаті всі на «ти» :) Додавання до чату автоматично вважається випивкою на брудершафт чи шо там за традиції цьому супутні…\n\n10. Грошові питання та накрути голосів також прошу вирішувати поза чатом. Дуже рідкі винятки — через консультацію з диктатором.\n\n11. Прямі і «не дуже прямі, але всім всьо ясно» образи в бік учасників чату заборонені. За конфліктну поведінку і підбурювання до срачів виноситься попередження. Якщо висновки не робляться — винос із чату.\n\n12. Як диктатор, лишаю за собою право сама обирати в разі порушення правил: винести попередження, зам’ютивши право писати на певний час, чи відразу видалити з чату.\n\n13. У чаті постійно граємо в ігри. У боті є вся інформація про активні ігри та ліміт одночасних активностей. Одно-дводенні інтерактиви не лімітуються, мова йде тільки про ігри чи активності довжиною від місяця.\n\n14. Приводити друзів — можна, але ви маєте розуміти, чи впишеться людина в чат, чи ні. Не приводьте тих, щодо кого є сумніви — це закінчиться видаленням людини.\n\n15. НЕ МОЖНА ЗЛИВАТИ СКРІНИ З ЧАТУ. Якщо є якесь обговорення, яке вас обурює, і вам дуже хочеться підключити когось до цього обговорення — майте сміливість додати цю людину в чат. Чат не закрита спільнота. Якщо сміливості нема — не грайте в крису, не зливайте скріни, які потім обов’язково будуть вирвані з контексту і приведуть до таких наслідків, про які ви навіть не почухались подумать. Також за злиття скрінів видаляю без попереджень.\n\nРЕКОМЕНДАЦІЯ: Знімайте з плити їжу, перш ніж зайти в чат «почитати, шо бабоньки пишуть», бо можна лишитись без хати.'


def seed_static_content(db):
    db.execute(
        """
        INSERT OR IGNORE INTO static_content (
            key,
            content,
            updated_at
        )
        VALUES (?, ?, ?)
        """,
        (
            "ciparules",
            CHAT_RULES,
            datetime.now(timezone.utc).isoformat(),
        ),
    )



CIPAINFO_WISHLIST = '🎁 Забаганки ціпочок можна знайти тут:\nhttps://docs.google.com/spreadsheets/d/1MYFQi9W-pLmbdOWPqAvuqOn_JLQC6C-PpIVspbNXrKo/edit?gid=0#gid=0\n\nВішліст може редагувати будь-який учасник чату, тож додавайте свої дні народження та забаганки!'
CIPAINFO_YOUTUBE = 'Ютуб канали учасниць чату\n\nOlga Dmytrenko @Shalkara\nhttps://youtube.com/@crossesandtails\n\nНата Носова @Nata_Nosova\nhttps://youtube.com/@natastichstory\n\nМария @maria_with_embroidery\nhttps://youtube.com/@mariawithembroidery2898\n\nIrina (Kiev) Shtanko\nhttps://youtube.com/@luckystitch4797\n\nМарго Маргарита\nhttps://youtube.com/@MargoStitch\n\nNina Duyunova Nina\nhttps://youtube.com/@NinaDuyunova\n\nLiza Goncharova Liza\nhttps://youtube.com/@LizaHoncharova\n\nСвітлана Петрова @svitpet01\nhttps://youtube.com/@svitlana_petrova?si=nLX5_QBI0dTgApOp\n\nАлёна Гончарь Алёна Гончарь\nhttps://youtube.com/@alena.gonchar\n\nMaria Maria\nhttps://www.youtube.com/@lazy_stitcher/videos\n\nKristinLavransdatter @KristinLavransdatter\nhttps://youtube.com/@slowcrossstitch?si=nXpKqO3GYFE8wb1J\n\nИрина @inarmiel\nhttps://www.youtube.com/@INarmiel/featured\n\n@tetyana_kulik Тетяна Кулик\nhttps://youtube.com/@rainbow_crosses_with_Tatyana?si=Bl50My7tt4blLAH1\n\nВікторія RutaStitch\nhttps://youtube.com/@rutastitch?si=o9IY-PRJEMng4Gop\n\nAlla Алла Бондар\nhttps://youtube.com/@allabondar?si=yuoGRpX99ik1ZsYU\n\n@m_maruse4ka_m Марина\nhttps://youtube.com/@m.mari.no4ka?feature=shared\n\nLiza Liza Auchyieva\nhttps://youtube.com/channel/UC4BsWHk__7DsSXxHdxW5FvQ?si=ukYAt_gBrR0EH_Xy\n\nTetiana Dovhanych @oddigrid\nhttps://youtube.com/@dovganich8840?si=JaUl2eHIy0qmLZlT\n\nТаня (Созвездие крестиков)\nhttps://www.youtube.com/@sozvezdiekrestikov'

CIPAINFO_THREADS = "🧵 Наші додаткові тематичні групи:\n\nВишиті сорочки\nhttps://t.me/+Lc0hwfsJnDI5NDEy\n\nЦіпи і серіали\nhttps://t.me/+k8XyU7v-ej8yMTgy\n\nСпорт і Ціпи\nhttps://t.me/+UlVRjrTKHbMxY2Q6\n\nВ'язальний чат\nhttps://t.me/+tCYzmI6cXhQ0MzVi\n\nКнижковий чат\nhttps://t.me/+-4YdtuE3Cao2OTcy\n\nРозхом'ячка для учасників чату\nhttps://t.me/+VW_T6VYjU1hmYjIy"


CIPAINFO_DESIGNERS = '🎨 Наші ціпи-дизайнери:\n\nKerry\nhttps://www.instagram.com/kerry_embroidery/\n\nKomod\nhttps://www.instagram.com/komod.for.you/\n\nМіла та Катя\nhttps://www.instagram.com/mika__mila_katya/'


CIPAINFO_THREADS_PLACEHOLDERS = ['🧵 Тематичні гілки чату поки порожні.', '🧵 Тематичні гілки чату поки не заповнені.']
CIPAINFO_DESIGNERS_PLACEHOLDERS = ["🎨 Список ціп-дизайнерів скоро з'явиться тут."]


def seed_cipainfo_content(db):
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        ("cipainfo_wishlist", CIPAINFO_WISHLIST, now),
        ("cipainfo_youtube", CIPAINFO_YOUTUBE, now),
        ("cipainfo_threads", CIPAINFO_THREADS, now),
        ("cipainfo_designers", CIPAINFO_DESIGNERS, now),
    ]
    db.executemany(
        """
        INSERT OR IGNORE INTO static_content (key, content, updated_at)
        VALUES (?, ?, ?)
        """,
        rows,
    )

    db.execute(
        """
        UPDATE static_content
        SET content = ?, updated_at = ?
        WHERE key = ?
          AND content = ?
        """,
        (
            CIPAINFO_WISHLIST,
            now,
            "cipainfo_wishlist",
            '🎁 Вішліст чату поки порожній.',
        ),
    )

    db.execute(
        """
        UPDATE static_content
        SET content = ?, updated_at = ?
        WHERE key = ?
          AND content = ?
        """,
        (
            CIPAINFO_THREADS,
            now,
            "cipainfo_threads",
            '🧵 Тематичні гілки чату поки порожні.',
        ),
    )


    for placeholder in CIPAINFO_THREADS_PLACEHOLDERS:
        db.execute(
            """
            UPDATE static_content
            SET content = ?, updated_at = ?
            WHERE key = ?
              AND content = ?
            """,
            (
                CIPAINFO_THREADS,
                now,
                "cipainfo_threads",
                placeholder,
            ),
        )

    for placeholder in CIPAINFO_DESIGNERS_PLACEHOLDERS:
        db.execute(
            """
            UPDATE static_content
            SET content = ?, updated_at = ?
            WHERE key = ?
              AND content = ?
            """,
            (
                CIPAINFO_DESIGNERS,
                now,
                "cipainfo_designers",
                placeholder,
            ),
        )


def run_migrations(db):
    migrate_games_table(db)
    seed_static_content(db)
    seed_cipainfo_content(db)
