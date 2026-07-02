import discord
from discord.ext import commands
from discord.ui import View, Select, Button
from dotenv import load_dotenv
import os
from database import execute, execute_commit, fetchone, fetchall
from typing import Literal, Optional

# ---------------- TOKEN ----------------
load_dotenv(".env.test")

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------- DATABASE ----------------

execute_commit("""
CREATE TABLE IF NOT EXISTS predictions (
    user_id TEXT,
    race TEXT,
    sprint_winner TEXT,
    pole TEXT,
    p1 TEXT,
    p2 TEXT,
    p3 TEXT,
    PRIMARY KEY(user_id, race)
)
""")

execute_commit("""
CREATE TABLE IF NOT EXISTS races (
    race TEXT PRIMARY KEY,
    status TEXT
)
""")

execute_commit("""
CREATE TABLE IF NOT EXISTS current_race (
    id INTEGER PRIMARY KEY,
    race TEXT,
    weekend_type TEXT DEFAULT 'normal'
)
""")

execute_commit("""
CREATE TABLE IF NOT EXISTS scores (
    user_id TEXT PRIMARY KEY,
    points INTEGER DEFAULT 0
)
""")

execute_commit("""
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

    execute_commit("""
    INSERT INTO drivers (name)
    VALUES (%s)
    ON CONFLICT (name) DO NOTHING
    """, (d,))


# ---------------- BOT ----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- READY ----------------
@bot.event
async def on_ready():

    if not hasattr(bot, "synced"):

        synced = await bot.tree.sync()

        bot.synced = True

        print(f"Synced {len(synced)} commands")

    print(f"Logged in as {bot.user}")

# ---------------- HELPERS ----------------

def get_current_race():

    row = fetchone(
        """
        SELECT race, weekend_type
        FROM current_race
        WHERE id = 1
        """
    )

    if row:
        return row[0], row[1]

    return None, "normal"


def get_drivers():

    rows = fetchall(
        """
        SELECT name
        FROM drivers
        ORDER BY name
        """
    )

    return [r[0] for r in rows]


def calculate(pred, res, sprint=False):

    points = 0

    idx = 0

    if sprint:

        if pred[idx] == res["sprint_winner"]:
            points += 2

        idx += 1

    if pred[idx] == res["pole"]:
        points += 3

    idx += 1

    if pred[idx] == res["p1"]:
        points += 5

    idx += 1

    if pred[idx] == res["p2"]:
        points += 3

    idx += 1

    if pred[idx] == res["p3"]:
        points += 3

    if (
        pred[idx - 2] == res["p1"]
        and pred[idx - 1] == res["p2"]
        and pred[idx] == res["p3"]
    ):
        points += 5

    return points

# ---------------- PREDICT UI ----------------
class NormalPredictView(View):

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
            style=discord.ButtonStyle.green,
            row=4
        )

        async def cb(i):
            await i.response.defer(ephemeral=True)
            

            race = self.race

            required = ["pole", "p1", "p2", "p3"]

            if any(self.data[k] is None for k in required):
                return await i.followup.send(
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
                return await i.followup.send(
                    "❌ P1, P2 and P3 must be different drivers",
                    ephemeral=True
                    )

            r = fetchone(
                "SELECT status FROM races WHERE race=%s",
                (race,)
            )

            if not r or r[0] != "open":
                return await i.followup.send(
                    "❌ Race closed",
                    ephemeral=True
                )

            existing = fetchone(
                """
                SELECT *
                FROM predictions
                WHERE user_id=%s
                AND race=%s
                """,
                (
                    str(self.user_id),
                    race
                )
            )

            if existing:
                return await i.followup.send(
                    "❌ Already submitted",
                    ephemeral=True
                )

            execute_commit(
                """
                INSERT INTO predictions
                (
                    user_id,
                    race,
                    sprint_winner,
                    pole,
                    p1,
                    p2,
                    p3
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(self.user_id),
                    race,
                    None,
                    self.data["pole"],
                    self.data["p1"],
                    self.data["p2"],
                    self.data["p3"]
                )
            )       


            await i.followup.send(
                "🏁 Prediction saved!",
                ephemeral=True
            )

        btn.callback = cb

        return btn
class SprintStep1View(View):

    def __init__(self, race, user_id):

        super().__init__(timeout=180)

        self.race = race
        self.user_id = user_id

        drivers = get_drivers()

        options = [
            discord.SelectOption(
                label=d,
                value=d
            )
            for d in drivers
        ]

        self.data = {
            "sprint_winner": None,
            "pole": None
        }

        self.sprint = Select(
            placeholder="Sprint Winner",
            options=options
        )

        self.pole = Select(
            placeholder="Pole Position",
            options=options
        )

        self.sprint.callback = self.cb_sprint
        self.pole.callback = self.cb_pole

        self.add_item(self.sprint)
        self.add_item(self.pole)

        next_btn = Button(
            label="Next ➜",
            style=discord.ButtonStyle.blurple
        )

        next_btn.callback = self.next_page

        self.add_item(next_btn)

    async def cb_sprint(self, interaction):

        self.data["sprint_winner"] = self.sprint.values[0]

        await interaction.response.defer()

    async def cb_pole(self, interaction):

        self.data["pole"] = self.pole.values[0]

        await interaction.response.defer()

    async def next_page(self, interaction):

        if (
            self.data["sprint_winner"] is None
            or
            self.data["pole"] is None
        ):
            return await interaction.response.send_message(
                "❌ Please select Sprint Winner and Pole Position.",
                ephemeral=True
            )

        embed = discord.Embed(
            title=f"⚡ {self.race}",
            description="**Sprint Weekend Prediction**\n\n**Step 2 of 2**",
            color=0xE10600
        )

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=SprintStep2View(
                self.race,
                self.user_id,
                self.data
            )
        )
        
class SprintStep2View(View):

    def __init__(self, race, user_id, data):

        super().__init__(timeout=180)

        self.race = race
        self.user_id = user_id
        self.data = data

        drivers = get_drivers()

        options = [
            discord.SelectOption(
                label=d,
                value=d
            )
            for d in drivers
        ]

        self.data["p1"] = None
        self.data["p2"] = None
        self.data["p3"] = None

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

        self.p1.callback = self.cb_p1
        self.p2.callback = self.cb_p2
        self.p3.callback = self.cb_p3

        self.add_item(self.p1)
        self.add_item(self.p2)
        self.add_item(self.p3)

        self.add_item(self.submit_button())

    async def cb_p1(self, interaction):

        self.data["p1"] = self.p1.values[0]

        await interaction.response.defer()

    async def cb_p2(self, interaction):

        self.data["p2"] = self.p2.values[0]

        await interaction.response.defer()

    async def cb_p3(self, interaction):

        self.data["p3"] = self.p3.values[0]

        await interaction.response.defer()

    def submit_button(self):

        btn = Button(
            label="Submit Prediction",
            style=discord.ButtonStyle.green
        )

        async def cb(interaction):
            await interaction.response.defer(ephemeral=True)

            required = [
                "sprint_winner",
                "pole",
                "p1",
                "p2",
                "p3"
            ]

            if any(self.data[x] is None for x in required):
                return await interaction.followup.send(
                    "❌ Complete all selections.",
                    ephemeral=True
                )

            podium = [
                self.data["p1"],
                self.data["p2"],
                self.data["p3"]
            ]

            if len(podium) != len(set(podium)):
                return await interaction.followup.send(
                    "❌ P1, P2 and P3 must be different.",
                    ephemeral=True
                )

            status = fetchone(
                "SELECT status FROM races WHERE race=%s",
                (self.race,)
            )

            if not status or status[0] != "open":
                return await interaction.followup.send(
                    "❌ Race closed.",
                    ephemeral=True
                )

            existing = fetchone(
                """
                SELECT *
                FROM predictions
                WHERE user_id=%s
                AND race=%s
                """,
                (
                    str(self.user_id),
                    self.race
                )
            )

            if existing:
                return await interaction.followup.send(
                    "❌ Already submitted.",
                    ephemeral=True
                )

            execute_commit(
                """
                INSERT INTO predictions
                (
                    user_id,
                    race,
                    sprint_winner,
                    pole,
                    p1,
                    p2,
                    p3
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(self.user_id),
                    self.race,
                    self.data["sprint_winner"],
                    self.data["pole"],
                    self.data["p1"],
                    self.data["p2"],
                    self.data["p3"]
                )
            )

            await interaction.followup.send(
                "🏁 Sprint prediction saved!",
                ephemeral=True
            )

        btn.callback = cb

        return btn
    

# ---------------- /PREDICT ----------------
from typing import Optional

@bot.tree.command(name="predict")
async def predict(i: discord.Interaction):

    race, weekend = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No active race set",
            ephemeral=True
        )

    emoji = "⚡" if weekend == "sprint" else "🏎️"

    if weekend == "sprint":
        view = SprintStep1View(
            race,
            i.user.id
        )
    else:
        view = NormalPredictView(
            race,
            i.user.id
        )

    await i.response.send_message(
        f"{emoji} Current Race: **{race}**",
        view=view,
        ephemeral=True
    )


# ---------------- ADMIN: SET CURRENT RACE ----------------
@bot.tree.command(name="setcurrent")
async def setcurrent(
    i: discord.Interaction,
    race: str,
    weekend_type: Literal["normal", "sprint"]
):

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

    execute_commit("""
    INSERT INTO current_race (id, race, weekend_type)
    VALUES (1, %s, %s)
    ON CONFLICT (id)
    DO UPDATE SET
        race = EXCLUDED.race,
        weekend_type = EXCLUDED.weekend_type
    """, (race.upper(), weekend_type))

    emoji = "⚡" if weekend_type == "sprint" else "🏎️"

    await i.response.send_message(
        f"{emoji} Current race set to **{race.upper()}**\n"
        f"Weekend Type: **{weekend_type.title()}**"
    )
    
# ---------------- OPEN RACE ----------------
@bot.tree.command(name="openrace")
async def openrace(i: discord.Interaction):
    
    

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

    race, _ = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No current race set",
            ephemeral=True
        )
    
    execute_commit("""
    INSERT INTO races (race, status)
    VALUES (%s,'open')
    ON CONFLICT (race)
    DO UPDATE SET status='open'
    """, (race,))

    await i.response.send_message(
        f"🏁 {race} OPENED"
    )

# ---------------- CLOSE RACE ----------------
@bot.tree.command(name="closerace")
async def closerace(i: discord.Interaction):
    
        

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

    race, _ = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No current race set",
            ephemeral=True
        )

    execute_commit("""
    INSERT INTO races (race, status)
    VALUES (%s,'closed')
    ON CONFLICT (race)
    DO UPDATE SET status='closed'
    """, (race,))

    await i.response.send_message(
        f"🔒 {race} CLOSED"
    )

# ---------------- SET RESULTS UI ----------------
class NormalResultView(View):

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
            await i.response.defer(ephemeral=True)
            

            race = self.race

            if None in self.data.values():
                return await i.followup.send(
                    "❌ Select all results first",
                    ephemeral=True
                )
            podium = [
                self.data["p1"],
                self.data["p2"],
                self.data["p3"]
            ]

            if len(podium) != len(set(podium)):
                return await i.followup.send(
                    "❌ P1, P2 and P3 must be different.",
                    ephemeral=True
                )
                
            status = fetchone(
                "SELECT status FROM races WHERE race=%s",
                (race,)
            )

            if status and status[0] == "scored":
                return await i.followup.send(
                    "❌ Results already submitted for this race",
                    ephemeral=True
                )
            if not status or status[0] != "closed":
                return await i.followup.send(
                    "❌ Race must be closed before entering results.",
                    ephemeral=True
                )

            rows = fetchall(
                """
                SELECT
                    user_id,
                    pole,
                    p1,
                    p2,
                    p3
                FROM predictions
                WHERE race=%s
                """,
                (race,)
            )
            
            if not rows:
                return await i.followup.send(
                    "❌ No predictions found for this race.",
                    ephemeral=True
                )
            

            for r in rows:

                pred = (
                    r[1],  # pole
                    r[2],  # p1
                    r[3],  # p2
                    r[4],  # p3
                )

                pts = calculate(
                    pred,
                    self.data
                )

                execute_commit("""
                INSERT INTO scores (user_id, points)
                VALUES (%s,%s)
                ON CONFLICT (user_id)
                DO UPDATE SET
                points = scores.points + EXCLUDED.points
                """, (
                    r[0],
                    pts
                ))

            execute_commit(
                "UPDATE races SET status='scored' WHERE race=%s",
                (race,)
            )

            await i.followup.send(
                f"🏆 Results saved for {race}",
                ephemeral=True
            )

        btn.callback = cb

        return btn
    
class SprintResultStep1View(View):

    def __init__(self, race):

        super().__init__(timeout=180)

        self.race = race

        drivers = get_drivers()

        options = [
            discord.SelectOption(
                label=d,
                value=d
            )
            for d in drivers
        ]

        self.data = {
            "sprint_winner": None,
            "pole": None
        }

        self.sprint = Select(
            placeholder="Sprint Winner",
            options=options
        )

        self.pole = Select(
            placeholder="Pole Position",
            options=options
        )

        self.sprint.callback = self.cb_sprint
        self.pole.callback = self.cb_pole

        self.add_item(self.sprint)
        self.add_item(self.pole)

        next_btn = Button(
            label="Next ➜",
            style=discord.ButtonStyle.blurple
        )

        next_btn.callback = self.next_page

        self.add_item(next_btn)

    async def cb_sprint(self, interaction):

        self.data["sprint_winner"] = self.sprint.values[0]

        await interaction.response.defer()

    async def cb_pole(self, interaction):

        self.data["pole"] = self.pole.values[0]

        await interaction.response.defer()

    async def next_page(self, interaction):

        if (
            self.data["sprint_winner"] is None
            or
            self.data["pole"] is None
        ):
            return await interaction.response.send_message(
                "❌ Please select Sprint Winner and Pole Position.",
                ephemeral=True
            )

        embed = discord.Embed(
            title=f"⚡ {self.race}",
            description="**Sprint Weekend Results**\n\n**Step 2 of 2**",
            color=0xE10600
        )

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=SprintResultStep2View(
                self.race,
                self.data
            )
        )
        
class SprintResultStep2View(View):

    def __init__(self, race, data):

        super().__init__(timeout=180)

        self.race = race
        self.data = data

        drivers = get_drivers()

        options = [
            discord.SelectOption(
                label=d,
                value=d
            )
            for d in drivers
        ]

        self.data["p1"] = None
        self.data["p2"] = None
        self.data["p3"] = None

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

        self.p1.callback = self.cb_p1
        self.p2.callback = self.cb_p2
        self.p3.callback = self.cb_p3

        self.add_item(self.p1)
        self.add_item(self.p2)
        self.add_item(self.p3)

        self.add_item(self.submit_button())

    async def cb_p1(self, interaction):

        self.data["p1"] = self.p1.values[0]

        await interaction.response.defer()

    async def cb_p2(self, interaction):

        self.data["p2"] = self.p2.values[0]

        await interaction.response.defer()

    async def cb_p3(self, interaction):

        self.data["p3"] = self.p3.values[0]

        await interaction.response.defer()

    def submit_button(self):

        btn = Button(
            label="Submit Results",
            style=discord.ButtonStyle.red
        )

        async def cb(interaction):
            await interaction.response.defer(ephemeral=True)

            required = [
                "sprint_winner",
                "pole",
                "p1",
                "p2",
                "p3"
            ]

            if any(self.data[x] is None for x in required):
                return await interaction.followup.send(
                    "❌ Complete all selections.",
                    ephemeral=True
                )

            podium = [
                self.data["p1"],
                self.data["p2"],
                self.data["p3"]
            ]

            if len(podium) != len(set(podium)):
                return await interaction.followup.send(
                    "❌ P1, P2 and P3 must be different.",
                    ephemeral=True
                )

            status = fetchone(
                "SELECT status FROM races WHERE race=%s",
                (self.race,)
            )

            if status and status[0] == "scored":
                return await interaction.followup.send(
                    "❌ Results already submitted.",
                    ephemeral=True
                )
            if not status or status[0] != "closed":
                return await interaction.followup.send(
                    "❌ Race must be closed before entering results.",
                    ephemeral=True
                )
            rows = fetchall(
                """
                SELECT
                    user_id,
                    sprint_winner,
                    pole,
                    p1,
                    p2,
                    p3
                FROM predictions
                WHERE race=%s
                """,
                (self.race,)
            )
            
            if not rows:
                return await interaction.followup.send(
                    "❌ No predictions found for this race.",
                    ephemeral=True
                )

            for r in rows:

                pred = (
                    r[1],  # sprint_winner
                    r[2],  # pole
                    r[3],  # p1
                    r[4],  # p2
                    r[5],  # p3
                )

                pts = calculate(
                    pred,
                    self.data,
                    sprint=True
                )

                execute_commit(
                    """
                    INSERT INTO scores (user_id, points)
                    VALUES (%s,%s)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                    points = scores.points + EXCLUDED.points
                    """,
                    (
                        r[0],
                        pts
                    )
                )

            execute_commit(
                """
                UPDATE races
                SET status='scored'
                WHERE race=%s
                """,
                (self.race,)
            )

            await interaction.followup.send(
                f"🏆 Sprint results saved for {self.race}",
                ephemeral=True
            )

        btn.callback = cb

        return btn

# ---------------- SET RESULTS ----------------
@bot.tree.command(name="setresults")
async def setresults(i: discord.Interaction):
    
    

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

    race, weekend = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No active race",
            ephemeral=True
        )


    if weekend == "sprint":
        view = SprintResultStep1View(race)
    else:
        view = NormalResultView(race)

    await i.response.send_message(
        f"🏁 Set results for **{race}**",
        view=view,
        ephemeral=True
    )
    
# ---------------- LEADERBOARD ----------------
@bot.tree.command(name="leaderboard")
async def leaderboard(i: discord.Interaction):
    
    

    rows = fetchall("""
    SELECT user_id, points
    FROM scores
    ORDER BY points DESC
    LIMIT 10
    """)
    
    embed = discord.Embed(
        title="📊 Poll Leaderboard",
        color=0xFF0000
    )

    if not rows:
        embed.description = "No scores yet."
    else:
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
    
    

    uid = str(i.user.id)

    row = fetchone(
        "SELECT points FROM scores WHERE user_id=%s",
        (uid,)
    )

    points = row[0] if row else 0

    rows = fetchall("""
    SELECT user_id
    FROM scores
    ORDER BY points DESC
    """)

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
    
    
# ---------------- VIEW PREDICTION ----------------
@bot.tree.command(name="viewprediction")
async def viewprediction(i: discord.Interaction):

    race, weekend = get_current_race()

    if not race:
        return await i.response.send_message(
            "❌ No active race.",
            ephemeral=True
        )

    row = fetchone(
        """
        SELECT sprint_winner, pole, p1, p2, p3
        FROM predictions
        WHERE user_id=%s
        AND race=%s
        """,
        (
            str(i.user.id),
            race
        )
    )

    if not row:
        return await i.response.send_message(
            "❌ You haven't submitted a prediction for this race.",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"🏁 {race} Prediction",
        color=0xE10600
    )


    if weekend == "sprint":

        embed.add_field(
            name="⚡ Sprint Winner",
            value=row[0],
            inline=False
        )

        embed.add_field(
            name="🏁 Pole Position",
            value=row[1],
            inline=False
        )

        embed.add_field(
            name="🥇 P1",
            value=row[2],
            inline=False
        )

        embed.add_field(
            name="🥈 P2",
            value=row[3],
            inline=False
        )

        embed.add_field(
            name="🥉 P3",
            value=row[4],
            inline=False
        )

    else:

        embed.add_field(
            name="🏁 Pole Position",
            value=row[1],
            inline=False
        )

        embed.add_field(
            name="🥇 P1",
            value=row[2],
            inline=False
        )

        embed.add_field(
            name="🥈 P2",
            value=row[3],
            inline=False
        )

        embed.add_field(
            name="🥉 P3",
            value=row[4],
            inline=False
        )

    embed.set_footer(
        text="Predictions are locked once the race closes."
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
    
    

    uid = str(user.id)

    row = fetchone(
        "SELECT points FROM scores WHERE user_id=%s",
        (uid,)
    )

    points = row[0] if row else 0

    rows = fetchall("""
    SELECT user_id
    FROM scores
    ORDER BY points DESC
    """)

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