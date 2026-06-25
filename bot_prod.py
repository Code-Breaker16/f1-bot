import discord
from discord.ext import commands
from discord.ui import View, Select, Button
from dotenv import load_dotenv
import os
import psycopg2

# ---------------- TOKEN ----------------
load_dotenv()

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------- DATABASE ----------------
conn = psycopg2.connect(DATABASE_URL)
c = conn.cursor()

def check_db():
    global conn, c

    try:
        c.execute("SELECT 1")
    except:
        conn = psycopg2.connect(DATABASE_URL)
        c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    user_id TEXT,
    race TEXT,
    pole TEXT,
    p1 TEXT,
    p2 TEXT,
    p3 TEXT,
    PRIMARY KEY(user_id, race)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS races (
    race TEXT PRIMARY KEY,
    status TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS current_race (
    id INTEGER PRIMARY KEY,
    race TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS scores (
    user_id TEXT PRIMARY KEY,
    points INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS drivers (
    name TEXT PRIMARY KEY
)
""")

# ---------------- 2026 GRID ----------------
drivers_list = [
    "Lewis Hamilton","Charles Leclerc",
    "Max Verstappen","Isack Hadjar",
    "George Russell","Kimi Antonelli",
    "Lando Norris","Oscar Piastri",
    "Fernando Alonso","Lance Stroll",
    "Pierre Gasly","Franco Colapinto",
    "Esteban Ocon","Oliver Bearman",
    "Alexander Albon","Carlos Sainz",
    "Nico Hülkenberg","Gabriel Bortoleto",
    "Liam Lawson","Arvid Lindblad",
    "Sergio Pérez","Valtteri Bottas"
]

for d in drivers_list:
    c.execute("""
    INSERT INTO drivers (name)
    VALUES (%s)
    ON CONFLICT (name) DO NOTHING
    """, (d,))

conn.commit()

# ---------------- BOT ----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands")
    print(f"Logged in as {bot.user}")

# ---------------- HELPERS ----------------
def get_current_race():
    c.execute(
        "SELECT race FROM current_race WHERE id=1"
    )

    r = c.fetchone()

    return r[0] if r else None


def get_drivers():
    c.execute(
        "SELECT name FROM drivers"
    )

    return [r[0] for r in c.fetchall()]


def calculate(pred, res):

    points = 0

    if pred[0] == res["pole"]:
        points += 3

    if pred[1] == res["p1"]:
        points += 5

    if pred[2] == res["p2"]:
        points += 3

    if pred[3] == res["p3"]:
        points += 3

    if (
        pred[1] == res["p1"]
        and pred[2] == res["p2"]
        and pred[3] == res["p3"]
    ):
        points += 5

    return points


# ---------------- PREDICT UI ----------------
class PredictView(View):

    def __init__(self, race, user_id):

        super().__init__(timeout=120)

        self.race = race
        self.user_id = user_id

        self.data = {
            "pole": None,
            "p1": None,
            "p2": None,
            "p3": None
        }

        drivers = get_drivers()

        options = [
            discord.SelectOption(
                label=d,
                value=d
            )
            for d in drivers
        ]

        self.pole = Select(
            placeholder="Pole Position",
            options=options
        )

        self.p1 = Select(
            placeholder="P1",
            options=options
        )

        self.p2 = Select(
            placeholder="P2",
            options=options
        )

        self.p3 = Select(
            placeholder="P3",
            options=options
        )

        self.pole.callback = self.cb_pole
        self.p1.callback = self.cb_p1
        self.p2.callback = self.cb_p2
        self.p3.callback = self.cb_p3

        self.add_item(self.pole)
        self.add_item(self.p1)
        self.add_item(self.p2)
        self.add_item(self.p3)

        self.add_item(self.submit_button())

    async def cb_pole(self, i):
        self.data["pole"] = self.pole.values[0]
        await i.response.defer()

    async def cb_p1(self, i):
        self.data["p1"] = self.p1.values[0]
        await i.response.defer()

    async def cb_p2(self, i):
        self.data["p2"] = self.p2.values[0]
        await i.response.defer()

    async def cb_p3(self, i):
        self.data["p3"] = self.p3.values[0]
        await i.response.defer()

    def submit_button(self):

        btn = Button(
            label="Submit Prediction",
            style=discord.ButtonStyle.green
        )

        async def cb(i):
            
            check_db()

            race = self.race

            if None in self.data.values():
                return await i.response.send_message(
                    "❌ Complete all selections",
                    ephemeral=True
                )

            # Prevent duplicate podium positions
            drivers = [
                self.data["p1"],
                self.data["p2"],
                self.data["p3"]
            ]

            if len(drivers) != len(set(drivers)):
                return await i.response.send_message(
                    "❌ P1, P2 and P3 must be different drivers",
                    ephemeral=True
                    )

            c.execute(
                "SELECT status FROM races WHERE race=%s",
                (race,)
            )

            r = c.fetchone()

            if not r or r[0] != "open":
                return await i.response.send_message(
                    "❌ Race closed",
                    ephemeral=True
                )

            c.execute(
                """
                SELECT *
                FROM predictions
                WHERE user_id=%s
                AND race=%s
                """,
                (
                    self.user_id,
                    race
                )
            )

            if c.fetchone():
                return await i.response.send_message(
                    "❌ Already submitted",
                    ephemeral=True
                )

            c.execute("""
            INSERT INTO predictions
            VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                self.user_id,
                race,
                self.data["pole"],
                self.data["p1"],
                self.data["p2"],
                self.data["p3"]
            ))

            conn.commit()

            await i.response.send_message(
                "🏁 Prediction saved!",
                ephemeral=True
            )

        btn.callback = cb

        return btn
# ---------------- /PREDICT ----------------
@bot.tree.command(name="predict")
async def predict(i: discord.Interaction):
    
    check_db()

    race = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No active race set",
            ephemeral=True
        )

    await i.response.send_message(
        f"🏁 Current Race: **{race}**",
        view=PredictView(
            race,
            str(i.user.id)
        ),
        ephemeral=True
    )

# ---------------- ADMIN: SET CURRENT RACE ----------------
@bot.tree.command(name="setcurrent")
async def setcurrent(
    i: discord.Interaction,
    race: str
):
    check_db()

    allowed_role = discord.utils.get(
        i.user.roles,
        name="MODs"
    )

    if not (
        i.user.guild_permissions.administrator
        or allowed_role
    ):
        return await i.response.send_message(
            "No permission",
            ephemeral=True
        )

    c.execute("""
    INSERT INTO current_race (id, race)
    VALUES (1, %s)
    ON CONFLICT (id)
    DO UPDATE SET race = EXCLUDED.race
    """, (race.upper(),))

    conn.commit()

    await i.response.send_message(
        f"🏁 Current race set: {race.upper()}"
    )

# ---------------- OPEN RACE ----------------
@bot.tree.command(name="openrace")
async def openrace(i: discord.Interaction):
    
    check_db()

    allowed_role = discord.utils.get(
        i.user.roles,
        name="MODs"
    )

    if not (
        i.user.guild_permissions.administrator
        or allowed_role
    ):
        return await i.response.send_message(
            "No permission",
            ephemeral=True
        )

    race = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No current race set",
            ephemeral=True
        )
    
    c.execute("""
    INSERT INTO races (race, status)
    VALUES (%s, 'open')
    ON CONFLICT (race)
    DO UPDATE SET status='open'
    """, (race,))

    conn.commit()

    await i.response.send_message(
        f"🏁 {race} OPENED"
    )

# ---------------- CLOSE RACE ----------------
@bot.tree.command(name="closerace")
async def closerace(i: discord.Interaction):
    
    check_db()

    allowed_role = discord.utils.get(
        i.user.roles,
        name="MODs"
    )

    if not (
        i.user.guild_permissions.administrator
        or allowed_role
    ):
        return await i.response.send_message(
            "No permission",
            ephemeral=True
        )

    race = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No current race set",
            ephemeral=True
        )

    c.execute("""
    INSERT INTO races (race, status)
    VALUES (%s, 'closed')
    ON CONFLICT (race)
    DO UPDATE SET status='closed'
    """, (race,))

    conn.commit()

    await i.response.send_message(
        f"🔒 {race} CLOSED"
    )

# ---------------- SET RESULTS UI ----------------
class ResultView(View):

    def __init__(self, race):

        super().__init__(timeout=180)

        self.race = race

        self.data = {
            "pole": None,
            "p1": None,
            "p2": None,
            "p3": None
        }

        drivers = get_drivers()

        options = [
            discord.SelectOption(
                label=d,
                value=d
            )
            for d in drivers
        ]

        self.pole = Select(
            placeholder="Pole Position",
            options=options
        )

        self.p1 = Select(
            placeholder="P1",
            options=options
        )

        self.p2 = Select(
            placeholder="P2",
            options=options
        )

        self.p3 = Select(
            placeholder="P3",
            options=options
        )

        self.pole.callback = self.cb_pole
        self.p1.callback = self.cb_p1
        self.p2.callback = self.cb_p2
        self.p3.callback = self.cb_p3

        self.add_item(self.pole)
        self.add_item(self.p1)
        self.add_item(self.p2)
        self.add_item(self.p3)

        self.add_item(
            self.submit_button()
        )

    async def cb_pole(self, i):
        self.data["pole"] = self.pole.values[0]
        await i.response.defer()

    async def cb_p1(self, i):
        self.data["p1"] = self.p1.values[0]
        await i.response.defer()

    async def cb_p2(self, i):
        self.data["p2"] = self.p2.values[0]
        await i.response.defer()

    async def cb_p3(self, i):
        self.data["p3"] = self.p3.values[0]
        await i.response.defer()

    def submit_button(self):

        btn = Button(
            label="Submit Results",
            style=discord.ButtonStyle.red
        )

        async def cb(i):
            
            check_db()

            race = self.race

            if None in self.data.values():
                return await i.response.send_message(
                    "❌ Select all results first",
                    ephemeral=True
                )
            c.execute(
                "SELECT status FROM races WHERE race=%s",
                (race,)
            )

            status = c.fetchone()

            if status and status[0] == "scored":
                return await i.response.send_message(
                    "❌ Results already submitted for this race",
                    ephemeral=True
                )

            c.execute(
                "SELECT * FROM predictions WHERE race=%s",
                (race,)
            )

            rows = c.fetchall()

            for r in rows:

                pts = calculate(
                    r[2:],
                    self.data
                )

                c.execute("""
                INSERT INTO scores (user_id, points)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET
                points = scores.points + EXCLUDED.points
                """, (
                    r[0],
                    pts
                ))

            c.execute(
                "UPDATE races SET status='scored' WHERE race=%s",
                (race,)
            )
            
            conn.commit()

            await i.response.send_message(
                f"🏆 Results saved for {race}",
                ephemeral=True
            )

        btn.callback = cb

        return btn

# ---------------- SET RESULTS ----------------
@bot.tree.command(name="setresults")
async def setresults(i: discord.Interaction):
    
    check_db()

    allowed_role = discord.utils.get(
        i.user.roles,
        name="MODs"
    )

    if not (
        i.user.guild_permissions.administrator
        or allowed_role
    ):
        return await i.response.send_message(
            "No permission",
            ephemeral=True
        )

    race = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No active race",
            ephemeral=True
        )


    await i.response.send_message(
        f"🏁 Set results for **{race}**",
        view=ResultView(race),
        ephemeral=True
    )
# ---------------- LEADERBOARD ----------------
@bot.tree.command(name="leaderboard")
async def leaderboard(i: discord.Interaction):
    
    check_db()

    c.execute("""
    SELECT user_id, points
    FROM scores
    ORDER BY points DESC
    LIMIT 10
    """)

    rows = c.fetchall()

    embed = discord.Embed(
        title="📊 Poll Leaderboard",
        color=0xFF0000
    )

    for idx, r in enumerate(rows, start=1):

        embed.add_field(
            name=f"#{idx}",
            value=f"<@{r[0]}> — {r[1]} pts",
            inline=False
        )

    await i.response.send_message(
        embed=embed
    )

# ---------------- MYSTATS ----------------
@bot.tree.command(name="mystats")
async def mystats(i: discord.Interaction):
    
    check_db()

    uid = str(i.user.id)

    c.execute(
        "SELECT points FROM scores WHERE user_id=%s",
        (uid,)
    )

    row = c.fetchone()

    points = row[0] if row else 0

    c.execute("""
    SELECT user_id
    FROM scores
    ORDER BY points DESC
    """)

    rows = c.fetchall()

    rank = 1

    for r in rows:

        if r[0] == uid:
            break

        rank += 1

    embed = discord.Embed(
        title="📊 Your Stats",
        color=0x00ffcc
    )

    embed.add_field(
        name="Points",
        value=str(points),
        inline=False
    )

    embed.add_field(
        name="Rank",
        value=f"#{rank}",
        inline=False
    )

    await i.response.send_message(
        embed=embed,
        ephemeral=True
    )

# ---------------- RANK ----------------
@bot.tree.command(name="rank")
async def rank(
    i: discord.Interaction,
    user: discord.Member
):
    
    check_db()

    uid = str(user.id)

    c.execute(
        "SELECT points FROM scores WHERE user_id=%s",
        (uid,)
    )

    row = c.fetchone()

    points = row[0] if row else 0

    c.execute("""
    SELECT user_id
    FROM scores
    ORDER BY points DESC
    """)

    rows = c.fetchall()

    rank = 1

    for r in rows:

        if r[0] == uid:
            break

        rank += 1

    await i.response.send_message(
        f"🏁 {user.mention}\n"
        f"Points: **{points}**\n"
        f"Rank: **#{rank}**"
    )

# ---------------- RUN ----------------
bot.run(TOKEN)