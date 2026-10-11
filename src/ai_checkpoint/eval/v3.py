"""handover-v3: human conversations from OpenAssistant (Apache-2.0).

The message text is copied from ``datasets/handover-v3/sources/oasst1_threads.json``
and is not rewritten. Answer keys and probes use phrases that already appear
in that text. There is no filler and no planted secret.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SOURCE_PATH = Path(__file__).resolve().parents[3] / "datasets" / "handover-v3" / "sources" / "oasst1_threads.json"

# Every string below is checked against the conversation. Keep them as substrings of the thread.
_SPECS: List[dict] = [
    dict(
        subject="coding",
        description="A person asks for a script that logs precipitation to a CSV every 30 minutes, then switches the source from OpenWeatherMap to AccuWeather.",
        decisions=[dict(
            topic="which weather API the logger should call",
            decision="use the AccuWeather API instead of openweathermap",
            reason="AccuWeather has the concept of 'locations', so an extra call has to be made to determine which location to request weather data about.",
            rejected="OpenWeatherMap API",
        )],
        verbatim=[
            dict(label="how often the script sleeps", type="number", text="time.sleep(1800)"),
            dict(label="install command", type="command", text="pip install requests pandas"),
            dict(label="CSV path in the script", type="code", text="output_csv = 'precipitation_data.csv'"),
        ],
        correction=dict(what="weather API", old="OpenWeatherMap", new="AccuWeather"),
        next_step=dict(
            text="you will need to register for access to AccuWeather (https://developer.accuweather.com/user/register)",
            required_terms=["AccuWeather", "precipitation.py"],
        ),
        environment={
            "files": [
                dict(path="precipitation.py", status="still_relevant"),
                dict(path="precipitation_data.csv", status="still_relevant"),
            ],
            "tools": [
                dict(name="pandas", status="still_relevant"),
                dict(name="requests", status="still_relevant"),
            ],
            "references": [
                dict(name="AccuWeather", url="https://developer.accuweather.com/user/register", status="still_relevant"),
                dict(name="OpenWeatherMap", url="https://openweathermap.org/api", status="done_with"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="Which weather API did we switch the logger to, why does that API need an extra call, and which API did we drop?",
                 key_facts=["use the AccuWeather API instead of openweathermap",
                            "AccuWeather has the concept of 'locations', so an extra call has to be made to determine which location to request weather data about.",
                            "OpenWeatherMap API"],
                 known_wrong=["The logger still calls the OpenWeatherMap API"]),
            dict(kind="verbatim", target="verbatim[1]",
                 question="What exact pip command installs the libraries for the first script?",
                 key_facts=["pip install requests pandas"]),
            dict(kind="verbatim", target="verbatim[2]",
                 question="What is the exact assignment of the output CSV path in the script?",
                 key_facts=["output_csv = 'precipitation_data.csv'"]),
            dict(kind="stale", target="correction",
                 question="Which weather API is the current script written against?",
                 key_facts=["AccuWeather"], known_wrong=["OpenWeatherMap"]),
            dict(kind="next_step", target="next_step",
                 question="What does the thread say I still need to do before the AccuWeather script can run?",
                 key_facts=["you will need to register for access to AccuWeather (https://developer.accuweather.com/user/register)"]),
            dict(kind="fact", target="environment.files",
                 question="What file should the AccuWeather script replace the contents of?",
                 key_facts=["precipitation.py"]),
        ],
    ),
    dict(
        subject="data_analysis",
        description="A person asks for a pandas summary of page impressions and top queries, then for a PyTorch model that predicts impressions.",
        decisions=[dict(
            topic="predicting impressions",
            decision="create a simple regression model using Pytorch to predict impressions for a given date",
            reason="features = ['date', 'clicks']",
            rejected="Get the top 5 queries by impressions for each page and date",
        )],
        verbatim=[
            dict(label="training epochs", type="number", text="num_epochs = 1000"),
            dict(label="optimizer line", type="command", text="optimizer = torch.optim.SGD(model.parameters(), lr=0.01)"),
            dict(label="pandas groupby", type="code", text="grouped = df.groupby(['page', 'date']).agg({'impressions': 'sum'})"),
        ],
        next_step=dict(
            text="create a simple regression model using Pytorch to predict impressions for a given date",
            required_terms=["Pytorch", "impressions", "date"],
        ),
        environment={
            "files": [dict(path="impressions_data.csv", status="still_relevant")],
            "tools": [
                dict(name="pandas", status="still_relevant"),
                dict(name="PyTorch", status="still_relevant"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="What model did we ask for to predict impressions, which features does that example use, and which earlier aggregation did that request leave behind?",
                 key_facts=["create a simple regression model using Pytorch to predict impressions for a given date",
                            "features = ['date', 'clicks']",
                            "Get the top 5 queries by impressions for each page and date"]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="How many epochs does the example train for? Quote the assignment.",
                 key_facts=["num_epochs = 1000"]),
            dict(kind="verbatim", target="verbatim[2]",
                 question="Quote the pandas line that sums impressions by page and date.",
                 key_facts=["grouped = df.groupby(['page', 'date']).agg({'impressions': 'sum'})"]),
            dict(kind="next_step", target="next_step",
                 question="What did I ask for after the pandas summary?",
                 key_facts=["create a simple regression model using Pytorch to predict impressions for a given date"]),
            dict(kind="fact", target="environment.files",
                 question="Which CSV does the PyTorch example load?",
                 key_facts=["impressions_data.csv"]),
        ],
    ),
    dict(
        subject="writing",
        description="A person asks for a 200-word family-medicine residency essay and then says the draft is 188 words.",
        decisions=[dict(
            topic="the length of the residency essay",
            decision="give me one that's more close to 200 words",
            reason="This is actually 188 words, not 200 words.",
            rejected="188 words",
        )],
        verbatim=[
            dict(label="length of the first draft", type="number", text="188 words"),
            dict(label="requested length", type="number", text="200 words"),
            dict(label="the essay's field", type="code", text="family medicine"),
        ],
        correction=dict(what="essay length", old="188 words", new="200 words"),
        next_step=dict(
            text="give me one that's more close to 200 words",
            required_terms=["200 words", "188 words"],
        ),
        environment={
            "references": [dict(name="family medicine", status="still_relevant")],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="What length did I ask the essay to move to, why, and what length was the draft we set aside?",
                 key_facts=["give me one that's more close to 200 words",
                            "This is actually 188 words, not 200 words.",
                            "188 words"],
                 known_wrong=["The essay we are keeping is 188 words"]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="How long did I say the first draft was?",
                 key_facts=["188 words"]),
            dict(kind="stale", target="correction",
                 question="What essay length are we aiming for now?",
                 key_facts=["200 words"], known_wrong=["188 words"]),
            dict(kind="next_step", target="next_step",
                 question="What did I ask for after counting the first draft?",
                 key_facts=["give me one that's more close to 200 words"]),
            dict(kind="fact", target="environment.references",
                 question="Which residency field is the essay about?",
                 key_facts=["family medicine"]),
        ],
    ),
    dict(
        subject="literature",
        description="A person asks how to write a clear essay, then narrows it to a book or movie whose main character makes a hard choice.",
        decisions=[dict(
            topic="which story to use for the essay",
            decision='watching the Oscar winning movie "No Country for Old Men"',
            reason="Llewelen Moss has to decide between keeping a large sum of money he found or giving up the money to escape the seemingly unstoppable hitman Anton Chigurh",
            rejected="Use simple language",
        )],
        verbatim=[
            dict(label="the film", type="code", text="No Country for Old Men"),
            dict(label="the novelist", type="code", text="Cormac McCarthy"),
            dict(label="the choice", type="number", text="keeping a large sum of money"),
        ],
        next_step=dict(
            text="Can you give more details?",
            required_terms=["No Country for Old Men", "Anton Chigurh"],
        ),
        environment={
            "references": [
                dict(name="No Country for Old Men", status="still_relevant"),
                dict(name="Cormac McCarthy", status="still_relevant"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="Which film did the thread recommend for the essay, what choice does the main character face, and what writing tip came before that recommendation?",
                 key_facts=['watching the Oscar winning movie "No Country for Old Men"',
                            "Llewelen Moss has to decide between keeping a large sum of money he found or giving up the money to escape the seemingly unstoppable hitman Anton Chigurh",
                            "Use simple language"]),
            dict(kind="verbatim", target="verbatim[1]",
                 question="Who wrote the novel the recommendation is based on?",
                 key_facts=["Cormac McCarthy"]),
            dict(kind="next_step", target="next_step",
                 question="What did I ask for after the first recommendation?",
                 key_facts=["Can you give more details?"]),
            dict(kind="fact", target="environment.references",
                 question="Which film is the essay recommendation about?",
                 key_facts=["No Country for Old Men"]),
        ],
    ),
    dict(
        subject="housing",
        description="A person in Los Angeles asks for a cost estimate for a 3-bedroom house, then for the trades involved and how to find a contractor.",
        decisions=[dict(
            topic="foundation type",
            decision="A concrete slab foundation is the most common and affordable option",
            reason="while a basement foundation or pier and beam foundation may be more expensive",
            rejected="a basement foundation",
        )],
        verbatim=[
            dict(label="cost per square foot", type="number", text="$200 to $400"),
            dict(label="total estimate", type="number", text="$500,000 to $1,000,000"),
            dict(label="contractor directory", type="command", text="https://www.angi.com/"),
        ],
        next_step=dict(
            text="https://www.angi.com/",
            required_terms=["angi.com", "yelp.com"],
        ),
        environment={
            "references": [
                dict(name="Angie's List", url="https://www.angi.com/", status="still_relevant"),
                dict(name="Yelp", url="https://www.yelp.com/", status="still_relevant"),
                dict(name="Better Business Bearau", url="https://www.bbb.org/near-me/general-contractor", status="still_relevant"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="Which foundation did the thread call the most affordable, why are the others different, and which foundation was the more expensive example?",
                 key_facts=["A concrete slab foundation is the most common and affordable option",
                            "while a basement foundation or pier and beam foundation may be more expensive",
                            "a basement foundation"]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="What cost per square foot did the thread give for Los Angeles?",
                 key_facts=["$200 to $400"]),
            dict(kind="verbatim", target="verbatim[1]",
                 question="What total cost range did the thread give for the 3-bedroom house?",
                 key_facts=["$500,000 to $1,000,000"]),
            dict(kind="next_step", target="next_step",
                 question="Which contractor site did the thread link first among the directories?",
                 key_facts=["https://www.angi.com/"]),
            dict(kind="fact", target="environment.references",
                 question="Which directory URLs did the thread give for finding a contractor?",
                 key_facts=["https://www.angi.com/", "https://www.yelp.com/"]),
        ],
    ),
    dict(
        subject="manufacturing",
        description="A person on an assembly line records stations that run over cycle time and asks how to turn that into an SOP.",
        decisions=[dict(
            topic="how operators should follow one process",
            decision="Developing a Standard Operating Procedure (SOP) can help ensure that all operators follow the same process and adhere to best practices, which can improve efficiency.",
            reason="provide clear guidance to operators on how to complete their work efficiently and consistently",
            rejected="avoid jargon",
        )],
        verbatim=[
            dict(label="what gets recorded", type="code", text="the station number, the amount of time over cycle, and the reason"),
            dict(label="review cadence", type="number", text="quarterly, semi-annually, or annually"),
            dict(label="document style", type="command", text="avoid jargon"),
        ],
        next_step=dict(
            text="Assign a person or team responsible for maintaining the SOP.",
            required_terms=["SOP", "quarterly"],
        ),
        environment={
            "skills": [dict(name="SOP", status="still_relevant")],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="What document did we decide to write for the operators, what guidance should it give, and what should its language avoid?",
                 key_facts=["Developing a Standard Operating Procedure (SOP) can help ensure that all operators follow the same process and adhere to best practices, which can improve efficiency.",
                            "provide clear guidance to operators on how to complete their work efficiently and consistently",
                            "avoid jargon"]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="What three things do we record when a station runs long?",
                 key_facts=["the station number, the amount of time over cycle, and the reason"]),
            dict(kind="verbatim", target="verbatim[1]",
                 question="How often did the thread say the SOP could be reviewed?",
                 key_facts=["quarterly, semi-annually, or annually"]),
            dict(kind="next_step", target="next_step",
                 question="Who should own the SOP once it exists?",
                 key_facts=["Assign a person or team responsible for maintaining the SOP."]),
            dict(kind="fact", target="environment.skills",
                 question="What document are we maintaining?",
                 key_facts=["SOP"]),
        ],
    ),
    dict(
        subject="engineering",
        description="A person designing fan control for an industrial airflow system asks about PID versus fuzzy logic.",
        decisions=[dict(
            topic="PID versus fuzzy logic for the fans",
            decision="FLC may be preferable for complex, nonlinear systems where models are difficult to obtain",
            reason="PID may be better for well-understood linear systems where performance is a priority",
            rejected="Can be slower to respond compared to well-tuned PID.",
        )],
        verbatim=[
            dict(label="fuzzy logic", type="code", text="Fuzzy logic control (FLC)"),
            dict(label="the other controller", type="code", text="PID controller"),
            dict(label="FLC downside", type="number", text="Can be slower to respond compared to well-tuned PID."),
        ],
        next_step=dict(
            text="FLC may be preferable for complex, nonlinear systems where models are difficult to obtain, while PID may be better for well-understood linear systems where performance is a priority.",
            required_terms=["FLC", "PID", "nonlinear"],
        ),
        environment={
            "tools": [
                dict(name="PID controller", status="still_relevant"),
                dict(name="FLC", status="still_relevant"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="When did the thread say FLC is preferable, when did it say PID is better, and what downside did it give FLC?",
                 key_facts=["FLC may be preferable for complex, nonlinear systems where models are difficult to obtain",
                            "PID may be better for well-understood linear systems where performance is a priority",
                            "Can be slower to respond compared to well-tuned PID."]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="What does the thread expand FLC as?",
                 key_facts=["Fuzzy logic control (FLC)"]),
            dict(kind="next_step", target="next_step",
                 question="What comparison did the thread settle on between FLC and PID?",
                 key_facts=["FLC may be preferable for complex, nonlinear systems where models are difficult to obtain, while PID may be better for well-understood linear systems where performance is a priority."]),
            dict(kind="fact", target="environment.tools",
                 question="Which two controllers does the thread compare?",
                 key_facts=["PID controller", "FLC"]),
        ],
    ),
    dict(
        subject="games",
        description="A person compares web game engines, then narrows it to a one-weekend charity game with little coding experience, and asks about the Unreal license.",
        decisions=[dict(
            topic="engine for a weekend charity game",
            decision="Unreal Engine might be favorable for your project due to the sheer amount of high quality assets available for free",
            reason="Unity is a very popular engine with people getting into game development, due to the large amount of tutorials available for learning.",
            rejected="Phaser is limited to 2D games and may not be suitable for more complex games.",
        )],
        verbatim=[
            dict(label="free tier", type="number", text="less than $1 million per year"),
            dict(label="royalty", type="number", text="flat 5% royalty fee"),
            dict(label="engine set aside", type="code", text="Phaser is limited to 2D games"),
        ],
        next_step=dict(
            text="developers can use the engine for free if their gross revenue from the product is less than $1 million per year",
            required_terms=["Unreal Engine", "$1 million", "5%"],
        ),
        environment={
            "tools": [
                dict(name="Unreal Engine", status="still_relevant"),
                dict(name="Unity", status="still_relevant"),
                dict(name="Phaser", status="done_with"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="Which engine did the thread call favorable for the weekend project, which other engine did it mention for beginners, and which engine did it say is limited to 2D?",
                 key_facts=["Unreal Engine might be favorable for your project due to the sheer amount of high quality assets available for free",
                            "Unity is a very popular engine with people getting into game development, due to the large amount of tutorials available for learning.",
                            "Phaser is limited to 2D games and may not be suitable for more complex games."]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="Below what yearly gross revenue did the thread say Unreal Engine is free?",
                 key_facts=["less than $1 million per year"]),
            dict(kind="verbatim", target="verbatim[1]",
                 question="What royalty did the thread say Unreal charges after that threshold?",
                 key_facts=["flat 5% royalty fee"]),
            dict(kind="next_step", target="next_step",
                 question="On what revenue condition did the thread say developers can use Unreal Engine for free?",
                 key_facts=["developers can use the engine for free if their gross revenue from the product is less than $1 million per year"]),
            dict(kind="fact", target="environment.tools",
                 question="Which engine did the thread say is limited to 2D games?",
                 key_facts=["Phaser"]),
        ],
    ),
    dict(
        subject="geography",
        description="A person asks several geography questions. The first answer gives the Earth-Moon distance and asks whether city size means land area or population. The follow-up asks for land area and for Mars.",
        decisions=[dict(
            topic="how to measure the largest city",
            decision="I meant in terms of land area for my first question.",
            reason="The largest incorporated municipality in North America is the regional municpality of Woodbuffalo (Alberta, Canada) with a land area of 24570.53 square miles",
            rejected="122.27 million miles",
        )],
        verbatim=[
            dict(label="Wood Buffalo land area", type="number", text="24570.53 square miles"),
            dict(label="average Earth-Mars distance", type="number", text="140 million miles"),
            dict(label="the municipality", type="code", text="Woodbuffalo (Alberta, Canada)"),
        ],
        correction=dict(what="distance figure used for a planet question", old="122.27 million miles", new="140 million miles"),
        next_step=dict(
            text="The largest incorporated municipality in North America is the regional municpality of Woodbuffalo (Alberta, Canada) with a land area of 24570.53 square miles",
            required_terms=["Woodbuffalo", "24570.53", "140 million miles"],
        ),
        environment={
            "references": [
                dict(name="Woodbuffalo", status="still_relevant"),
                dict(name="Neptune", status="still_relevant"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="Did I want city size by land area or by the other measure the assistant asked about, and which place did the thread then name?",
                 key_facts=["I meant in terms of land area for my first question.",
                            "The largest incorporated municipality in North America is the regional municpality of Woodbuffalo (Alberta, Canada) with a land area of 24570.53 square miles"]),
            dict(kind="verbatim", target="verbatim[0]",
                 question="What land area did the thread give for Wood Buffalo?",
                 key_facts=["24570.53 square miles"]),
            dict(kind="stale", target="correction",
                 question="What average Earth-Mars distance did the later answer give?",
                 key_facts=["140 million miles"], known_wrong=["122.27 million miles"]),
            dict(kind="next_step", target="next_step",
                 question="Which municipality did the thread name as the largest by land area, and what area did it give?",
                 key_facts=["The largest incorporated municipality in North America is the regional municpality of Woodbuffalo (Alberta, Canada) with a land area of 24570.53 square miles"]),
            dict(kind="fact", target="environment.references",
                 question="Which planet did the thread call the last one discovered in our solar system?",
                 key_facts=["Neptune"]),
        ],
    ),
    dict(
        subject="hardware",
        description="A person asks about consumer graphics cards for AI, then corrects that to a laptop.",
        decisions=[dict(
            topic="a GPU for AI on a laptop",
            decision="The most popular GPU for running AI on a laptop is Nvidia GeForce RTX series.",
            reason="They are also equipped with Tensor Cores that accelerate AI workloads.",
            rejected="Nvidia GeForce RTX 3080",
        )],
        verbatim=[
            dict(label="desktop card named first", type="code", text="Nvidia GeForce RTX 3080"),
            dict(label="laptop recommendation", type="code", text="Nvidia GeForce RTX series"),
            dict(label="AMD option from the first reply", type="number", text="AMD Radeon VII"),
        ],
        correction=dict(what="machine the GPU has to fit", old="Nvidia GeForce RTX 3080", new="Nvidia GeForce RTX series"),
        next_step=dict(
            text="The most popular GPU for running AI on a laptop is Nvidia GeForce RTX series.",
            required_terms=["laptop", "Nvidia GeForce RTX series"],
        ),
        environment={
            "tools": [
                dict(name="Nvidia GeForce RTX series", status="still_relevant"),
                dict(name="Nvidia GeForce RTX 3080", status="done_with"),
            ],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="Which GPU family did the thread recommend for AI on a laptop, why, and which desktop card was named before I said I wanted a laptop?",
                 key_facts=["The most popular GPU for running AI on a laptop is Nvidia GeForce RTX series.",
                            "They are also equipped with Tensor Cores that accelerate AI workloads.",
                            "Nvidia GeForce RTX 3080"],
                 known_wrong=["The laptop recommendation is the Nvidia GeForce RTX 3080"]),
            dict(kind="verbatim", target="verbatim[2]",
                 question="Which AMD card did the first reply mention?",
                 key_facts=["AMD Radeon VII"]),
            dict(kind="stale", target="correction",
                 question="What should I shop for once I said the machine is a laptop?",
                 key_facts=["Nvidia GeForce RTX series"], known_wrong=["Nvidia GeForce RTX 3080"]),
            dict(kind="next_step", target="next_step",
                 question="What is the laptop GPU recommendation?",
                 key_facts=["The most popular GPU for running AI on a laptop is Nvidia GeForce RTX series."]),
            dict(kind="fact", target="environment.tools",
                 question="Which GPU recommendation is the current one for the laptop?",
                 key_facts=["Nvidia GeForce RTX series"]),
        ],
    ),
    dict(
        subject="learning",
        description="A person asks how to learn Python, is pointed at a book and at a dice-run exercise, then asks for help writing longest_run after expanding the trial count.",
        decisions=[dict(
            topic="a first Python exercise",
            decision="Probability exercises are a good start.",
            reason="Imagine a six-sided die.",
            rejected="developing a game",
        )],
        verbatim=[
            dict(label="rolls in one trial", type="number", text="roll the die 100 times"),
            dict(label="how many trials I added", type="number", text="1000x sounds good for now."),
            dict(label="function to write", type="code", text="def longest_run(outcomes):"),
        ],
        correction=dict(what="how many times to repeat the experiment", old="roll the die 100 times", new="1000x sounds good for now."),
        next_step=dict(
            text="def longest_run(outcomes):",
            required_terms=["longest_run", "1000x"],
        ),
        environment={
            "references": [
                dict(name="Automate The Boring Stuff with Python", url="https://automatetheboringstuff.com/", status="still_relevant"),
            ],
            "tools": [dict(name="numpy", status="still_relevant")],
        },
        probes=[
            dict(kind="decision", target="decisions[0]",
                 question="What kind of exercise did the thread say was a good start, what object does it use, and what other project idea was offered first?",
                 key_facts=["Probability exercises are a good start.",
                            "Imagine a six-sided die.",
                            "developing a game"]),
            dict(kind="verbatim", target="verbatim[2]",
                 question="Quote the function signature given for the longest run.",
                 key_facts=["def longest_run(outcomes):"]),
            dict(kind="stale", target="correction",
                 question="How many times did I say to repeat the experiment, after the single 100-roll trial?",
                 key_facts=["1000x sounds good for now."], known_wrong=["roll the die 100 times"]),
            dict(kind="next_step", target="next_step",
                 question="What function was I stuck on?",
                 key_facts=["def longest_run(outcomes):"]),
            dict(kind="fact", target="environment.references",
                 question="Which book and URL did the thread recommend first?",
                 key_facts=["Automate The Boring Stuff with Python", "https://automatetheboringstuff.com/"]),
        ],
    ),
]


def _load() -> Dict[str, Any]:
    try:
        return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"cannot read handover-v3 source {SOURCE_PATH}: {e}") from None


def _messages(thread: dict) -> List[dict]:
    out = []
    for m in thread["messages"]:
        role = m["role"]
        if role == "prompter":
            role = "user"
        elif role != "assistant":
            raise ValueError(f"{thread['message_tree_id']}: unexpected role {role!r}")
        text = m["text"].strip()
        if not text:
            raise ValueError(f"{thread['message_tree_id']}: empty message")
        out.append({"role": role, "content": text})
    return out


def _first(messages: List[dict], text: str) -> int:
    low = text.lower()
    for i, m in enumerate(messages):
        if low in m["content"].lower():
            return i
    raise ValueError(f"phrase not in conversation: {text!r}")


def build_scenarios() -> List[dict]:
    blob = _load()
    by_subject = {t["subject"]: t for t in blob["threads"]}
    if set(by_subject) != {s["subject"] for s in _SPECS}:
        raise ValueError("handover-v3 annotations and source threads do not match")
    scenarios = []
    for spec in _SPECS:
        thread = by_subject[spec["subject"]]
        messages = _messages(thread)
        key: Dict[str, Any] = dict(decisions=spec["decisions"], verbatim=spec["verbatim"])
        corr: Optional[dict] = spec.get("correction")
        if corr:
            key["correction"] = corr
        key["next_step"] = spec["next_step"]
        meta = dict(
            seed=None, task=spec["subject"], length=len(messages), generator="handover-v3",
            filler_indexes=[],
            next_step_index=_first(messages, spec["next_step"]["text"]),
            source=dict(
                dataset=blob["dataset"], revision=blob["revision"], license=blob["license"],
                url=blob["url"], message_tree_id=thread["message_tree_id"],
                message_ids=[m["message_id"] for m in thread["messages"]],
            ),
        )
        if corr:
            meta["correction_old_index"] = _first(messages, corr["old"])
            meta["correction_new_index"] = _first(messages, corr["new"])
            chat = "\n".join(m["content"] for m in messages).lower()
            if chat.find(corr["old"].lower()) >= chat.find(corr["new"].lower()):
                raise ValueError(f"{spec['subject']}: correction old appears after new")
        scenarios.append(dict(
            name=spec["subject"],
            description=spec["description"],
            messages=messages,
            probes=spec["probes"],
            answer_key=key,
            environment=spec.get("environment") or {},
            secret_values=[],
            meta=meta,
        ))
    return scenarios
